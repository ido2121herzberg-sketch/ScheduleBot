import os
import json
import asyncio
import anthropic
import httpx
import pytz
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)

# Configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
RECURRING_TASKS_DB = "367464c26f0980bfa319c778167a19a3"
TASK_INBOX_DB = "367464c26f0980ed89b0ca6831f4b27e"

WEEKLY_SCHEDULES_PARENT = "378464c26f098051ba48e8f539d92328"

# Stronger model for the weekly schedule (the reasoning is heavy). If it errors,
# swap to "claude-haiku-4-5" — but expect lower quality on the constraints.
SCHEDULE_MODEL = "claude-sonnet-4-6"

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ENERGY_CHECK = 1
SCHEDULE_EXCEPTIONS = 2  # conversation state for /schedule

DAY_ORDER = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]

# Your weekly rules, verbatim from the Master weekly prompt. The generator uses
# these as the fixed rules; recurring tasks + inbox tasks + your weekly
# exceptions get injected below them at runtime.
MASTER_RULES = """אתה עוזר אישי לניהול לוח זמנים. בנה לוח זמנים מלא לשבוע הבא לפי הכללים הבאים:

**רוטינת בוקר קבועה כל יום:**
- 07:30 קימה, נטילת ידיים, מים, היגיינה, התלבשות, סידור מיטה
- 08:00-08:30 תפילת שחרית
- 08:30-09:00 ארוחת בוקר בריאה + מדיטציה 10 דקות

**בלוקים קבועים שלא זזים לעולם:**
- סשן מסחר יורו שני עד שישי 09:00-11:00
- מענה ראשון לתלמידים ראשון עד חמישי — ראשון מ11:30, שאר הימים מ11:00. משך שעה וחצי
- מענה שני לתלמידים ראשון עד חמישי 16:30-18:00
- וולט רביעי וחמישי 19:00-23:00
- וולט שבת 18:00-23:00
- שיעור מסחר פרונטלי עם שחף — שעה אחת, חמישי 18:00-19:00 בעדיפות ראשונה, אם יש התנגשות קבע ביום אחר באותו שבוע
- ראשון 13:00-14:00 נסיעה לאופיס ועבודה מהמשרד

**כללי אימון גוף:**
- 3 פעמים בשבוע
- ראשון 09:00-11:30 כולל מקלחת
- שאר הימים 12:00-14:00 בלבד, לא בזמן מסחר ולא בשעות עומס

**כללי סשן עם תמיר מפיק:**
- פעם בשבוע, יום שני עד חמישי, 14:00-18:30
- בחר את היום הכי פנוי ועם הכי פחות משימות כבדות באותו שבוע
- ביום הסשן — יום קל בלבד לפני ואחרי
- יציאה מהבית ב11:00 לתחבורה ציבורית למודיעין
- מענה ראשון תוך כדי הליכה
- אין ארוחת צהריים קבועה באותו יום
- מענה שני בדרך חזרה 18:30-20:00
- חדר כושר בתל אביב אחרי החזרה 20:00-22:00

**כללי ארוחות:**
- ארוחת צהריים 12:30-13:00 בימים ראשון, שני, רביעי, חמישי, שישי
- ביום הסשן עם תמיר — אין ארוחת צהריים קבועה

**כללי קריאה:**
- פעם אחת בלבד ביום, 30 דקות
- פזר על פני כל ימות השבוע
- לא לשבץ פעמיים באותו יום

**כללי כתיבת שירים:**
- פעמיים בשבוע בלבד
- 3 שעות רצופות כל פעם
- בערב בלבד
- אין פיצול בשום מקרה
- אם אין מספיק חלונות — פעם אחת בלבד, 3 שעות רצופות

**כללי הופעת רחוב ושיעור ריקוד:**
- מתחלפים כל שבוע — שבוע הופעת רחוב, שבוע שיעור ריקוד
- הופעת רחוב — שישי או שבת, לא אחרי 16:00 בשישי בגלל קבלת שבת
- שיעור ריקוד עם שירן — שישי 15:30, רמת גן, פעם בשבועיים

**שבת:**
- 08:30-09:00 ארוחת בוקר + מדיטציה
- 09:00-10:30 בישול לשבוע
- עד 11:00 שיחת משפחה
- עד 11:30 תכנון לוח זמנים לשבוע הבא
- 11:30-13:00 יצירת תוכן
- 13:00-13:30 ארוחת צהריים
- 13:30-17:00 יצירת תוכן המשך
- 18:00-23:00 וולט

**כללי אנרגיה:**
- 🟢 ירוק = אנרגיה גבוהה וחיובית — משימות יצירתיות הדורשות ריכוז
- 🟡 צהוב = אנרגיה נמוכה וחיובית — משימות קלות הדורשות קצת רצון
- 🔴 אדום = אנרגיה נמוכה ושלילית — מטלות אדמין בלבד

**אל תיצור התנגשויות. אל תפצל משימות שצריכות להיות רצופות. מלא את כל החלונות הפנויים במשימות החוזרות לפי אנרגיה וזמן מועדף.**"""


