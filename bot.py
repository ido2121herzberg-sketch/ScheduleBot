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
- מיקום: לכל משימה יש מקום. נגינה, אימון על שירים וכתיבת מוזיקה דורשים בית — אי אפשר במשרד. בזמן בלוק עבודה/משרד שבץ אך ורק משימות עבודה או מחשב, לעולם לא מוזיקה. אל תשבץ משימה במקום שלא מתאים לה.
- נסיעה בתחבורה ציבורית: משימות שאפשר לעשות תוך כדי (מענה לתלמידים, קריאה, שיחות) רצות במקביל לנסיעה — "parallel": true. זו לא חפיפה ולא שגיאה.
- זמני מעבר: בין בלוקים במקומות שונים השאר זמן נסיעה. אחרי חדר כושר או יציאה מהבית יש דרך — אל תניח התחלה מיידית של המשימה הבאה; אפשר לשבץ בזמן המעבר משהו שאפשר לעשות בדרך.
- התאמה לשעת היום: אל תשבץ עבודה יצירתית תובענית (תוכן, כתיבת שירים, נגינה) אחרי 22:00 — עדיף בוקר או צהריים.
- משימות מיקרו (לשלוח הודעה, עדכון קצר) = 2-5 דקות, "parallel": true, מוצמדות לבלוק סמוך. לעולם לא בלוק ייעודי של חצי שעה.
- בלי פיצול שגרות: כל מופע הוא בלוק רצוף אחד באורך המלא.

== יום הסשן עם תמיר מפיק (לוגיקה מיוחדת) ==
- פעם בשבוע, שני עד חמישי. בחר את היום הקל ביותר. יום קל בלבד — בלי משימות כבדות לפני ואחרי.
- יציאה מהבית ב-11:00. הנסיעה למודיעין = בלוק יחיד "נסיעה למודיעין".
- 'מענה ראשון' מתבצע תוך כדי הנסיעה — "parallel": true, באותו משך כרגיל.
- מענה שני בדרך חזרה; חדר כושר בתל אביב בערב נחשב כאחד מימי הכושר (אין כושר בוקר/צהריים באותו יום).

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
    #    This is what catches "told it Wednesday, it placed Friday".
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
            # קבוע routines are fixed blocks or have their own hard rules — don't double-require here.
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

        # 1. Merge adjacent same-energy open windows into one.
        merged = []
        for b in blocks:
            if (is_open(b) and merged and is_open(merged[-1])
                    and merged[-1].get("energy") == b.get("energy")
                    and _to_min(merged[-1].get("end", "")) == _to_min(b.get("start", ""))):
                merged[-1]["end"] = b.get("end")
            else:
                merged.append(b)

        # 2. Open windows shorter than 60 min get absorbed into the shorter adjacent real block.
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
                    prev_b["end"] = b.get("end")        # extend shorter previous block into the gap
                elif next_ok:
                    next_b["start"] = b.get("start")     # pull shorter next block back into the gap
                # else: no real neighbor to absorb into -> drop the window
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

    # Silent validation + up to 2 prescriptive repair passes.
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
        # Re-parse the whole intent fresh, so a correction never builds on a corrupted copy.
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

    # Surface what actually happened instead of silently re-showing the same screen.
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
