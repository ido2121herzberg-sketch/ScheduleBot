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
FLEXIBLE_RULES = """כללי שיבוץ למשימות הגמישות. הבלוקים הקבועים כבר נתונים לך בנפרד — שבץ סביבם בלי לגעת בהם, בלי לשנות שעות ובלי למחוק.

**מענה ראשון לתלמידים:**
- ראשון 11:30-13:00. שני עד חמישי 11:00-12:30. תמיד בדיוק 90 דקות.
- ביום הסשן עם תמיר: מתבצע תוך כדי הליכה החל מ-11:00, באותו אורך (90 דקות).

**מענה שני לתלמידים:**
- ראשון עד חמישי 16:30-18:00.
- ביום הסשן עם תמיר בלבד: 18:30-20:00 (בדרך חזרה) במקום 16:30.

**ארוחת צהריים (חול):**
- 12:30-13:00 בימים ראשון, שני, רביעי, חמישי, שישי.
- ביום הסשן עם תמיר אין ארוחת צהריים קבועה.

**אימון כושר:**
- 3 פעמים בשבוע.
- ראשון 09:00-11:30 כולל מקלחת.
- בשאר הימים 12:00-14:00 בלבד, לא בזמן מסחר ולא בשעות עומס.

**סשן עם תמיר מפיק:**
- פעם בשבוע, יום שני עד חמישי, 14:00-18:30. בחר את היום הכי פנוי והכי קל.
- יציאה מהבית ב11:00 לתחבורה למודיעין; מענה ראשון תוך כדי הליכה.
- מענה שני בדרך חזרה 18:30-20:00; חדר כושר בתל אביב 20:00-22:00.
- ביום הזה — יום קל בלבד, בלי משימות כבדות לפני ואחרי.

**שיעור מסחר עם שחף:**
- שעה אחת, חמישי 18:00-19:00 בעדיפות. אם יש התנגשות — יום אחר באותו שבוע.

**כתיבת שירים:**
- בדיוק פעמיים בשבוע, בשני ימים שונים. כל פעם בלוק יחיד ורצוף של 3 שעות (180 דקות) בערב.
- אסור לפצל. אסור 'חלק א/ב'. אסור בלוק קצר מ-180 דקות. אסור פעמיים באותו יום.
- אם אין מספיק חלונות — פעם אחת בלבד, 180 דקות רצופות.

**קריאה:**
- 30 דקות, פעם אחת ביום, מפוזר על פני השבוע. לא פעמיים באותו יום.

**הופעת רחוב / שיעור ריקוד (מתחלפים כל שבוע):**
- הופעת רחוב — שישי או שבת, לא אחרי 16:00 בשישי.
- שיעור ריקוד עם שירן — שישי 15:30, רמת גן, פעם בשבועיים.
- המשתמש מציין בחריגים מה פעיל השבוע.

**משימות מיקרו (כמה דקות):**
- משימה שלוקחת דקה-שתיים — לשלוח הודעה, לעדכן מישהו, אדמין מהיר וקצר — סמן אותה עם "parallel": true.
- מותר שמשימת מיקרו תחפוף בלוק אחר (אפשר לעשות אותה תוך כדי). אל תקצה לה בלוק זמן בלעדי על חשבון משימה אמיתית, ואל תדחוף בגללה משימות אחרות.

**אנרגיה:**
- 🟢 גבוהה/חיובית — יצירתי ודורש ריכוז.
- 🟡 נמוכה/חיובית — קל, דורש קצת רצון.
- 🔴 נמוכה/שלילית — אדמין בלבד.

**חוקי ברזל: שני בלוקים אמיתיים (לא מיקרו) לעולם לא חופפים. אסור לגעת בבלוקים הקבועים או לשנות את שעותיהם. אל תפצל משימות שצריכות להיות רצופות."""


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
- time: שעה בפורמט HH:MM אם צוינה, אחרת "גמיש".
- recurring: true אם זה חוזר, אחרת false.
- energy/priority: רק אם נרמז, אחרת "".
- duration_min: מספר דקות אם צוין, אחרת null.
- אל תמציא פרטים שלא נאמרו ואל תוסיף אירועים שלא הוזכרו.
בלי טקסט נוסף, בלי markdown.

הקלט של המשתמש:
{text}"""
    return _claude_json(PARSE_MODEL, prompt, max_tokens=1500).get("events", [])


def reparse_with_correction(events, correction):
    prompt = f"""להלן פירוש קודם של אירועי השבוע (JSON) ותיקון שהמשתמש כתב. עדכן את הרשימה לפי התיקון.
פירוש קודם:
{json.dumps({"events": events}, ensure_ascii=False)}

התיקון של המשתמש:
{correction}