def get_current_time_info():
    israel_tz = pytz.timezone("Asia/Jerusalem")
    now = datetime.now(israel_tz)
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


# Generic Notion call for create / patch (used by the /schedule flow).
async def notion_request(method, path, body=None):
    url = f"https://api.notion.com/v1/{path}"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, url, headers=headers, json=body)
            return response.json()
    except Exception as e:
        print(f"Notion request error ({method} {path}): {e}")
        return {}


# ---- small property readers ----
def _title(props, key):
    arr = props.get(key, {}).get("title", [])
    return arr[0].get("text", {}).get("content", "") if arr else ""

def _select(props, key):
    v = props.get(key, {}).get("select")
    return v.get("name", "") if v else ""

def _multi(props, key):
    return [o.get("name", "") for o in props.get(key, {}).get("multi_select", [])]

def _rtext(props, key):
    arr = props.get(key, {}).get("rich_text", [])
    return arr[0].get("text", {}).get("content", "") if arr else ""


async def get_inbox_tasks():
    """Used by the energy-suggestion feature (name + energy only)."""
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
        name = _title(props, "שם")
        energy = _select(props, "אנרגיה")
        if name:
            tasks.append({"name": name, "energy": energy})
    return tasks


async def get_recurring_tasks():
    """Used by the energy-suggestion feature."""
    data = await get_notion_data(RECURRING_TASKS_DB)
    if not data:
        return []
    tasks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = _title(props, "Name") or _title(props, "שם")
        energy = _select(props, "אנרגיה")
        preferred_time = _rtext(props, "זמן מועדף")
        if name:
            tasks.append({"name": name, "energy": energy, "preferred_time": preferred_time})
    return tasks


# ---- richer fetchers for the weekly schedule generator ----
async def get_inbox_tasks_full():
    """Inbox tasks WITH page ids + all scheduling-relevant fields."""
    data = await get_notion_data(TASK_INBOX_DB, {
        "filter": {"property": "סטטוס", "select": {"equals": "אינבוקס"}}
    })
    if not data:
        return []
    tasks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = _title(props, "שם")
        if not name:
            continue
        tasks.append({
            "id": page["id"],
            "name": name,
            "energy": _select(props, "אנרגיה"),
            "category": _select(props, "קטגוריה"),
            "priority": _select(props, "Priority"),
            "type": _select(props, "סוג"),
            "preferred_time": _rtext(props, "זמן מועדף"),
            "days": _multi(props, "יום"),
        })
    return tasks


async def get_recurring_tasks_full():
    data = await get_notion_data(RECURRING_TASKS_DB)
    if not data:
        return []
    tasks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = _title(props, "Name") or _title(props, "שם")
        if not name:
            continue
        tasks.append({
            "name": name,
            "energy": _select(props, "אנרגיה"),
            "frequency": _select(props, "תדירות"),
            "block_type": _select(props, "סוג בלוק"),
            "preferred_time": _rtext(props, "זמן מועדף"),
            "days": _multi(props, "יום מועדף"),
        })
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

    prompt = f"""אתה עוזר אישי של עידו, מנטור מסחר ומוזיקאי בן 25 מתל אביב. עידו מנגן בס, לא גיטרה.

השעה עכשיו: {time_info['time']} ביום {time_info['day']}
מצב אנרגיה: {energy_desc}

משימות באינבוקס:
{inbox_text}

משימות חוזרות:
{recurring_text}

תן לעידו 3-4 משימות מתאימות לעכשיו לפי האנרגיה והשעה. כתוב בעברית, קצר וישיר."""

    message = claude.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ================= WEEKLY SCHEDULE GENERATION =================

