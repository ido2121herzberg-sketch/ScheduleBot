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
FIXED_BLOCKS_DB = "ca022797f1844cb79c76be05fae5e073"  # בלוקים קבועים

SCHEDULE_MODEL = "claude-sonnet-4-6"
PARSE_MODEL = "claude-haiku-4-5"

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ENERGY_CHECK = 1
SCHEDULE_EXCEPTIONS = 2
SCHEDULE_CONFIRM = 3
TIME_CHECK = 4  # /start: how much free time the user has, after picking energy

DAY_ORDER = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
WEEKDAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי"]
SKIP_WORDS = {"אין", "-", "אין חריגים", "ללא", "כלום"}
YES_WORDS = {"כן", "כן.", "yes", "אישור", "מאשר", "מאשרת", "✅", "אוקיי", "אוקי"}

# FLEXIBLE / logic rules. Fixed blocks come from the בלוקים קבועים database.
FLEXIBLE_RULES = """אתה בונה לוז שבועי לעידו. הנתונים — בלוקים קבועים, שגרות חוזרות ואירועי השבוע — ניתנים לך בנפרד והם מקור האמת לשמות, ימים, שעות ומשכים. הכללים כאן הם עקרונות היגיון בלבד, לא שעות קשיחות. אל תמציא שעות; קח אותן מהנתונים.

== סדר עדיפויות — החוק המרכזי ==
כששני דברים רוצים את אותו זמן, מה שבעדיפות נמוכה יותר זז או מוותר. לעולם לא חופפים, לעולם לא דוחסים, לעולם לא מפצלים אירוע.
1. בלוקים קבועים מהשלד (רוטינת בוקר, תפילה, מסחר, ארוחות, נסיעה לאופיס + עבודה) — לא זזים ולא מתקצרים.
2. אירועים חד-פעמיים עם יום ושעה (חתונה, מסיבה, פגישה) — לא זזים ליום אחר, לא מתפצלים. אירוע כזה גובר על שגרות וגם על וולט: ביום שיש אירוע, מותר ונכון שוולט או שגרה פשוט לא יקרו באותו יום — אל תנסה לדחוס אותם בכל זאת. הוסף בלוק "נסיעה" לפני אירוע ערב כשצריך.
3. שגרות חוזרות — שבץ לפי התדירות, אבל הן מוותרות לעדיפות 1 ו-2: אם אין מקום ביום מסוים, הזז ליום אחר; אם אין בכלל מקום בשבוע, ותר על המופע ודווח. לעולם אל תחפוף שגרה על בלוק קבוע או אירוע.
4. משימות אינבוקס — ממלאות חלונות פתוחים בלבד, לפי בחירת המשתמש בזמן אמת.

== חוקי-על ==
- שני בלוקים אמיתיים (לא מיקרו / לא parallel) לעולם לא חופפים.
- אירוע (עדיפות 2) הוא בלוק יחיד ורצוף. לעולם אל תפצל אותו — גם לא בשביל ארוחה או שגרה. אם ארוחה נופלת בתוך אירוע, הארוחה זזה או מדלגת באותו יום.
- שגרה עם משך מוגדר (יצירת תוכן, כתיבת שירים, סונו וכו') = בלוק רצוף אחד באורך המלא. לעולם אל תפצל לחתיכות של חצי שעה. אסור 'חלק א/ב' כריפוד.
- כל השעות מעוגלות ל-:00 או :30. לעולם לא 23:59. אם לאירוע אין שעת סיום — משך ברירת מחדל עגול לפי הסוג (אירוע ערב כמו חתונה = 4 שעות).
- שום דבר לא מתוזמן אחרי 23:30 — זו שעת השינה.
- נסיעה היא בלוק יחיד עם משך עגול. אל תפצל ל'הליכה'+'נסיעה' ואל תמציא אמצעי תחבורה או משכי-ביניים.

== עקרונות חכמים ==
- **מיקום — מתי עידו מחוץ לבית:** רק בפעילויות האלה הוא לא בבית: עבודה במשרד (ראשון), וולט, סשן עם תמיר, שיעור ריקוד, שיעור הרב יגאל, וחדר כושר. בכל זמן אחר הוא בבית. בזמן שהוא מחוץ לבית — אסור לשבץ מוזיקה (נגינה, אימון על שירים, כתיבת שירים) או עבודה ממוקדת מהבית. במשרד שבץ רק עבודה. אם המשתמש מציין בחריגים שהוא בחוץ בזמן נוסף — התחשב בזה.
- **זמני מעבר:** לכל פעילות מחוץ לבית יש נסיעה. השאר בלוק "נסיעה" קצר לפניה ואחריה — אל תניח שעידו מתחיל את המשימה הבאה ברגע שהקודמת נגמרה.
- **משימות בדרך:** משימות שאפשר לעשות תוך כדי נסיעה בתחבורה ציבורית (מענה לתלמידים, קריאה, שיחות) — שבץ אותן בתוך זמן הנסיעה עם "parallel": true במקום לבזבז את הזמן. זו לא חפיפה.
- התאמה לשעת היום: אל תשבץ עבודה יצירתית תובענית (תוכן, כתיבת שירים, נגינה) אחרי 22:00 — עדיף בוקר או צהריים.
- משימות מיקרו (לשלוח הודעה, עדכון קצר) = 2-5 דקות, "parallel": true, מוצמדות לבלוק סמוך. לעולם לא בלוק ייעודי של חצי שעה.
- בלי פיצול שגרות: כל מופע הוא בלוק רצוף אחד באורך המלא.

== יום הסשן עם תמיר מפיק (לוגיקה מיוחדת) ==
- פעם בשבוע, שני עד חמישי. בחר את היום הקל ביותר. יום קל בלבד — בלי משימות כבדות לפני ואחרי.
- יציאה מהבית ב-11:00. הנסיעה למודיעין = בלוק יחיד "נסיעה למודיעין".
- 'מענה ראשון' מתבצע תוך כדי הנסיעה — "parallel": true, באותו משך כרגיל.
- מענה שני בדרך חזרה; חדר כושר בתל אביב בערב נחשב כאחד מימי הכושר.

== הופעת רחוב / שיעור ריקוד (פעם בשבועיים, מתחלפים) ==
- פעילים רק אם המשתמש ציין בחריגים שזה השבוע. הופעת רחוב — שישי/שבת, לא אחרי 16:00 בשישי.

== חלונות פתוחים ואנרגיה ==
- 🟢 גבוהה (יצירתי/ריכוז), 🟡 קל, 🔴 אדמין בלבד.
- אל תמלא זמן פנוי במשימות אינבוקס. כל זמן פנוי שנשאר אחרי הכל — בלוק "חלון פתוח" עם "type": "חלון פתוח" וסיווג אנרגיה לפי שעת היום. המשתמש ימלא אותו בזמן אמת."""


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
            "importance": _select(props, "חשיבות"),
            "preferred_time": _rtext(props, "זמן מועדף"),
            "days": _multi(props, "יום מועדף"),
        })
    return tasks


