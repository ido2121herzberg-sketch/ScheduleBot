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

# Models: strong model for the weekly schedule + repairs, fast/cheap model for parsing input.
SCHEDULE_MODEL = "claude-sonnet-4-6"
PARSE_MODEL = "claude-haiku-4-5"

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ENERGY_CHECK = 1
SCHEDULE_EXCEPTIONS = 2   # waiting for the user's raw exceptions text
SCHEDULE_CONFIRM = 3      # waiting for "כן" or a correction

DAY_ORDER = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
SKIP_WORDS = {"אין", "-", "אין חריגים", "ללא", "כלום"}
YES_WORDS = {"כן", "כן.", "yes", "אישור", "מאשר", "מאשרת", "✅", "כ", "אוקיי", "אוקי"}

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

**חוקי ברזל: אל תיצור התנגשויות — שני בלוקים לעולם לא חופפים באותה שעה. אל תפצל משימות שצריכות להיות רצופות. אל תשבץ שום דבר בתוך בלוק קבוע (מסחר, וולט). מלא את כל החלונות הפנויים במשימות החוזרות לפי אנרגיה וזמן מועדף.**"""


# ===================== TIME / NOTION HELPERS =====================

def get_current_time_info():
    israel_tz = pytz.timezone("Asia/Jerusalem")
    now = datetime.now(israel_tz)
    days = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
    return {"time": now.strftime("%H:%M"), "day": days[now.weekday()]}


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
    data = await get_notion_data(TASK_INBOX_DB, {
        "filter": {"property": "סטטוס", "select": {"equals": "אינבוקס"}}
    })
    if not data:
        return []
    tasks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = _title(props, "שם")
        if name:
            tasks.append({"name": name, "energy": _select(props, "אנרגיה")})
    return tasks


async def get_recurring_tasks():
    data = await get_notion_data(RECURRING_TASKS_DB)
    if not data:
        return []
    tasks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = _title(props, "Name") or _title(props, "שם")
        if name:
            tasks.append({
                "name": name,
                "energy": _select(props, "אנרגיה"),
                "preferred_time": _rtext(props, "זמן מועדף"),
            })
    return tasks


async def get_inbox_tasks_full():
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


# ===================== ENERGY SUGGESTION (existing feature) =====================

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
        model=PARSE_MODEL, max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ===================== INPUT PARSING (the "secretary" layer) =====================

def _claude_json(model, prompt, max_tokens=4000):
    """Call Claude and parse a JSON object out of the reply. Sync; run via to_thread."""
    msg = claude.messages.create(
        model=model, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e != -1:
        raw = raw[s:e + 1]
    return json.loads(raw)


def parse_exceptions(text):
    prompt = f"""אתה מנתח קלט עבור עוזר אישי. המשתמש כתב את החריגים והאירועים שלו לשבוע הקרוב.
פרק כל אירוע לרשומה מובנית. החזר אך ורק JSON בפורמט הזה:
{{"events":[{{"name":"שם האירוע","days":["שלישי"],"time":"16:00","recurring":false,"energy":"","priority":"","duration_min":null}}]}}

כללים:
- days: רשימת ימים בעברית (ראשון..שבת). אם נאמר "כל יום" שים ["כל יום"]. אם לא צוין יום, השאר [].
- time: שעה בפורמט HH:MM אם צוינה, אחרת "גמיש".
- recurring: true אם זה חוזר (כל יום/כל שבוע), אחרת false.
- energy: "🟢"/"🟡"/"🔴" רק אם המשתמש רמז לכך, אחרת "".
- priority: "דחוף"/"רגיל" אם נרמז, אחרת "".
- duration_min: מספר דקות אם צוין, אחרת null.
- אל תמציא פרטים שלא נאמרו. אל תוסיף אירועים שלא הוזכרו.
בלי טקסט נוסף, בלי הסברים, בלי markdown.