def build_schedule_prompt(recurring, inbox, exceptions):
    rec_lines = []
    for t in recurring:
        days = ", ".join(t["days"]) if t["days"] else "גמיש"
        rec_lines.append(
            f"- {t['name']} | אנרגיה: {t['energy']} | תדירות: {t['frequency']} | "
            f"יום מועדף: {days} | זמן מועדף: {t['preferred_time'] or 'גמיש'} | סוג: {t['block_type']}"
        )
    rec_text = "\n".join(rec_lines) if rec_lines else "אין משימות חוזרות"

    inbox_lines = []
    for t in inbox:
        days = ", ".join(t["days"]) if t["days"] else "גמיש"
        inbox_lines.append(
            f"- [id:{t['id']}] {t['name']} | אנרגיה: {t['energy']} | קטגוריה: {t['category']} | "
            f"עדיפות: {t['priority']} | יום: {days} | זמן מועדף: {t['preferred_time'] or 'גמיש'}"
        )
    inbox_text = "\n".join(inbox_lines) if inbox_lines else "אין משימות חדשות באינבוקס"

    exc = exceptions.strip() if (exceptions and exceptions.strip()) else "אין חריגים מיוחדים השבוע"

    return f"""{MASTER_RULES}

---
המשימות החוזרות מהטבלה (שבץ אותן בחלונות הפנויים לפי אנרגיה, יום מועדף, זמן מועדף ותדירות):
{rec_text}

---
משימות חדשות מהאינבוקס שצריך לשבץ השבוע (כל אחת עם מזהה id):
{inbox_text}

---
החריגים והאירועים החד-פעמיים של השבוע הזה:
{exc}

---
החזר אך ורק JSON תקין. בלי טקסט נוסף, בלי הסברים, בלי markdown, בלי backticks.
מבנה מדויק:
{{
  "schedule": [
    {{"day": "ראשון", "blocks": [
        {{"start": "07:30", "end": "08:00", "name": "שם הבלוק", "energy": "🟢", "type": "קבוע"}}
    ]}}
  ],
  "scheduled_inbox_ids": ["<ה-id של כל משימת אינבוקס ששובצה בפועל>"]
}}

כלול את כל שבעת הימים לפי הסדר: ראשון, שני, שלישי, רביעי, חמישי, שישי, שבת.
ב-scheduled_inbox_ids כלול אך ורק את ה-id-ים של משימות האינבוקס ששיבצת בפועל בלוח, בדיוק כפי שקיבלת אותם."""


def generate_schedule_json(prompt):
    """Synchronous Claude call -> parsed dict. Run via asyncio.to_thread."""
    message = claude.messages.create(
        model=SCHEDULE_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    # Slice to the JSON object in case of stray text.
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


def schedule_to_blocks(schedule):
    """Turn the schedule JSON into Notion block objects, ordered by day."""
    blocks = []
    by_day = {d.get("day"): d.get("blocks", []) for d in schedule}
    for day in DAY_ORDER:
        day_blocks = by_day.get(day)
        if not day_blocks:
            continue
        blocks.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": day}}]}
        })
        for b in day_blocks:
            line = f"{b.get('start', '')}–{b.get('end', '')}  {b.get('name', '')}  {b.get('energy', '')}".strip()
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line}}]}
            })
    return blocks


async def create_schedule_page(title, blocks):
    page = await notion_request("POST", "pages", {
        "parent": {"type": "page_id", "page_id": WEEKLY_SCHEDULES_PARENT},
        "properties": {"title": {"title": [{"text": {"content": title}}]}}
    })
    page_id = page.get("id")
    if not page_id:
        print(f"Page creation failed: {page}")
        return None, None
    # Notion accepts max 100 children per call; chunk to be safe.
    for i in range(0, len(blocks), 90):
        await notion_request("PATCH", f"blocks/{page_id}/children", {"children": blocks[i:i + 90]})
    return page_id, page.get("url", "")


async def archive_page(page_id):
    await notion_request("PATCH", f"pages/{page_id}", {"archived": True})