async def get_fixed_blocks():
    """The immutable skeleton, read from the בלוקים קבועים database."""
    data = await get_notion_data(FIXED_BLOCKS_DB)
    if not data:
        return []
    blocks = []
    for page in data.get("results", []):
        props = page["properties"]
        name = _title(props, "שם")
        if not name:
            continue
        blocks.append({
            "name": name,
            "days": _multi(props, "ימים"),
            "start": _rtext(props, "שעת התחלה"),
            "end": _rtext(props, "שעת סיום"),
            "energy": _select(props, "אנרגיה"),
        })
    return blocks


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
- **קריטי — יום מפורש:** אם המשתמש ציין יום מפורש (למשל "ביום רביעי", "ברביעי", "מחר", "ביום שלישי") — קבע בדיוק את אותו יום. לעולם אל תשנה את היום, אל תנחש יום אחר, ואל תעביר ליום סמוך. טעות ביום היא הטעות החמורה ביותר.
- time: שעה בפורמט HH:MM אם צוינה, אחרת "גמיש". עגל ל-:00 או :30. אל תשתמש לעולם ב-23:59.
- **שם האירוע = בדיוק המילים שהמשתמש כתב, בעברית. אל תתרגם לאנגלית לעולם. אל תקצר, אל תפרש ואל תהפוך שם לתיאור.** שמות מקומות/אירועים נשמרים מילה-במילה. למשל "ערב לא ברור" הוא ערב בפאב ששמו "לא ברור" — שם האירוע הוא "ערב לא ברור" במלואו (לא "ערב", לא "unclear").
- כל אירוע נפרד = רשומה נפרדת. לעולם אל תמזג שני אירועים לאחד, ולעולם אל תשמיט אירוע שהוזכר. שעה ששייכת לאירוע אחד לא עוברת לאירוע אחר.
- recurring: true אם זה חוזר, אחרת false.
- energy/priority: רק אם נרמז, אחרת "".
- duration_min: מספר דקות אם צוין, אחרת null.
- אל תמציא פרטים שלא נאמרו ואל תוסיף אירועים שלא הוזכרו.
בלי טקסט נוסף, בלי markdown.

הקלט של המשתמש:
{text}"""
    return _claude_json(SCHEDULE_MODEL, prompt, max_tokens=1500).get("events", [])


def reparse_with_correction(events, correction):
    prompt = f"""להלן פירוש קודם של אירועי השבוע (JSON) ותיקון שהמשתמש כתב. עדכן את הרשימה לפי התיקון.
פירוש קודם:
{json.dumps({"events": events}, ensure_ascii=False)}

התיקון של המשתמש:
{correction}

שמור על היום המפורש של כל אירוע בדיוק כפי שנקבע, אלא אם התיקון משנה אותו במפורש. לעולם אל תזיז אירוע ליום אחר על דעת עצמך.
החזר אך ורק JSON באותו פורמט {{"events":[...]}}, בלי טקסט נוסף, בלי markdown."""
    return _claude_json(PARSE_MODEL, prompt, max_tokens=1500).get("events", events)


def build_readback(events):
    if not events:
        return "לא זיהיתי אירועים מיוחדים השבוע."

    def is_dated(e):
        d = e.get("days") or []
        return (not e.get("recurring")) and d and "כל יום" not in d

    dated = [e for e in events if is_dated(e)]
    other = [e for e in events if not is_dated(e)]

    lines = ["הבנתי ככה 👇"]

    # Dated one-off events first and prominent, so a wrong day is impossible to miss.
    for e in dated:
        days = ", ".join(e.get("days") or [])
        t = e.get("time") or "גמיש"
        dur = f" ({e['duration_min']} דק')" if e.get("duration_min") else ""
        lines.append(f"📌 {e.get('name','')} — יום {days} בשעה {t}{dur}")

    for e in other:
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

    if dated:
        lines.append("\n⚠️ בדוק שהימים שמסומנים ב-📌 נכונים לפני שאתה מאשר.")
    return "\n".join(lines)


# ===================== SCHEDULE GENERATION =====================

def _to_min(hhmm):
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None

def _to_hhmm(mins):
    return f"{mins // 60:02d}:{mins % 60:02d}"


def skeleton_by_day(fixed_blocks):
    by_day = {d: [] for d in DAY_ORDER}
    for b in fixed_blocks:
        for d in b.get("days", []):
            if d in by_day:
                by_day[d].append(b)
    for d in by_day:
        by_day[d].sort(key=lambda x: _to_min(x.get("start", "")) or 0)
    return by_day


def skeleton_text(by_day):
    lines = []
    for d in DAY_ORDER:
        if not by_day[d]:
            continue
        lines.append(f"{d}:")
        for b in by_day[d]:
            lines.append(f"  {b['start']}–{b['end']} {b['name']} {b.get('energy','')}")
    return "\n".join(lines) if lines else "אין בלוקים קבועים"


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


def build_schedule_prompt(fixed_by_day, recurring, inbox, events):
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

    return f"""{FLEXIBLE_RULES}

---
בלוקים קבועים — חובה להעתיק אותם בדיוק לתוך הלוח, באותם ימים ושעות בדיוק. אסור לשנות, לקצר, לפצל או למחוק אותם:
{skeleton_text(fixed_by_day)}

---
משימות חוזרות (שגרות) — התחייבויות שבועיות. חובה לשבץ כל אחת לפי התדירות שלה, במשך ובחלון הזמן שכתובים בשדה 'זמן מועדף'. תן לכל בלוק בדיוק את השם מהרשימה (אל תקצר ואל תשנה):
{rec_text}

---
משימות מהאינבוקס (לעיון). שבץ מתוכן אך ורק את אלה שיש להן יום מפורש. שאר המשימות לא משובצות — המשתמש ימלא אותן בזמן אמת:
{inbox_text}

---
החריגים והאירועים של השבוע (מנותחים ומאושרים — שבץ בדיוק לפי היום והשעה; חובה שכולם יופיעו בלוח, כל אחד ביום שניתן לו):
{events_to_text(events)}