הקלט של המשתמש:
{text}"""
    data = _claude_json(PARSE_MODEL, prompt, max_tokens=1500)
    return data.get("events", [])


def reparse_with_correction(events, correction):
    prompt = f"""להלן פירוש קודם של אירועי השבוע (JSON) ותיקון שהמשתמש כתב. עדכן את הרשימה לפי התיקון.
פירוש קודם:
{json.dumps({"events": events}, ensure_ascii=False)}

התיקון של המשתמש:
{correction}

החזר אך ורק JSON באותו פורמט {{"events":[...]}}, בלי טקסט נוסף, בלי markdown."""
    data = _claude_json(PARSE_MODEL, prompt, max_tokens=1500)
    return data.get("events", events)


def build_readback(events):
    if not events:
        return "לא זיהיתי אירועים מיוחדים השבוע."
    lines = ["הבנתי ככה 👇"]
    for e in events:
        days_list = e.get("days") or []
        if "כל יום" in days_list:
            days = "כל יום"
        elif days_list:
            days = ", ".join(days_list)
        else:
            days = "יום גמיש"
        t = e.get("time") or "גמיש"
        kind = "חוזר" if e.get("recurring") else "חד-פעמי"
        extra = []
        if e.get("energy"):
            extra.append(f"אנרגיה {e['energy']}")
        if e.get("priority"):
            extra.append(e["priority"])
        if e.get("duration_min"):
            extra.append(f"{e['duration_min']} דק'")
        suffix = (" — " + ", ".join(extra)) if extra else ""
        lines.append(f"• {e.get('name','')}: {days}, {t}, {kind}{suffix}")
    return "\n".join(lines)


# ===================== SCHEDULE GENERATION + VALIDATION =====================

def events_to_text(events):
    if not events:
        return "אין חריגים מיוחדים השבוע"
    out = []
    for e in events:
        days_list = e.get("days") or []
        days = "כל יום" if "כל יום" in days_list else (", ".join(days_list) if days_list else "גמיש")
        out.append(
            f"- {e.get('name','')} | ימים: {days} | שעה: {e.get('time','גמיש')} | "
            f"{'חוזר' if e.get('recurring') else 'חד-פעמי'} | אנרגיה: {e.get('energy','') or '-'} | "
            f"עדיפות: {e.get('priority','') or '-'} | משך: {e.get('duration_min') or '-'}"
        )
    return "\n".join(out)


def build_schedule_prompt(recurring, inbox, events):
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

    return f"""{MASTER_RULES}

---
המשימות החוזרות מהטבלה (שבץ לפי אנרגיה, יום, זמן מועדף ותדירות):
{rec_text}

---
משימות חדשות מהאינבוקס לשיבוץ השבוע (כל אחת עם מזהה id):
{inbox_text}

---
החריגים והאירועים החד-פעמיים של השבוע (כבר מנותחים ומאושרים על ידי המשתמש — שבץ אותם בדיוק לפי היום והשעה שצוינו):
{events_to_text(events)}

---
החזר אך ורק JSON תקין. בלי טקסט נוסף, בלי markdown, בלי backticks. מבנה מדויק:
{{
  "schedule": [
    {{"day": "ראשון", "blocks": [
        {{"start": "07:30", "end": "08:00", "name": "שם הבלוק", "energy": "🟢", "type": "קבוע"}}
    ]}}
  ],
  "scheduled_inbox_ids": ["<id של כל משימת אינבוקס ששובצה בפועל>"]
}}