async def mark_scheduled(page_id):
    await notion_request("PATCH", f"pages/{page_id}", {
        "properties": {"סטטוס": {"select": {"name": "מתוזמן"}}}
    })


async def generate_and_post(chat_id, context, exceptions):
    """Shared by /schedule and the 🔄 regenerate button."""
    # If a previous unapproved draft exists, archive it so drafts don't pile up.
    prev = context.user_data.get("draft_page_id")
    if prev:
        try:
            await archive_page(prev)
        except Exception as e:
            print(f"archive error: {e}")
        context.user_data["draft_page_id"] = None

    recurring = await get_recurring_tasks_full()
    inbox = await get_inbox_tasks_full()
    prompt = build_schedule_prompt(recurring, inbox, exceptions)

    try:
        result = await asyncio.to_thread(generate_schedule_json, prompt)
    except Exception as e:
        print(f"generation error: {e}")
        await context.bot.send_message(chat_id, "הבנייה נכשלה (שגיאת JSON או מודל). נסה שוב עם /schedule.")
        return

    schedule = result.get("schedule", [])
    ids = result.get("scheduled_inbox_ids", [])

    israel_tz = pytz.timezone("Asia/Jerusalem")
    title = "לוז שבועי – " + datetime.now(israel_tz).strftime("%d/%m/%Y")
    blocks = schedule_to_blocks(schedule)

    page_id, url = await create_schedule_page(title, blocks)
    if not page_id:
        await context.bot.send_message(
            chat_id,
            "יצירת הדף בנוטיון נכשלה. ודא ש-WEEKLY_SCHEDULES_PARENT נכון, ושחיברת את ה-integration של הבוט לדף."
        )
        return

    context.user_data["draft_page_id"] = page_id
    context.user_data["pending_inbox_ids"] = ids
    context.user_data["exceptions"] = exceptions

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ אשר", callback_data="approve_schedule"),
        InlineKeyboardButton("🔄 צור מחדש", callback_data="regen_schedule"),
    ]])
    await context.bot.send_message(
        chat_id,
        f"הלוח מוכן 📅\n{url}\n\nשובצו {len(ids)} משימות מהאינבוקס. לאשר?",
        reply_markup=keyboard
    )


async def schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "בוא נבנה את הלוז לשבוע הבא 📅\n"
        "כתוב לי את החריגים של השבוע — אירועים חד-פעמיים, שינויים, ומה פעיל השבוע "
        "(הופעת רחוב / שיעור ריקוד).\n"
        'אם אין חריגים, כתוב "אין".'
    )
    return SCHEDULE_EXCEPTIONS


async def schedule_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exceptions = update.message.text or ""
    if exceptions.strip() in ("אין", "-", "אין חריגים", " אין"):
        exceptions = ""
    await update.message.reply_text("רגע, בונה את הלוח... (יכול לקחת חצי דקה)")
    await generate_and_post(update.effective_chat.id, context, exceptions)
    return ConversationHandler.END


async def handle_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "approve_schedule":
        ids = context.user_data.get("pending_inbox_ids", [])
        ok = 0
        for pid in ids:
            try:
                await mark_scheduled(pid)
                ok += 1
            except Exception as e:
                print(f"mark error {pid}: {e}")
        context.user_data["draft_page_id"] = None  # approved -> keep the page
        await query.edit_message_text(
            f'אושר ✅\n{ok} משימות סומנו כ"מתוזמן" (האוטומציה תהפוך אותן ל"גמור").'
        )
    elif query.data == "regen_schedule":
        await query.edit_message_text("בונה מחדש... 🔄")
        exceptions = context.user_data.get("exceptions", "")
        await generate_and_post(query.message.chat_id, context, exceptions)


# ================= EXISTING FEATURES =================

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

    energy_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={ENERGY_CHECK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_energy)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    schedule_conv = ConversationHandler(
        entry_points=[CommandHandler("schedule", schedule_start)],
        states={SCHEDULE_EXCEPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_generate)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(energy_conv)
    app.add_handler(schedule_conv)
    app.add_handler(CallbackQueryHandler(handle_schedule_callback))
    app.add_handler(CommandHandler("inbox", inbox_command))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()