---
בנה לוז שבועי מלא לפי סדר העדיפויות:
1. העתק את כל הבלוקים הקבועים בדיוק (עדיפות 1).
2. שבץ כל אירוע ביום ובשעה שניתנו לו בדיוק (עדיפות 2). עוגן לא זז ליום אחר ולא מתפצל. אם אירוע מתנגש עם וולט או שגרה — האירוע מנצח, והוולט/שגרה פשוט לא קורים באותו יום (אל תדחוס ואל תקצר את הוולט מסביב). הוסף בלוק "נסיעה" לפני אירוע ערב כשצריך.
3. שבץ כל שגרה חוזרת לפי התדירות: 'יומי' = בכל יום מועדף; 'שבועי' = פעם; 'x2/x3 בשבוע' = פעמיים/שלוש בימים שונים; 'פעם בשבועיים' = רק אם צוין בחריגים. השתמש במשך ובחלון מ'זמן מועדף'. שגרה עם משך מוגדר = בלוק רצוף אחד באורך המלא, לעולם לא חתיכות של חצי שעה. אם אין מקום ביום בגלל עדיפות 1/2 — הזז ליום אחר, ואם אין בכלל — דלג ודווח. לעולם אל תחפוף.
4. מהאינבוקס שבץ אך ורק משימות עם יום מפורש. אל תדחוף משימות אינבוקס כלליות לזמן פנוי.
5. רק זמן פנוי אמיתי שנשאר (רצף של שעה ומעלה) — בלוק יחיד "חלון פתוח" עם "type": "חלון פתוח" וסיווג אנרגיה (🟢 בוקר, 🟡 אמצע יום, 🔴 ערב מאוחר). אל תיצור חלון קצר משעה ואל תיצור שני חלונות צמודים.
חוק-העל: שני בלוקים אמיתיים לעולם לא חופפים — מי שבעדיפות נמוכה זז או מוותר, אף פעם לא נדחס ואף פעם לא מפצל אירוע. משימות מיקרו (parallel) מותר שיחפפו.
שעות מעוגלות ל-:00/:30, שום דבר אחרי 23:30, אף פעם לא 23:59.
החזר אך ורק JSON תקין. בלי טקסט נוסף, בלי markdown. מבנה מדויק:
{{
  "schedule": [
    {{"day": "ראשון", "blocks": [
        {{"start": "07:30", "end": "08:00", "name": "שם הבלוק", "energy": "🟢", "type": "קבוע", "parallel": false}},
        {{"start": "16:00", "end": "17:00", "name": "חלון פתוח", "energy": "🟡", "type": "חלון פתוח", "parallel": false}}
    ]}}
  ],
  "scheduled_inbox_ids": ["<id של כל משימת אינבוקס עם יום מפורש ששובצה בפועל>"]
}}
כלול את כל שבעת הימים לפי הסדר: ראשון, שני, שלישי, רביעי, חמישי, שישי, שבת.
סמן "parallel": true רק למשימות מיקרו קצרות ולמענה ראשון ביום תמיר, אחרת false."""


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


def validate_schedule(schedule, fixed_by_day, events, recurring=None):
    violations = []
    out_by_day = {d.get("day"): d.get("blocks", []) for d in schedule}

    # 1. No overlaps between REAL blocks (parallel micro-tasks are allowed to overlap).
    for day in schedule:
        parsed = []
        for b in day.get("blocks", []):
            if b.get("parallel"):
                continue
            st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
            if st is None or en is None:
                continue
            parsed.append((st, en, b.get("name", "")))
        parsed.sort()
        for i in range(1, len(parsed)):
            if parsed[i][0] < parsed[i - 1][1]:
                violations.append(
                    f"יום {day.get('day','')}: חפיפה בין '{parsed[i-1][2]}' ל-'{parsed[i][2]}' סביב {_to_hhmm(parsed[i][0])}"
                )

    # 2. Every fixed block must appear unchanged — UNLESS a priority-2 event displaced it that day.
    event_words = []
    for e in (events or []):
        nm = (e.get("name") or "").strip()
        ws = [w for w in nm.split() if len(w) >= 3]
        if ws:
            event_words.append(ws)

    def event_block_on(day_name, fs, fe):
        """True if a scheduled event block overlaps [fs, fe] on this day."""
        for b in out_by_day.get(day_name, []):
            bn = b.get("name", "")
            if not any(all(w in bn for w in ws) for ws in event_words):
                continue
            bs, be = _to_min(b.get("start")), _to_min(b.get("end"))
            if bs is not None and be is not None and bs < fe and be > fs:
                return True
        return False

    for d in DAY_ORDER:
        for fb in fixed_by_day.get(d, []):
            fs, fe = _to_min(fb.get("start", "")), _to_min(fb.get("end", ""))
            found = any(
                _to_min(b.get("start")) == fs and _to_min(b.get("end")) == fe
                for b in out_by_day.get(d, [])
            )
            if not found and not event_block_on(d, fs, fe):
                violations.append(f"יום {d}: הבלוק הקבוע '{fb['name']}' ({fb['start']}–{fb['end']}) חסר או זז")

    # 3. מענה ראשון must be 90 minutes (prescriptive: state the exact corrected time).
    for day in schedule:
        if day.get("day") not in WEEKDAYS:
            continue
        for b in day.get("blocks", []):
            if "מענה ראשון" in b.get("name", ""):
                st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
                if st is not None and en is not None and (en - st) != 90:
                    violations.append(
                        f"יום {day.get('day','')}: 'מענה ראשון' חייב 90 דקות — שנה ל-{b.get('start')}–{_to_hhmm(st + 90)}"
                    )

    # 4. Songwriting: exactly 180 continuous min, once/week, never twice in a day.
    song_days = {}
    song_total = 0
    for day in schedule:
        for b in day.get("blocks", []):
            if "כתיבת שיר" in b.get("name", ""):
                song_total += 1
                song_days[day.get("day", "")] = song_days.get(day.get("day", ""), 0) + 1
                st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
                if st is not None and en is not None and (en - st) < 180:
                    violations.append(
                        f"יום {day.get('day','')}: 'כתיבת שירים' חייב 180 דקות רצופות — שנה ל-{b.get('start')}–{_to_hhmm(st + 180)} (או הזז לחלון ערב פנוי של 3 שעות)"
                    )
    for d, c in song_days.items():
        if c >= 2:
            violations.append(f"יום {d}: 'כתיבת שירים' שובץ פעמיים באותו יום — אחד את שני החלקים לבלוק יחיד של 180 דקות")
    if song_total > 1:
        violations.append(f"'כתיבת שירים' שובץ {song_total} פעמים — מקסימום פעם אחת בשבוע")

    # 5. Every confirmed event the user gave must appear somewhere.
    if events:
        all_names = " ".join(b.get("name", "") for d in schedule for b in d.get("blocks", []))
        for e in events:
            nm = (e.get("name") or "").strip()
            words = [w for w in nm.split() if len(w) >= 3]
            if words and not any(w in all_names for w in words):
                violations.append(f"האירוע שביקשת '{nm}' לא שובץ בלוח")

    # 6. ANCHOR LOCK: an event with a user-given day MUST appear on that exact day.
    if events:
        for e in events:
            days_list = e.get("days") or []
            if e.get("recurring") or not days_list or "כל יום" in days_list:
                continue
            target_days = [d for d in days_list if d in DAY_ORDER]
            if not target_days:
                continue
            nm = (e.get("name") or "").strip()
            words = [w for w in nm.split() if len(w) >= 3]
            if not words:
                continue
            on_target = any(
                any(w in b.get("name", "") for w in words)
                for d in target_days for b in out_by_day.get(d, [])
            )
            if not on_target:
                wrong = [d for d in DAY_ORDER
                         if any(any(w in b.get("name", "") for w in words) for b in out_by_day.get(d, []))]
                where = f" (כרגע מופיע ב-{', '.join(wrong)})" if wrong else ""
                violations.append(
                    f"האירוע '{nm}' חייב להיות ביום {', '.join(target_days)} בלבד — הזז אותו לשם{where}"
                )

    # 7. ROUNDING: no block may end at 23:59 or use off-grid minutes.
    for day in schedule:
        for b in day.get("blocks", []):
            for fld in ("start", "end"):
                v = _to_min(b.get(fld, ""))
                if v is None:
                    continue
                if b.get(fld) == "23:59" or (v % 30 != 0):
                    rounded = _to_hhmm(round(v / 30) * 30 % (24 * 60))
                    violations.append(
                        f"יום {day.get('day','')}: '{b.get('name','')}' עם שעה לא עגולה ({b.get(fld)}) — עגל ל-{rounded} (אף פעם לא 23:59)"
                    )

    # 8. RECURRING COVERAGE: every routine is a weekly commitment — enforce its frequency.
    if recurring:
        all_blocks = [(d.get("day", ""), b) for d in schedule for b in d.get("blocks", [])]
        freq_required = {"שבועי": 1, "x2 בשבוע": 2, "x3 בשבוע": 3}
        for t in recurring:
            nm = (t.get("name") or "").strip()
            freq = t.get("frequency") or ""
            block_type = t.get("block_type") or ""
            if not nm or freq == "פעם בשבועיים" or block_type == "קבוע":
                continue
            words = [w for w in nm.split() if len(w) >= 3]
            if not words:
                continue
            days_hit = set()
            count = 0
            for day_name, b in all_blocks:
                if all(w in b.get("name", "") for w in words):
                    count += 1
                    days_hit.add(day_name)
            if freq == "יומי":
                pref = t.get("days") or []
                target = DAY_ORDER if "כל יום" in pref else [d for d in pref if d in DAY_ORDER]
                missing = [d for d in target if d not in days_hit]
                if missing:
                    violations.append(f"השגרה '{nm}' (יומי) חסרה בימים: {', '.join(missing)} — שבץ אותה שם")
            else:
                need = freq_required.get(freq, 1)
                if count < need:
                    violations.append(
                        f"השגרה '{nm}' ({freq}) מופיעה {count} פעמים, צריך {need} — הוסף {need - count} בלוקים בימים שונים, לפי המשך שב'זמן מועדף'"
                    )

    # 9. GYM: the regular gym block must be 2.5h (the Tel Aviv evening one is exempt).
    for day in schedule:
        for b in day.get("blocks", []):
            name = b.get("name", "")
            if "כושר" in name and "תל אביב" not in name:
                st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
                if st is not None and en is not None and (en - st) != 150:
                    violations.append(
                        f"יום {day.get('day','')}: '{name}' חייב 2.5 שעות — שנה ל-{b.get('start')}–{_to_hhmm(st + 150)}"
                    )

    # 10. LUNCH: weekday lunch is 12:30-13:00, never overlapping מענה ראשון.
    for day in schedule:
        if day.get("day") not in WEEKDAYS:
            continue
        for b in day.get("blocks", []):
            if "ארוחת צהריים" in b.get("name", "") and (b.get("start"), b.get("end")) != ("12:30", "13:00"):
                violations.append(
                    f"יום {day.get('day','')}: 'ארוחת צהריים' חייב 12:30–13:00 (לא לחפוף מענה ראשון) — שנה לשם"
                )

    # 11. One מענה ראשון per day (the Tamir-day one runs parallel during travel).
    for day in schedule:
        cnt = sum(1 for b in day.get("blocks", []) if "מענה ראשון" in b.get("name", ""))
        if cnt > 1:
            violations.append(
                f"יום {day.get('day','')}: 'מענה ראשון' שובץ {cnt} פעמים — השאר רק אחד (ביום תמיר רק זה שמתבצע תוך כדי הנסיעה)"
            )

    # 13. EVENTS NOT FRAGMENTED: each event appears as exactly one block on its day.
    if events:
        for e in events:
            if e.get("recurring"):
                continue
            nm = (e.get("name") or "").strip()
            words = [w for w in nm.split() if len(w) >= 3]
            if not words:
                continue
            hits = [(d.get("day", ""), b) for d in schedule for b in d.get("blocks", [])
                    if all(w in b.get("name", "") for w in words) and "נסיעה" not in b.get("name", "")]
            if len(hits) > 1:
                violations.append(
                    f"האירוע '{nm}' פוצל ל-{len(hits)} בלוקים — אחד אותו לבלוק רצוף יחיד (אירוע לא מתפצל, גם לא בשביל ארוחה)"
                )

    # 14. CONTENT: יצירת תוכן is one contiguous block of at least 60 min, never fragmented.
    for day in schedule:
        content = [b for b in day.get("blocks", []) if "יצירת תוכן" in b.get("name", "")]
        if len(content) > 1:
            violations.append(
                f"יום {day.get('day','')}: 'יצירת תוכן' פוצל ל-{len(content)} חתיכות — אחד לבלוק רצוף אחד"
            )
        for b in content:
            st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
            if st is not None and en is not None and (en - st) < 60:
                violations.append(
                    f"יום {day.get('day','')}: 'יצירת תוכן' קצר מדי ({_to_hhmm(en - st)}) — בלוק רצוף של שעה לפחות"
                )

    # 12. BEDTIME: nothing scheduled past 23:30.
    bedtime = _to_min("23:30")
    for day in schedule:
        for b in day.get("blocks", []):
            en = _to_min(b.get("end", ""))
            if en is not None and en > bedtime:
                violations.append(
                    f"יום {day.get('day','')}: '{b.get('name','')}' נמשך אחרי 23:30 (שעת שינה) — סיים עד 23:30 או הזז מוקדם יותר"
                )

    return violations


def merge_open_windows(schedule):
    """Merge adjacent same-energy open windows; absorb sub-60-min windows into the shorter neighbor."""
    def is_open(b):
        return b.get("type") == "חלון פתוח" or b.get("name") == "חלון פתוח"

    def dur(b):
        return (_to_min(b.get("end", "")) or 0) - (_to_min(b.get("start", "")) or 0)

    for day in schedule:
        blocks = day.get("blocks", [])
        blocks.sort(key=lambda b: _to_min(b.get("start", "")) or 0)

        merged = []
        for b in blocks:
            if (is_open(b) and merged and is_open(merged[-1])
                    and merged[-1].get("energy") == b.get("energy")
                    and _to_min(merged[-1].get("end", "")) == _to_min(b.get("start", ""))):
                merged[-1]["end"] = b.get("end")
            else:
                merged.append(b)

        result = []
        for i, b in enumerate(merged):
            if is_open(b) and 0 <= dur(b) < 60:
                prev_b = result[-1] if result else None
                next_b = merged[i + 1] if i + 1 < len(merged) else None
                prev_ok = (prev_b is not None and not is_open(prev_b)
                           and _to_min(prev_b.get("end", "")) == _to_min(b.get("start", "")))
                next_ok = (next_b is not None and not is_open(next_b)
                           and _to_min(next_b.get("start", "")) == _to_min(b.get("end", "")))
                if prev_ok and (not next_ok or dur(prev_b) <= dur(next_b)):
                    prev_b["end"] = b.get("end")
                elif next_ok:
                    next_b["start"] = b.get("start")
                continue
            result.append(b)
        day["blocks"] = result
    return schedule


def build_repair_prompt(schedule, violations):
    return f"""להלן לוח שבועי בפורמט JSON שיצרת:
{json.dumps(schedule, ensure_ascii=False)}