כלול את כל שבעת הימים לפי הסדר: ראשון, שני, שלישי, רביעי, חמישי, שישי, שבת.
ב-scheduled_inbox_ids כלול אך ורק את ה-id-ים של משימות האינבוקס ששיבצת בפועל, בדיוק כפי שקיבלת."""


def generate_schedule_json(prompt):
    msg = claude.messages.create(
        model=SCHEDULE_MODEL, max_tokens=8000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip().replace("```json", "").replace("```", "").strip()
    s, e = raw.find("{"), raw.rfind("}")
    if s != -1 and e != -1:
        raw = raw[s:e + 1]
    return json.loads(raw)


def _to_min(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None

def _to_hhmm(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}"


def validate_schedule(schedule):
    """Deterministic rule checks. Returns a list of violation strings (empty = clean)."""
    violations = []
    for day in schedule:
        day_name = day.get("day", "")
        parsed = []
        for b in day.get("blocks", []):
            st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
            if st is None or en is None:
                continue
            parsed.append((st, en, b.get("name", "")))
        parsed.sort()
        for i in range(1, len(parsed)):
            if parsed[i][0] < parsed[i - 1][1]:
                violations.append(
                    f"יום {day_name}: חפיפה בין '{parsed[i-1][2]}' ל-'{parsed[i][2]}' סביב {_to_hhmm(parsed[i][0])}"
                )

    # Songwriting must be 3 continuous hours (match 'כתיבת שיר' so it won't catch 'שירן').
    for day in schedule:
        for b in day.get("blocks", []):
            if "כתיבת שיר" in b.get("name", ""):
                st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
                if st is not None and en is not None and (en - st) < 180:
                    violations.append(
                        f"יום {day.get('day','')}: 'כתיבת שירים' חייב 3 שעות רצופות (180 דק'), הופיע {en-st} דק'"
                    )
    return violations


def build_repair_prompt(schedule, violations):
    return f"""להלן לוח שבועי בפורמט JSON שיצרת:
{json.dumps(schedule, ensure_ascii=False)}

נמצאו הבעיות הבאות שחייבות תיקון:
{chr(10).join('- ' + v for v in violations)}

