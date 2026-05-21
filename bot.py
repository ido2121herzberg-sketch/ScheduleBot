import anthropic
import httpx
import json
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Configuration
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
RECURRING_TASKS_DB = "367464c26f0980bfa319c778167a19a3"
TASK_INBOX_DB = "367464c26f0980ed89b0ca6831f4b27e"

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ENERGY_CHECK = 1

def get_current_time_info():
    now = datetime.now()
    days = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    day_name = days[now.weekday()]
    return {
        "time": now.strftime("%H:%M"),
        "day": day_name
    }

async def get_notion_data(database_id, filter_body=None):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    body = filter_body if filter_body else {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, headers=headers, json=body)
            return response.json()
    except Exception as e:
        print(f"Notion error: {e}")
        return None

async def get_inbox_tasks():
    data = await get_notion_data(TASK_INBOX_DB, {
        "filter": {
            "property": "סטטוס",
            "select": {"equals": "אינבוקס"}
        }
    })
    if not data:
        return []
    tasks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = props.get("שם", {}).get("title", [{}])
        name = name[0].get("text", {}).get("content", "") if name else ""
        energy = props.get("אנרגיה", {}).get("select", {})
        energy = energy.get("name", "") if energy else ""
        if name:
            tasks.append({"name": name, "energy": energy})
    return tasks

async def get_recurring_tasks():
    data = await get_notion_data(RECURRING_TASKS_DB)
    if not data:
        return []
    tasks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = props.get("שם", {}).get("title", [{}])
        name = name[0].get("text", {}).get("content", "") if name else ""
        energy = props.get("אנרגיה", {}).get("select", {})
        energy = energy.get("name", "") if energy else ""
        preferred_time = props.get("זמן מועדף", {}).get("rich_text", [{}])
        preferred_time = preferred_time[0].get("text", {}).get("content", "") if preferred_time else ""
        if name:
            tasks.append({"name": name, "energy": energy, "preferred_time": preferred_time})
    return tasks

def ask_claude(energy_state, time_info, inbox_tasks, recurring_tasks):
    energy_map = {
        "🟢": "ירוק - אנרגיה גבוהה וחיובית",
        "🟡": "צהוב - אנרגיה נמוכה וחיובית",
        "🔴": "אדום - אנרגיה נמוכה ושלילית"
    }
    energy_desc = energy_map.get(energy_state, energy_state)
    inbox_text = "\n".join([f"- {t['name']} ({t['energy']})" for t in inbox_tasks]) if inbox_tasks else "אין משימות חדשות"
    recurring_text = "\n".join([f"- {t['name']} ({t['energy']}, {t['preferred_time']})" for t in recurring_tasks[:10]])

    prompt = f"""אתה עוזר אישי של עידו, מנטור מסחר ומוזיקאי בן 25 מתל אביב.

השעה עכשיו: {time_info['time']} ביום {time_info['day']}
מצב אנרגיה: {energy_desc}

משימות באינבוקס:
{inbox_text}

משימות חוזרות:
{recurring_text}

תן לעידו 3-4 משימות מתאימות לעכשיו לפי האנרגיה והשעה. כתוב בעברית, קצר וישיר."""

    message = claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🟢 אנרגיה גבוהה", "🟡 אנרגיה בינונית", "🔴 אנרגיה נמוכה"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("היי עידו! 👋\nמה מצב האנרגיה שלך עכשיו?", reply_markup=reply_markup)
    return ENERGY_CHECK

async def handle_energy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "🟢" in text:
        energy = "🟢"
    elif "🟡" in text:
        energy = "🟡"
    elif "🔴" in text:
        energy = "🔴"
    else:
        await update.message.reply_text("תבחר אנרגיה מהכפתורים 😊")
        return ENERGY_CHECK

    await update.message.reply_text("רגע אחד...")

    time_info = get_current_time_info()
    inbox_tasks = await get_inbox_tasks()
    recurring_tasks = await get_recurring_tasks()
    response = ask_claude(energy, time_info, inbox_tasks, recurring_tasks)
    await update.message.reply_text(response)
    return ConversationHandler.END

async def inbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = await get_inbox_tasks()
    if not tasks:
        await update.message.reply_text("האינבוקס שלך ריק 🎉")
        return
    response = "📋 המשימות באינבוקס שלך:\n\n"
    for task in tasks:
        response += f"• {task['name']} {task['energy']}\n"
    await update.message.reply_text(response)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("אוקי, מבטל.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ENERGY_CHECK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_energy)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("inbox", inbox_command))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()