נמצאו הבעיות הבאות. בצע בדיוק את התיקונים המצוינים:
{chr(10).join('- ' + v for v in violations)}

תקן אך ורק את הבעיות האלה. אם צוין זמן מדויק לתיקון — השתמש בו בדיוק. אל תיגע בבלוקים הקבועים פרט להחזרתם למקומם, ואל תשנה שום דבר אחר.
זכור: משימות מיקרו עם "parallel": true מותר שיחפפו — אל תזיז אותן בגלל חפיפה.
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
            tag = " ↔ (במקביל)" if b.get("parallel") else ""
            line = f"{b.get('start','')}–{b.get('end','')}  {b.get('name','')}{tag}".strip()
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


# ===================== DETERMINISTIC PLACEMENT ENGINE =====================
# The model never sets times. This code does. Priority: EVENTS > FIXED > ROUTINES.

DAY_START_MIN, BEDTIME_MIN = 7 * 60 + 30, 23 * 60 + 30
TRAVEL_BUFFER_MIN = 30
DATED_INBOX_DEFAULT_MIN = 90  # default length for a dated inbox task with no duration in זמן מועדף
MICRO_MAX_MIN = 15  # routines shorter than this are micro-tasks: placed parallel, never their own grid slot
OUT_NAMES = ["נסיעה לאופיס", "וולט", "תמיר", "שיעור ריקוד", "הרב יגאל", "כושר"]
HOME_ONLY_NAMES = ["כתיבת שירים", "הבס", "הופעה", "יצירת תוכן", "סונו", "מהלכי ריקוד"]

# Biweekly pair that alternates week-to-week (one each week). פעם בשבועיים items NOT in a pair
# stay manual (flagged via weekly exceptions), same as before. (Future: this becomes a data tag.)
ALTERNATING_PAIR = ("הופעת רחוב", "שיעור ריקוד")