החזר אך ורק JSON באותו פורמט {{"events":[...]}}, בלי טקסט נוסף, בלי markdown."""
    return _claude_json(PARSE_MODEL, prompt, max_tokens=1500).get("events", events)


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
משימות חוזרות גמישות לשיבוץ בחלונות הפנויים (לפי אנרגיה, יום וזמן מועדף):
{rec_text}

---
משימות חדשות מהאינבוקס לשיבוץ (כל אחת עם מזהה id):
{inbox_text}

---
החריגים והאירועים של השבוע (מנותחים ומאושרים — שבץ בדיוק לפי היום והשעה; חובה שכולם יופיעו בלוח):
{events_to_text(events)}

---
בנה לוח שבועי מלא: העתק את כל הבלוקים הקבועים בדיוק, ואז מלא את שאר הזמן הפנוי במשימות הגמישות, החוזרות, האינבוקס והחריגים — בלי שום חפיפה בין משימות אמיתיות. משימות מיקרו (parallel) מותר שיחפפו.
החזר אך ורק JSON תקין. בלי טקסט נוסף, בלי markdown. מבנה מדויק:
{{
  "schedule": [
    {{"day": "ראשון", "blocks": [
        {{"start": "07:30", "end": "08:00", "name": "שם הבלוק", "energy": "🟢", "type": "קבוע", "parallel": false}}
    ]}}
  ],
  "scheduled_inbox_ids": ["<id של כל משימת אינבוקס ששובצה בפועל>"]
}}
כלול את כל שבעת הימים לפי הסדר: ראשון, שני, שלישי, רביעי, חמישי, שישי, שבת.
סמן "parallel": true רק למשימות מיקרו קצרות (כמה דקות), אחרת false."""


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


def validate_schedule(schedule, fixed_by_day, events):
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

    # 2. Every fixed block must appear unchanged (matched by day + exact start/end).
    for d in DAY_ORDER:
        for fb in fixed_by_day.get(d, []):
            fs, fe = _to_min(fb.get("start", "")), _to_min(fb.get("end", ""))
            found = any(
                _to_min(b.get("start")) == fs and _to_min(b.get("end")) == fe
                for b in out_by_day.get(d, [])
            )
            if not found:
                violations.append(f"יום {d}: הבלוק הקבוע '{fb['name']}' ({fb['start']}–{fb['end']}) חסר או זז")

    # 3. מענה ראשון must be 90 minutes on every weekday it appears (catches the shrink;
    #    works on Tamir day too since the walking version is also 90 min).
    for day in schedule:
        if day.get("day") not in WEEKDAYS:
            continue
        for b in day.get("blocks", []):
            if "מענה ראשון" in b.get("name", ""):
                st, en = _to_min(b.get("start", "")), _to_min(b.get("end", ""))
                if st is not None and en is not None and (en - st) < 90:
                    violations.append(
                        f"יום {day.get('day','')}: 'מענה ראשון' חייב 90 דקות, הופיע {en-st} דק'"
                    )

    # 4. Songwriting: exactly 3 continuous hours, max twice a week, never twice in a day,
    #    never split ('כתיבת שיר' avoids matching 'שירן').
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
                        f"יום {day.get('day','')}: 'כתיבת שירים' חייב 3 שעות רצופות, הופיע {en-st} דק'"
                    )
    for d, c in song_days.items():
        if c >= 2:
            violations.append(f"יום {d}: 'כתיבת שירים' שובץ פעמיים באותו יום — אסור לפצל")
    if song_total > 2:
        violations.append(f"'כתיבת שירים' שובץ {song_total} פעמים — מקסימום פעמיים בשבוע")

    # 5. Every confirmed event the user gave must appear somewhere.
    if events:
        all_names = " ".join(b.get("name", "") for d in schedule for b in d.get("blocks", []))
        for e in events:
            nm = (e.get("name") or "").strip()
            words = [w for w in nm.split() if len(w) >= 3]
            if words and not any(w in all_names for w in words):
                violations.append(f"האירוע שביקשת '{nm}' לא שובץ בלוח")
    return violations


def build_repair_prompt(schedule, violations):
    return f"""להלן לוח שבועי בפורמט JSON שיצרת:
{json.dumps(schedule, ensure_ascii=False)}

נמצאו הבעיות הבאות שחייבות תיקון:
{chr(10).join('- ' + v for v in violations)}

תקן אך ורק את הבעיות האלה. אל תיגע בבלוקים הקבועים פרט להחזרתם למקומם, ואל תשנה שום דבר אחר.
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
            line = f"{b.get('start','')}–{b.get('end','')}  {b.get('name','')}  {b.get('energy','')}{tag}".strip()
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

    violations = validate_schedule(schedule, fixed_by_day, events)
    if violations:
        await context.bot.send_message(chat_id, "כמעט מוכן, מתקן כמה התנגשויות אחרונות...")
        try:
            repaired = await asyncio.to_thread(generate_schedule_json, build_repair_prompt(schedule, violations))
            schedule = repaired.get("schedule", schedule)
            if repaired.get("scheduled_inbox_ids"):
                ids = repaired.get("scheduled_inbox_ids")
        except Exception as e:
            print(f"repair error: {e}")

    remaining = validate_schedule(schedule, fixed_by_day, events)

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