תקן אך ורק את הבעיות האלה. אל תשנה שום דבר אחר בלוח — אותם בלוקים, אותם זמנים, פרט למקומות שצריך לתקן.
החזר JSON מלא ותקין באותו מבנה בדיוק: {{"schedule":[...], "scheduled_inbox_ids":[...]}}. בלי טקסט נוסף, בלי markdown."""


# ===================== NOTION PAGE OUTPUT =====================

def schedule_to_blocks(schedule):
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
            line = f"{b.get('start','')}–{b.get('end','')}  {b.get('name','')}  {b.get('energy','')}".strip()
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
    for i in range(0, len(blocks), 90):
        await notion_request("PATCH", f"blocks/{page_id}/children", {"children": blocks[i:i + 90]})
    return page_id, page.get("url", "")


async def archive_page(page_id):
    await notion_request("PATCH", f"pages/{page_id}", {"archived": True})


async def mark_scheduled(page_id):
    await notion_request("PATCH", f"pages/{page_id}", {
        "properties": {"סטטוס": {"select": {"name": "מתוזמן"}}}
    })


# ===================== ORCHESTRATION =====================

async def generate_and_post(chat_id, context):
    events = context.user_data.get("parsed_events", [])

    prev = context.user_data.get("draft_page_id")
    if prev:
        try:
            await archive_page(prev)
        except Exception as e:
            print(f"archive error: {e}")
        context.user_data["draft_page_id"] = None

    recurring = await get_recurring_tasks_full()
    inbox = await get_inbox_tasks_full()
    prompt = build_schedule_prompt(recurring, inbox, events)

    try:
        result = await asyncio.to_thread(generate_schedule_json, prompt)
    except Exception as e:
        print(f"generation error: {e}")
        await context.bot.send_message(chat_id, "הבנייה נכשלה (שגיאת JSON או מודל). נסה שוב עם /schedule.")
        return

    schedule = result.get("schedule", [])
    ids = result.get("scheduled_inbox_ids", [])

    # Silent validation + auto-repair, up to 3 passes.
    for _ in range(3):
        violations = validate_schedule(schedule)
        if not violations:
            break
        try:
            repaired = await asyncio.to_thread(generate_schedule_json, build_repair_prompt(schedule, violations))
            schedule = repaired.get("schedule", schedule)
            if repaired.get("scheduled_inbox_ids"):
                ids = repaired.get("scheduled_inbox_ids")
        except Exception as e:
            print(f"repair error: {e}")
            break

    remaining = validate_schedule(schedule)

    israel_tz = pytz.timezone("Asia/Jerusalem")
    title = "לוז שבועי – " + datetime.now(israel_tz).strftime("%d/%m/%Y")
    page_id, url = await create_schedule_page(title, schedule_to_blocks(schedule))
    if not page_id:
        await context.bot.send_message(
            chat_id,
            "יצירת הדף בנוטיון נכשלה. ודא ש-WEEKLY_SCHEDULES_PARENT נכון ושה-integration של הבוט מחובר לדף."
        )
        return

    context.user_data["draft_page_id"] = page_id
    context.user_data["pending_inbox_ids"] = ids

    msg = f"הלוח מוכן 📅\n{url}\n\nשובצו {len(ids)} משימות מהאינבוקס. לאשר?"
    if remaining:
        msg += "\n\n⚠️ לא הצלחתי לתקן לבד:\n" + "\n".join("• " + v for v in remaining)

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ אשר", callback_data="approve_schedule"),
        InlineKeyboardButton("🔄 צור מחדש", callback_data="regen_schedule"),
    ]])
    await context.bot.send_message(chat_id, msg, reply_markup=keyboard)


# ===================== SCHEDULE CONVERSATION =====================

async def schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "בוא נבנה את הלוז לשבוע הבא 📅\n"
        "כתוב לי את החריגים של השבוע — אירועים חד-פעמיים, שינויים, ומה פעיל השבוע "
        "(הופעת רחוב / שיעור ריקוד).\n"
        'אם אין חריגים, כתוב "אין".'
    )
    return SCHEDULE_EXCEPTIONS


async def schedule_exceptions_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in SKIP_WORDS:
        context.user_data["parsed_events"] = []
        await update.message.reply_text("אין חריגים. בונה את הלוח... (יכול לקחת חצי דקה)")
        await generate_and_post(update.effective_chat.id, context)
        return ConversationHandler.END

    await update.message.reply_text("רגע, מנתח את מה שכתבת...")
    try:
        events = await asyncio.to_thread(parse_exceptions, text)
    except Exception as e:
        print(f"parse error: {e}")
        events = [{"name": text, "days": [], "time": "גמיש", "recurring": False,
                   "energy": "", "priority": "", "duration_min": None}]
    context.user_data["parsed_events"] = events
    await update.message.reply_text(
        build_readback(events) + "\n\nנכון? כתוב \"כן\" לאישור, או תקן אותי במילים שלך."
    )
    return SCHEDULE_CONFIRM


async def schedule_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in YES_WORDS:
        await update.message.reply_text("מעולה, בונה את הלוח... (יכול לקחת חצי דקה)")
        await generate_and_post(update.effective_chat.id, context)
        return ConversationHandler.END

    await update.message.reply_text("רגע, מעדכן...")
    prev = context.user_data.get("parsed_events", [])
    try:
        events = await asyncio.to_thread(reparse_with_correction, prev, text)
    except Exception as e:
        print(f"reparse error: {e}")
        events = prev
    context.user_data["parsed_events"] = events
    await update.message.reply_text(
        build_readback(events) + "\n\nנכון עכשיו? \"כן\" לאישור, או תקן שוב."
    )
    return SCHEDULE_CONFIRM


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
        context.user_data["draft_page_id"] = None
        await query.edit_message_text(
            f'אושר ✅\n{ok} משימות סומנו כ"מתוזמן" (האוטומציה תהפוך אותן ל"גמור").'
        )
    elif query.data == "regen_schedule":
        await query.edit_message_text("בונה מחדש... 🔄")
        await generate_and_post(query.message.chat_id, context)


# ===================== EXISTING FEATURES =====================

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
        states={
            SCHEDULE_EXCEPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_exceptions_received)],
            SCHEDULE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_confirm)],
        },
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