def select_biweekly_twin(events, recurring, week_index):
    """Pick which of the alternating pair runs THIS week.
    - Deterministic by calendar-week parity -> regenerating in the same week never flips it
      (important during testing); real week-to-week it alternates and 'lands' on its own.
    - If the user names one of the pair in this week's exceptions, that overrides parity."""
    names = sorted({r.get("name") for r in recurring
                    if r.get("name") in ALTERNATING_PAIR and r.get("frequency") == "פעם בשבועיים"})
    if not names:
        return None
    for ev in (events or []):                    # manual override for this week
        evn = ev.get("name") or ""
        for nm in names:
            if nm in evn:
                return nm
    if len(names) == 1:                          # lone item -> every other week
        return names[0] if week_index % 2 == 0 else None
    return names[week_index % len(names)]        # the pair -> alternate


def _energy_emoji(s):
    """Normalize any energy value (full Hebrew label or emoji) to a single emoji."""
    if not s:
        return ""
    if "ירוק" in s or "🟢" in s:
        return "🟢"
    if "צהוב" in s or "🟡" in s:
        return "🟡"
    if "אדום" in s or "🔴" in s:
        return "🔴"
    return ""


def _parse_duration_he(text):
    if not text:
        return None
    import re
    # Digit forms first (most common when users type): "2 דקות", "45 דקות", "2 שעות", "1.5 שעות".
    m = re.search(r"(\d+(?:\.\d+)?)\s*דק", text)          # דקה / דקות
    if m:
        return max(1, int(round(float(m.group(1)))))
    m = re.search(r"(\d+(?:\.\d+)?)\s*שע", text)          # שעה / שעות
    if m:
        return int(round(float(m.group(1)) * 60))
    table = [("חמש עשרה דקות", 15), ("שעתיים וחצי", 150), ("שלוש שעות", 180),
             ("ארבע שעות", 240), ("חמש שעות", 300), ("שעתיים", 120), ("חצי שעה", 30),
             ("שעה וחצי", 90), ("שעה אחת", 60),
             ("עשר דקות", 10), ("חמש דקות", 5), ("שתי דקות", 2), ("דקותיים", 2), ("שעה", 60)]
    for word, mins in table:
        if word in text:
            return mins
    return None


def _split_travel(text):
    """Separate an optional 'נסיעה: <dur>' hint from the rest of a זמן מועדף string.
    Lets travel time live in the task data (per destination) instead of being hardcoded."""
    if text and "נסיעה" in text:
        main, trav = text.split("נסיעה", 1)
        return main.rstrip(" /"), trav
    return (text or ""), ""


def _parse_travel_min(text):
    """Travel-buffer minutes from a 'נסיעה: <dur>' hint in זמן מועדף, else the default."""
    _, trav = _split_travel(text)
    return _parse_duration_he(trav) or TRAVEL_BUFFER_MIN


def _range_from(s):
    import re
    times = re.findall(r"(\d{1,2}):(\d{2})", s)
    if len(times) >= 2:
        return (int(times[0][0]) * 60 + int(times[0][1]), int(times[1][0]) * 60 + int(times[1][1]))
    if len(times) == 1:
        return (int(times[0][0]) * 60 + int(times[0][1]), None)
    return None


def _parse_window(text, day=None):
    if not text or ("גמיש" in text and "-" not in text):
        return (DAY_START_MIN, BEDTIME_MIN)
    if "בראשון" in text and "/" in text:
        sun_part, rest_part = text.split("/", 1)
        part = sun_part if day == "ראשון" else rest_part
        r = _range_from(part)
        return (r[0], r[1] or BEDTIME_MIN) if r else (DAY_START_MIN, BEDTIME_MIN)
    r = _range_from(text)
    return (r[0], r[1] or BEDTIME_MIN) if r else (DAY_START_MIN, BEDTIME_MIN)


def _freq_count(freq):
    return {"שבועי": 1, "x2 בשבוע": 2, "x3 בשבוע": 3}.get(freq, 1 if freq == "יומי" else 0)


def _is_out(name):
    return any(k in name for k in OUT_NAMES)


def _home_only(name):
    return any(k in name for k in HOME_ONLY_NAMES)


class DayPlan:
    def __init__(self, day):
        self.day = day
        self.blocks = []

    def occupied(self, s, e):  # spans don't count (office permits work blocks inside it)
        for b in self.blocks:
            if b.get("parallel") or b.get("span"):
                continue
            if s < b["end"] and e > b["start"]:
                return True
        return False

    def blocked(self, s, e):  # for routines: spans block too
        for b in self.blocks:
            if b.get("parallel"):
                continue
            if s < b["end"] and e > b["start"]:
                return True
        return False

    def out_overlap(self, s, e):
        for b in self.blocks:
            if b.get("out") and s < b["end"] and e > b["start"]:
                return True
        return False

    def place(self, name, s, e, energy="", parallel=False, out=False, span=False):
        self.blocks.append({"start": s, "end": e, "name": name, "energy": energy,
                            "parallel": parallel, "out": out, "span": span})

    def free_slot(self, win_s, win_e, dur, need_home=False):
        edges = sorted({win_s, win_e} | {b["start"] for b in self.blocks} | {b["end"] for b in self.blocks})
        for t in edges:
            if t < win_s:
                continue
            s, e = t, t + dur
            if e > win_e or e > BEDTIME_MIN:
                break
            if not self.blocked(s, e) and not (need_home and self.out_overlap(s, e)):
                return s
        return None

    def sorted_blocks(self):
        return sorted(self.blocks, key=lambda b: (b["start"], 1 if b.get("parallel") else 0))


def _spread_days(name, used_days, week):
    used = used_days.get(name, set())
    return [d for d in week if d not in used] + [d for d in week if d in used]


def _routine_days(r, tamir_day):
    """Explicit target days for a routine ('כל יום' -> all 7), or None if flexible.
    Tamir day is excluded (light day); a routine that names only Tamir-day falls
    back to flexible placement."""
    raw = r.get("days") or []
    if "כל יום" in raw:
        # "כל יום" = every working day. Saturday is a rest day: routines auto-placed across
        # the week skip it. A routine that genuinely runs on שבת must list שבת explicitly.
        return [d for d in DAY_ORDER if d != tamir_day and d != "שבת"]
    specific = [d for d in raw if d in DAY_ORDER and d != tamir_day]
    return specific or None


def classify_items(fixed_blocks, recurring):
    """Split everything into FIXED (concrete day+time) and ROUTINE (flexible window)."""
    fixed = [dict(name=f["name"], days=f.get("days", []),
                  start=_to_min(f.get("start", "")), end=_to_min(f.get("end", "")),
                  energy=f.get("energy", "")) for f in fixed_blocks
             if _to_min(f.get("start", "")) is not None and _to_min(f.get("end", "")) is not None]

    def covered(day, s, e):
        return any(day in fb["days"] and fb["start"] == s and fb["end"] == e for fb in fixed)

    routines = []
    for r in recurring:
        freq = r.get("frequency") or ""
        if freq == "פעם בשבועיים":
            continue  # only when the user flags it in the weekly exceptions
        if (r.get("importance") or "") == "זמן פנוי":
            continue  # mood pool: never auto-placed — offered by the /start energy flow
        pt = r.get("preferred_time") or ""
        days = [d for d in (r.get("days") or []) if d in DAY_ORDER]

        if days and "בראשון" in pt and "/" in pt:
            dur = _parse_duration_he(pt)
            for d in days:
                ws, we = _parse_window(pt, d)
                e = (ws + dur) if dur else we
                if not covered(d, ws, e):
                    fixed.append(dict(name=r["name"], days=[d], start=ws, end=e,
                                      energy=r.get("energy", "")))
            continue

        has_duration = ("משך" in pt) or (_parse_duration_he(pt) is not None)
        rng = _range_from(pt)
        # A concrete clock range with no duration word is a fixed-time block. Specific days
        # promote on those days; "כל יום" promotes on all 7. (Daily meals belong in the
        # skeleton, so they win their slot instead of losing it to a flexible routine.)
        promote_days = DAY_ORDER if "כל יום" in (r.get("days") or []) else days
        if rng and rng[1] and promote_days and not has_duration:
            for d in promote_days:
                if not covered(d, rng[0], rng[1]):
                    fixed.append(dict(name=r["name"], days=[d], start=rng[0], end=rng[1],
                                      energy=r.get("energy", "")))
        else:
            routines.append(r)
    return fixed, routines


def classify_dated_inbox(inbox_tasks):
    """Stage 3: pick inbox tasks that carry an explicit weekday.
    Tasks with no day (or only 'גמיש') stay out — they belong to the /start mood pool (Stage 4).
    Returns a list of dicts ready for build_week's dated-inbox pass."""
    dated = []
    for t in (inbox_tasks or []):
        days = [d for d in (t.get("days") or []) if d in DAY_ORDER]
        if not days:
            continue
        dated.append({
            "id": t.get("id"),
            "name": t.get("name", ""),
            "days": days,
            "preferred_time": t.get("preferred_time") or "",
            "energy": t.get("energy", ""),
        })
    return dated


def _dated_inbox_timing(pt):
    """Decide how a dated inbox task is timed from its זמן מועדף text.
    Returns (pinned_start_min_or_None, duration_min). A 'נסיעה: ...' travel hint is
    stripped first so it can't be mistaken for the task's own length.
    - single time, no duration word  -> pinned start (e.g. '21:30')
    - window/range or has a duration  -> not pinned; place in the window via free_slot."""
    main = _split_travel(pt)[0]
    has_dur = ("משך" in main) or (_parse_duration_he(main) is not None)
    dur = _parse_duration_he(main) or DATED_INBOX_DEFAULT_MIN
    rng = _range_from(main)
    if rng and rng[1] is None and not has_dur:
        return rng[0], dur          # one explicit clock time -> pin it
    return None, dur                # window / range / duration-based -> free slot


def build_week(fixed, recurring, events, dated_inbox=None):
    week = DAY_ORDER[:6]  # placement happens Sun–Fri; Sat is mostly its own fixed routine
    plans = {d: DayPlan(d) for d in DAY_ORDER}

    # 1. EVENTS (highest; with travel buffer; can displace fixed)
    for ev in events:
        dur = ev.get("duration_min") or 240
        for day in ev.get("days", []):
            if day not in plans:
                continue
            t = ev.get("time")
            start = _to_min(t) if t and t != "גמיש" else (plans[day].free_slot(18 * 60, BEDTIME_MIN, dur) or 18 * 60)
            end = min(start + dur, BEDTIME_MIN)
            plans[day].place("נסיעה ל" + ev["name"], max(DAY_START_MIN, start - TRAVEL_BUFFER_MIN), start, out=True)
            plans[day].place(ev["name"], start, end, out=True)

    # ---- TAMIR DAY: special flow (leave 11:00, מענה parallel in transit, evening TLV gym) ----
    tamir_day, tamir_fb = None, None
    for fb in fixed:
        if "תמיר" in fb["name"]:
            tamir_day = fb["days"][0] if fb["days"] else None
            tamir_fb = fb
            break
    if tamir_day:
        s_start, s_end = tamir_fb["start"], tamir_fb["end"]
        plans[tamir_day].place("נסיעה למודיעין", 11 * 60, s_start, out=True)
        plans[tamir_day].place("מענה ראשון לתלמידים", 11 * 60, 11 * 60 + 90, parallel=True, out=True)
        plans[tamir_day].place("נסיעה חזרה ממודיעין", s_end, s_end + 90, out=True)
        plans[tamir_day].place("מענה שני לתלמידים", s_end, s_end + 90, parallel=True, out=True)
        plans[tamir_day].place("חדר כושר (תל אביב)", s_end + 90, s_end + 90 + 120, out=True)

    # 2. FIXED (office = permeable span; others exclusive; skip if event took the slot)
    #    Placed earliest-start first (then longest first) so an earlier/longer commitment
    #    anchors and a later short block yields instead of evicting it.
    seen = set()
    for fb in sorted(fixed, key=lambda b: (b["start"], -(b["end"] - b["start"]))):
        s, e = fb["start"], fb["end"]
        is_office = ("אופיס" in fb["name"]) or ("עבודה" in fb["name"])
        for day in fb["days"]:
            if day not in plans:
                continue
            if day == tamir_day and ("מענה" in fb["name"]):
                continue
            key = (day, s, e, fb["name"])
            if key in seen:
                continue
            seen.add(key)
            if is_office:
                plans[day].place(fb["name"], s, e, energy=fb.get("energy", ""), out=True, span=True)
            elif not plans[day].occupied(s, e):
                plans[day].place(fb["name"], s, e, energy=fb.get("energy", ""), out=_is_out(fb["name"]))

    # 2.5 DATED INBOX (Stage 3): one-time tasks with an explicit day, placed like priority-2.
    #     Travel buffer only if the task is out-of-home (_is_out). Pinned tasks reserve their
    #     exact time; day-only tasks take a free slot inside their window. Runs after FIXED so a
    #     day-only task slots around the skeleton, and before ROUTINES so flexible routines yield.
    placed_inbox_ids = []
    for it in (dated_inbox or []):
        name = it.get("name", "")
        if not name:
            continue
        out = _is_out(name)
        energy = _energy_emoji(it.get("energy", ""))
        pt = it.get("preferred_time", "")
        main = _split_travel(pt)[0]          # זמן מועדף without the travel hint
        travel = _parse_travel_min(pt)       # per-task travel buffer (default 30)
        pinned_start, dur = _dated_inbox_timing(pt)
        placed_any = False
        for day in it.get("days", []):
            if day not in plans:
                continue
            if any(b["name"] == name for b in plans[day].blocks):
                placed_any = True  # already present on this day
                continue
            if pinned_start is not None:
                start = pinned_start
                end = min(start + dur, BEDTIME_MIN)
                if end <= start:
                    continue
            else:
                ws, we = _parse_window(main, day)
                slot = plans[day].free_slot(ws, we, dur, need_home=not out)
                if slot is None:
                    continue
                start, end = slot, slot + dur
            if out:
                plans[day].place("נסיעה ל" + name,
                                 max(DAY_START_MIN, start - travel), start, out=True)
            plans[day].place(name, start, end, energy=energy, out=out)
            placed_any = True
        if placed_any and it.get("id"):
            placed_inbox_ids.append(it["id"])

    # 3. ROUTINES (flexible, distributed; durations & windows from Notion)
    STRICT_NAMES = ["חדר כושר", "כתיבת שירים", "השלמת תוכן"]
    routine_week = [d for d in week if d != tamir_day]  # Tamir day is a light day
    occ = []  # each entry: (routine, day_pool) — the days this occurrence may use
    for r in recurring:
        freq = r.get("frequency") or ""
        gym_drop = 1 if (tamir_day and "חדר כושר" in r["name"]) else 0
        target = _routine_days(r, tamir_day)
        if freq == "יומי":
            for d in (target or routine_week):
                occ.append((r, [d]))
        else:
            pool = target or routine_week
            for _ in range(max(0, _freq_count(freq) - gym_drop)):
                occ.append((r, pool))
    occ.sort(key=lambda x: (0 if any(k in x[0]["name"] for k in STRICT_NAMES) else 1,
                            -(_parse_duration_he(x[0].get("preferred_time")) or 60)))

    unplaced, used_days = [], {}
    for r, day_pool in occ:
        name = r["name"]
        need_home = _home_only(name)
        strict = any(k in name for k in STRICT_NAMES)
        candidates = day_pool if len(day_pool) == 1 else _spread_days(name, used_days, day_pool)
        win_s, win_e = _parse_window(r.get("preferred_time"), candidates[0] if candidates else None)
        dur = _parse_duration_he(r.get("preferred_time")) or (win_e - win_s)
        micro = dur < MICRO_MAX_MIN  # a 2-5 min "send messages" task rides alongside, doesn't own a slot

        def try_place(window):
            for day in candidates:
                if any(b["name"] == name for b in plans[day].blocks):
                    used_days.setdefault(name, set()).add(day)
                    return True
                ws, we = window if window else _parse_window(r.get("preferred_time"), day)
                if micro:
                    # ride in real free time but as parallel, so it never shifts other blocks
                    anchor = plans[day].free_slot(ws, we, dur, need_home=need_home)
                    if anchor is None:
                        anchor = ws
                    plans[day].place(name, anchor, anchor + dur, energy=r.get("energy", ""),
                                     parallel=True, out=_is_out(name))
                    used_days.setdefault(name, set()).add(day)
                    return True
                slot = plans[day].free_slot(ws, we, dur, need_home=need_home)
                if slot is not None:
                    plans[day].place(name, slot, slot + dur, energy=r.get("energy", ""), out=_is_out(name))
                    used_days.setdefault(name, set()).add(day)
                    return True
            return False

        placed = try_place(None)
        if not placed and not strict:
            placed = try_place((DAY_START_MIN, BEDTIME_MIN))
        if not placed:
            unplaced.append(name)

    # 4. OPEN WINDOWS (>= 60 min gaps)
    for day, plan in plans.items():
        real = [x for x in plan.sorted_blocks() if not x.get("parallel")]
        if not real:
            continue  # nothing scheduled -> no open-window noise
        cursor = real[0]["start"]  # day begins at the first activity; no pre-wake/sleep window
        gaps = []
        for b in real:
            if b["start"] - cursor >= 60:
                gaps.append((cursor, b["start"]))
            cursor = max(cursor, b["end"])
        if BEDTIME_MIN - cursor >= 60:
            gaps.append((cursor, BEDTIME_MIN))
        for g in gaps:
            plan.place("חלון פתוח", g[0], g[1], energy="🟡")

    return plans, unplaced, placed_inbox_ids


def plans_to_schedule(plans):
    schedule = []
    for day in DAY_ORDER:
        blocks = []
        for b in plans[day].sorted_blocks():
            blocks.append({
                "day": day, "start": _to_hhmm(b["start"]), "end": _to_hhmm(b["end"]),
                "name": b["name"], "energy": b.get("energy", ""),
                "type": "חלון פתוח" if b["name"] == "חלון פתוח" else "בלוק",
                "parallel": bool(b.get("parallel")),
            })
        schedule.append({"day": day, "blocks": blocks})
    return schedule


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

    fixed_raw = await get_fixed_blocks()
    if not fixed_raw:
        await context.bot.send_message(
            chat_id,
            "לא הצלחתי לקרוא את הבלוקים הקבועים. ודא שה-integration של הבוט מחובר לדאטהבייס 'בלוקים קבועים'."
        )
        return
    recurring_raw = await get_recurring_tasks_full()
    inbox_raw = await get_inbox_tasks_full()
    dated_inbox = classify_dated_inbox(inbox_raw)

    israel_tz = pytz.timezone("Asia/Jerusalem")
    week_index = datetime.now(israel_tz).isocalendar()[1]

    # Alternating biweekly pair: activate exactly one for this week; skip the other.
    twin = select_biweekly_twin(events, recurring_raw, week_index)
    recurring_for_build = []
    for r in recurring_raw:
        if r.get("name") in ALTERNATING_PAIR and r.get("frequency") == "פעם בשבועיים":
            if r.get("name") == twin:
                recurring_for_build.append({**r, "frequency": "שבועי"})  # run it this week
            # else: the other twin -> not this week
        else:
            recurring_for_build.append(r)
    # if the user named the twin in exceptions, don't ALSO place it as a priority-2 event
    events = [e for e in events if not (twin and twin in (e.get("name") or ""))]

    fixed, routines = classify_items(fixed_raw, recurring_for_build)
    plans, unplaced, placed_inbox_ids = build_week(fixed, routines, events, dated_inbox=dated_inbox)
    schedule = plans_to_schedule(plans)

    title = "לוז שבועי – " + datetime.now(israel_tz).strftime("%d/%m/%Y")
    page_id, url = await create_schedule_page(title, schedule_to_blocks(schedule))
    if not page_id:
        await context.bot.send_message(
            chat_id,
            "יצירת הדף בנוטיון נכשלה. ודא ש-WEEKLY_SCHEDULES_PARENT נכון ושה-integration מחובר לדף."
        )
        return

    context.user_data["draft_page_id"] = page_id
    context.user_data["pending_inbox_ids"] = placed_inbox_ids

    msg = f"הלוח מוכן 📅\n{url}\n"
    if placed_inbox_ids:
        msg += f'\nℹ️ שובצו {len(placed_inbox_ids)} משימות אינבוקס עם יום מפורש (יסומנו כ"מתוזמן" באישור).'
    msg += "\nאת החלונות הפתוחים תמלא לפי אנרגיה במהלך השבוע (פקודת /start)."
    if unplaced:
        uniq = []
        for u in unplaced:
            if u not in uniq:
                uniq.append(u)
        msg += "\n\nℹ️ לא נמצא מקום השבוע ל: " + ", ".join(uniq) + " (השבוע עמוס — אפשר לפנות זמן ידנית)."
    msg += "\nלאשר?"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ אשר", callback_data="approve_schedule"),
        InlineKeyboardButton("🔄 צור מחדש", callback_data="regen_schedule"),
    ]])
    await context.bot.send_message(chat_id, msg, reply_markup=keyboard)


async def _OLD_generate_and_post(chat_id, context):
    events = context.user_data.get("parsed_events", [])

    prev = context.user_data.get("draft_page_id")
    if prev:
        try:
            await archive_page(prev)
        except Exception as e:
            print(f"archive error: {e}")
        context.user_data["draft_page_id"] = None

    fixed = await get_fixed_blocks()
    if not fixed:
        await context.bot.send_message(
            chat_id,
            "לא הצלחתי לקרוא את הבלוקים הקבועים. ודא שה-integration של הבוט מחובר לדאטהבייס 'בלוקים קבועים'."
        )
        return
    fixed_by_day = skeleton_by_day(fixed)
    recurring = await get_recurring_tasks_full()
    inbox = await get_inbox_tasks_full()

    prompt = build_schedule_prompt(fixed_by_day, recurring, inbox, events)
    try:
        result = await asyncio.to_thread(generate_schedule_json, prompt)
    except Exception as e:
        print(f"generation error: {e}")
        await context.bot.send_message(chat_id, "הבנייה נכשלה (שגיאת JSON או מודל). נסה שוב עם /schedule.")
        return

    schedule = result.get("schedule", [])
    ids = result.get("scheduled_inbox_ids", [])

    violations = validate_schedule(schedule, fixed_by_day, events, recurring)
    attempts = 0
    while violations and attempts < 2:
        if attempts == 0:
            await context.bot.send_message(chat_id, "כמעט מוכן, מתקן כמה פרטים אחרונים...")
        try:
            repaired = await asyncio.to_thread(generate_schedule_json, build_repair_prompt(schedule, violations))
            schedule = repaired.get("schedule", schedule)
            if repaired.get("scheduled_inbox_ids"):
                ids = repaired.get("scheduled_inbox_ids")
        except Exception as e:
            print(f"repair error: {e}")
            break
        violations = validate_schedule(schedule, fixed_by_day, events, recurring)
        attempts += 1

    schedule = merge_open_windows(schedule)
    remaining = violations

    israel_tz = pytz.timezone("Asia/Jerusalem")
    title = "לוז שבועי – " + datetime.now(israel_tz).strftime("%d/%m/%Y")
    page_id, url = await create_schedule_page(title, schedule_to_blocks(schedule))
    if not page_id:
        await context.bot.send_message(
            chat_id,
            "יצירת הדף בנוטיון נכשלה. ודא ש-WEEKLY_SCHEDULES_PARENT נכון ושה-integration מחובר לדף."
        )
        return

    context.user_data["draft_page_id"] = page_id
    context.user_data["pending_inbox_ids"] = ids

    if ids:
        inbox_line = f"שובצו {len(ids)} משימות אינבוקס עם יום מפורש."
    else:
        inbox_line = "לא שובצו משימות אינבוקס אוטומטית — את החלונות הפתוחים תמלא לפי אנרגיה במהלך השבוע (פקודת /start)."
    msg = f"הלוח מוכן 📅\n{url}\n\n{inbox_line}\nלאשר?"
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
    context.user_data["exceptions_text"] = text
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
    base_text = context.user_data.get("exceptions_text", "")
    full_text = (base_text + "\n\nהבהרה/תיקון נוסף מהמשתמש: " + text).strip()
    failed = False
    try:
        events = await asyncio.to_thread(parse_exceptions, full_text)
        if not events:
            events = prev
            failed = True
    except Exception as e:
        print(f"reparse error: {e}")
        events = prev
        failed = True

    context.user_data["exceptions_text"] = full_text
    context.user_data["parsed_events"] = events

    if failed:
        await update.message.reply_text(
            "לא הצלחתי לעבד את התיקון הזה 🤔 נסה לנסח אותו אחרת (איזה אירוע ומה לשנות), "
            'או כתוב "כן" כדי לאשר את מה שיש.'
        )
        return SCHEDULE_CONFIRM

    if events == prev:
        await update.message.reply_text(
            build_readback(events) +
            '\n\nℹ️ זה כבר מסומן בדיוק ככה — לא היה מה לשנות. כתוב "כן" לאישור, '
            "או תגיד מפורש איזה אירוע ומה לשנות בו."
        )
        return SCHEDULE_CONFIRM

    await update.message.reply_text(
        build_readback(events) + '\n\nנכון עכשיו? "כן" לאישור, או תקן שוב.'
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
        if ok:
            await query.edit_message_text(
                f'אושר ✅\n{ok} משימות אינבוקס סומנו כ"מתוזמן".'
            )
        else:
            await query.edit_message_text("אושר ✅")
    elif query.data == "regen_schedule":
        await query.edit_message_text("בונה מחדש... 🔄")
        await generate_and_post(query.message.chat_id, context)
    elif query.data.startswith("moodpick:"):
        try:
            i = int(query.data.split(":")[1])
        except (ValueError, IndexError):
            return
        sug = context.user_data.get("mood_suggestions", [])
        if 0 <= i < len(sug):
            p = sug[i]
            await query.edit_message_text(f"יאללה — {p['name']} 💪 ({p['dur']} דק')\nתיהנה!")


# ===================== MOOD POOL (/start energy flow) =====================
# Pool = tasks the user does only "if they feel like it". Signal (per spec): חשיבות/Priority
# == "זמן פנוי", in BOTH the recurring DB and the inbox. build_week already skips these, so
# their time stays an open window; /start offers them to fill it by energy + available time.

TIME_CHOICES = [["🕐 חצי שעה", "🕐 שעה"], ["🕐 שעתיים", "🕐 3 שעות+"]]


def parse_time_choice(text):
    text = text or ""
    if "חצי שעה" in text:
        return 30
    if "שעתיים" in text:
        return 120
    if "3 שעות" in text or "3+" in text or "שלוש שעות" in text:
        return 180
    if "שעה" in text:
        return 60
    return None


def _energy_allows(task_energy, chosen):
    """🟢→🟢 only; 🟡→🟡 or 🟢; 🔴→🔴 only. Blank task energy matches anything."""
    if not task_energy:
        return True
    if chosen == "🟢":
        return task_energy == "🟢"
    if chosen == "🟡":
        return task_energy in ("🟡", "🟢")
    if chosen == "🔴":
        return task_energy == "🔴"
    return True


def build_mood_pool(recurring_full, inbox_full):
    """Gather pool members from both sources. Inbox members must be חשיבות=זמן פנוי AND have no
    assigned day (a dated one is handled by the weekly schedule, not offered here)."""
    pool = []
    for r in recurring_full:
        if (r.get("importance") or "") == "זמן פנוי":
            pool.append({
                "name": r["name"],
                "energy": _energy_emoji(r.get("energy", "")),
                "dur": _parse_duration_he(r.get("preferred_time")) or 60,
                "src": "שגרה",
            })
    for t in inbox_full:
        has_day = any(d in DAY_ORDER for d in (t.get("days") or []))
        if (t.get("priority") or "") == "זמן פנוי" and not has_day:
            pool.append({
                "name": t["name"],
                "energy": _energy_emoji(t.get("energy", "")),
                "dur": _parse_duration_he(t.get("preferred_time")) or 60,
                "src": "אינבוקס",
            })
    return pool


def match_mood_pool(pool, chosen_energy, available_min):
    matches = [p for p in pool
               if _energy_allows(p["energy"], chosen_energy) and p["dur"] <= available_min]
    # nicest-first: higher-energy tasks first, then shorter ones (easier to start)
    rank = {"🟢": 0, "🟡": 1, "🔴": 2, "": 3}
    matches.sort(key=lambda p: (rank.get(p["energy"], 3), p["dur"]))
    return matches[:6]


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
    context.user_data["mood_energy"] = energy
    reply_markup = ReplyKeyboardMarkup(TIME_CHOICES, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("כמה זמן פנוי יש לך עכשיו?", reply_markup=reply_markup)
    return TIME_CHECK


async def handle_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mins = parse_time_choice(update.message.text)
    if mins is None:
        await update.message.reply_text("תבחר זמן מהכפתורים 🙂")
        return TIME_CHECK
    energy = context.user_data.get("mood_energy", "🟡")
    await update.message.reply_text("רגע, בודק מה מתאים...")
    recurring_full = await get_recurring_tasks_full()
    inbox_full = await get_inbox_tasks_full()
    pool = build_mood_pool(recurring_full, inbox_full)
    matches = match_mood_pool(pool, energy, mins)
    context.user_data["mood_suggestions"] = matches

    if not matches:
        await update.message.reply_text(
            f"אין כרגע משימות מאגר שמתאימות ל-{energy} ולזמן הזה. "
            "אפשר פשוט לנוח, או לבחור אנרגיה/זמן אחרים עם /start 🙂"
        )
        return ConversationHandler.END

    buttons = [[InlineKeyboardButton(f"{p['energy']} {p['name']} · {p['dur']} דק'",
                                     callback_data=f"moodpick:{i}")]
               for i, p in enumerate(matches)]
    await update.message.reply_text(
        "הנה כמה דברים מהמאגר שמתאימים לך עכשיו 👇\nבחר אחד (או פשוט תתעלם):",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
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
        states={
            ENERGY_CHECK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_energy)],
            TIME_CHECK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time)],
        },
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
