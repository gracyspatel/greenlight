"""Owner: Split A (intake). Endpoint: POST /extract  {text, event?} -> {event, questions}.

How it works (the AI understands, code checks):
  1. The LLM turns the text (plus the current event, for follow-up answers) into Event JSON.
  2. Code verifies it: a date or number the model returns is kept only if it actually
     appears in the text (code also resolves "next Friday", "Dec 12", "$3.5k" itself).
     Anything unverified is dropped, so the engine asks for it instead of guessing.
  3. The result is deep-merged into the current event and normalized by the engine.
  No key / any LLM error -> a plain regex extractor does steps 1-2 on its own.
"""
from __future__ import annotations

import datetime as dt
import json
import re

from fastapi import APIRouter
from pydantic import BaseModel

from .. import engine, llm

router = APIRouter(tags=["intake"])

EXTRACT_SYSTEM = """You turn a USC student club's event description into JSON for an approvals checker.

Return ONE JSON object with exactly these keys. Use null for anything the text does not state.
Never guess or invent a date, amount, count or name.

{
  "name": string,                      // event name, e.g. "Diwali Night"
  "date": "YYYY-MM-DD" | null,         // the event day. Resolve words like "next Friday" using TODAY given below
  "venue": {
    "name": string | null,             // e.g. "TCC Grand Ballroom"
    "on_campus": true | false | null,  // false only if clearly off campus (restaurant, park, hotel, another city)
    "confirmed": true | false | null   // true only if the text says the room is booked/confirmed/reserved
  },
  "attendance": integer | null,        // expected people
  "food": {
    "served": true | false | null,     // any food or drinks at the event
    "sold": true | false | null,       // food is SOLD to attendees (not just given away)
    "vendor": string | null,           // e.g. "USC Hospitality", "a local restaurant"
    "vendor_approved": true | false | null  // true only for USC Hospitality or a vendor the text calls USC-approved
  },
  "dancing": true | false | null,      // dancing, DJ dance floor, social dance
  "ticket_sales": true | false | null, // tickets, entry fee, selling anything to raise money
  "funding_source": "USG" | "GSG" | "none" | null,  // who they ask for money (undergrad gov = USG, grad gov = GSG)
  "amount_requested": number | null,   // dollars asked from USG/GSG. "$3.5k" = 3500
  "budget_lines": [                    // one per cost the text mentions, [] if none
    {"item": string, "category": "venue"|"food"|"entertainment"|"supplies"|"marketing"|"other",
     "amount": number, "quote_attached": true | false}   // quote_attached true only if the text says they have a quote
  ],
  "org": {
    "funded_events_this_semester": integer | null,  // events USG already funded for this club this semester
    "usg_received_this_year": number | null,        // dollars from USG already this academic year
    "other_university_funding": true | false | null,// another USC office also funds this event
    "past_misuse": true | false | null,
    "usg_funds_low": true | false | null
  },
  "questions": [string]                // 0-3 short questions, ONLY about something the text mentions but leaves unclear
}                                      // (e.g. "food" but not who provides it). Never ask whether they will add
                                       // something the text doesn't mention (dancing, tickets, other funding): treat it as no.

Example. TODAY: Sunday 2026-11-15.
Text: "Diwali Night on Dec 12 in the TCC Grand Ballroom (not booked yet), about 300 people. We'll sell tickets and
food from a local restaurant, DJ and dancing. Asking USG for $3,500. Costs: ballroom $4,500, DJ $600, no quotes yet.
USG has funded 4 of our events this semester, $5,200 total this year."
JSON:
{"name":"Diwali Night","date":"2026-12-12",
 "venue":{"name":"TCC Grand Ballroom","on_campus":true,"confirmed":false},
 "attendance":300,
 "food":{"served":true,"sold":true,"vendor":"Local restaurant","vendor_approved":false},
 "dancing":true,"ticket_sales":true,"funding_source":"USG","amount_requested":3500,
 "budget_lines":[{"item":"Grand Ballroom","category":"venue","amount":4500,"quote_attached":false},
                 {"item":"DJ","category":"entertainment","amount":600,"quote_attached":false}],
 "org":{"funded_events_this_semester":4,"usg_received_this_year":5200,
        "other_university_funding":null,"past_misuse":null,"usg_funds_low":null},
 "questions":[]}

If a CURRENT EVENT is given, the text is a follow-up answer: return the full updated event
(keep current values unless the text changes them)."""


class ExtractIn(BaseModel):
    text: str
    event: dict | None = None


# ------------------------------------------------------------------ text parsing (no AI)
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NUM_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"


def _future(month: int, day: int, today: dt.date) -> dt.date | None:
    """Month/day with no year -> the next time it happens on or after today."""
    for year in (today.year, today.year + 1):
        try:
            d = dt.date(year, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


def find_dates(text: str, today: dt.date) -> list[dt.date]:
    """Every event date a person could mean in `text`, in order of appearance."""
    t = text.lower()
    found: list[tuple[int, dt.date]] = []

    def add(pos, d):
        if d:
            found.append((pos, d))

    for m in re.finditer(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t):
        try:
            add(m.start(), dt.date(int(m[1]), int(m[2]), int(m[3])))
        except ValueError:
            pass
    for m in re.finditer(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s*(20\d\d))?", t):
        mon, day, year = MONTHS[m[1][:3]], int(m[2]), m[3]
        if year:
            try:
                add(m.start(), dt.date(int(year), mon, day))
            except ValueError:
                pass
        else:
            add(m.start(), _future(mon, day, today))
    for m in re.finditer(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}(?:,?\s*(20\d\d))?", t):
        mon, day, year = MONTHS[m[2][:3]], int(m[1]), m[3]
        if year:
            try:
                add(m.start(), dt.date(int(year), mon, day))
            except ValueError:
                pass
        else:
            add(m.start(), _future(mon, day, today))
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t):
        mon, day, year = int(m[1]), int(m[2]), m[3]
        if not (1 <= mon <= 12):
            continue
        if year:
            y = int(year) + (2000 if len(year) == 2 else 0)
            try:
                add(m.start(), dt.date(y, mon, day))
            except ValueError:
                pass
        else:
            add(m.start(), _future(mon, day, today))
    for m in re.finditer(r"\btomorrow\b", t):
        add(m.start(), today + dt.timedelta(days=1))
    for m in re.finditer(r"\bin\s+(\d+|" + "|".join(NUM_WORDS) + r")\s+(day|week)s?\b", t):
        n = int(m[1]) if m[1].isdigit() else NUM_WORDS[m[1]]
        add(m.start(), today + dt.timedelta(days=n * (7 if m[2] == "week" else 1)))
    for m in re.finditer(r"\b(next|this|on)?\s*(" + "|".join(WEEKDAYS) + r")\b", t):
        target = WEEKDAYS.index(m[2])
        ahead = (target - today.weekday()) % 7 or 7          # strictly after today
        d = today + dt.timedelta(days=ahead)
        week_end = today + dt.timedelta(days=6 - today.weekday())  # this Sunday
        if m[1] == "next" and d <= week_end:
            d += dt.timedelta(days=7)
        add(m.start(), d)

    out = []
    for _, d in sorted(found, key=lambda x: x[0]):
        if d not in out:
            out.append(d)
    return out


_AMT = re.compile(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*([km])?\b|\b(\d[\d,]*(?:\.\d+)?)\s*([km])?\s*(?:dollars|usd|bucks)\b", re.I)


def _to_num(digits: str, suffix: str | None) -> float:
    v = float(digits.replace(",", ""))
    if suffix and suffix.lower() == "k":
        v *= 1000
    elif suffix and suffix.lower() == "m":
        v *= 1_000_000
    return v


def find_amounts(text: str) -> list[tuple[int, int, float]]:
    """Dollar amounts as (start, end, value): "$3,500", "$3.5k", "600 dollars"."""
    out = []
    for m in _AMT.finditer(text):
        digits, suf = (m[1], m[2]) if m[1] else (m[3], m[4])
        out.append((m.start(), m.end(), _to_num(digits, suf)))
    return out


def numbers_in(text: str) -> set[float]:
    """Every number written in the text (dollars, counts, '3.5k', 'four')."""
    nums = {v for _, _, v in find_amounts(text)}
    for m in re.finditer(r"\b(\d[\d,]*(?:\.\d+)?)\s*([km])?\b", text, re.I):
        try:
            nums.add(_to_num(m[1], m[2]))
            nums.add(float(m[1].replace(",", "")))
        except ValueError:
            pass
    for w, n in NUM_WORDS.items():
        if re.search(rf"\b{w}\b", text, re.I):
            nums.add(float(n))
    return nums


CATEGORY_WORDS = [
    ("venue", r"room|hall|ballroom|venue|space|rental|auditorium|theater|theatre|lawn"),
    ("food", r"food|catering|cater|pizza|dinner|lunch|snack|drink|meal|restaurant|boba|dessert"),
    ("entertainment", r"\bdj\b|band|performer|speaker|artist|music|sound|photographer|entertainment"),
    ("marketing", r"flyer|poster|marketing|ads?\b|banner|print"),
    ("supplies", r"decor|decoration|supplies|shirt|t-shirt|prize|lights|lighting|table|chair|equipment"),
]

KNOWN_VENUES = [
    r"tcc (?:grand )?ballroom", r"grand ballroom", r"ronald tutor campus center(?: \d+)?", r"\btcc\b(?: \d+)?",
    r"seeley g\.? mudd(?: \d+)?", r"\bsgm(?: \d+)?", r"bovard auditorium", r"doheny library", r"alumni park",
    r"mccarthy quad", r"trousdale", r"taper hall(?: \d+)?", r"\bthh(?: \d+)?", r"leavey library", r"wallis annenberg hall",
    r"town and gown", r"fertitta hall", r"\bvkc(?: \d+)?", r"\bsal(?: \d+)?",
]


def _category(item: str) -> str:
    for cat, pat in CATEGORY_WORDS:
        if re.search(pat, item, re.I):
            return cat
    return "other"


def _yes(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.I))


def _no(pattern: str, text: str) -> bool:
    """'no dancing', 'not selling', 'without tickets', 'free food'."""
    return bool(re.search(r"\b(no|not|without|won'?t|don'?t|isn'?t|aren'?t|never)\b[^.,;]{0,25}(" + pattern + ")", text, re.I))


# food and drink words (singular or plural), for "food served" and "selling food"
FOOD = (r"food|catering|catered|cater|pizzas?|dinners?|lunch(?:es)?|breakfast|brunch|snacks?|refreshments?|meals?|"
        r"boba|restaurant|popcorn|cookies?|baked goods|cupcakes?|cakes?|brownies?|donuts?|doughnuts?|pastr(?:y|ies)|"
        r"coffee|tea|drinks?|desserts?|tacos?|bbq|barbecue|ice cream|food trucks?|plates|bake sale")
_SELLS_FOOD = rf"\bsell\w*\s+(?:[\w']+\s+){{0,2}}(?:{FOOD})\b"
# a date at the end of the name: 'Bake sale Jan 20' -> 'Bake sale'
_DATE_IN_NAME = re.compile(rf"\s+(?:{_MON}\s*\d|\d{{1,2}}/\d|20\d\d-\d|(?:next|this)\s+\w+day\b|tomorrow\b|tonight\b).*$", re.I)


def rule_extract(text: str, today: dt.date, question: str | None = None) -> dict:
    """Best-effort extraction with plain regex. Only sets what it actually finds."""
    t = text.strip()
    low = t.lower()
    ev: dict = {}

    # name: 'Diwali Night on Dec 12...' -> text before the first ' on|at|in|is ' or comma
    m = re.match(r"\s*(?:our |the |a |an )?([A-Z][\w'&\- ]{2,40}?)(?=\s+(?:on|at|in|is|will|this|next)\b|[,.:(])", t)
    if m and not question:
        name = _DATE_IN_NAME.sub("", m[1].strip())
        if name:
            ev["name"] = name

    dates = find_dates(t, today)
    if dates:
        ev["date"] = dates[0].isoformat()

    # attendance
    m = re.search(r"(\d[\d,]*)\s*(?:\+\s*)?(?:people|attendees|guests|students|ppl|persons|members|folks)", low) \
        or re.search(r"(?:expect(?:ing)?|about|around|~)\s*(\d[\d,]*)\b(?!\s*(?:dollars|k\b|/|-))", low)
    if m:
        ev["attendance"] = int(m[1].replace(",", ""))

    # venue
    for pat in KNOWN_VENUES:
        m = re.search(pat, t, re.I)
        if m:
            ev.setdefault("venue", {})["name"] = m[0].strip().title().replace("Tcc", "TCC").replace("Sgm", "SGM").replace("Thh", "THH").replace("Vkc", "VKC").replace("Sal", "SAL")
            ev["venue"]["on_campus"] = True
            break
    else:
        m = re.search(r"\b(?:in|at)\s+(?:the\s+)?([A-Z][\w'&]*(?:\s+[A-Z0-9][\w'&]*){0,4})", t)
        if m and not re.match(r"(?:" + "|".join(MONTHS) + r")", m[1].lower()):
            ev.setdefault("venue", {})["name"] = m[1].strip()
    if _yes(r"off[- ]campus|restaurant venue|at a hotel|downtown|in (?:santa monica|pasadena|hollywood|koreatown)", low):
        ev.setdefault("venue", {})["on_campus"] = False
    elif _yes(r"on[- ]campus", low):
        ev.setdefault("venue", {})["on_campus"] = True
    if _yes(r"(?:not|isn'?t|aren'?t|haven'?t)\s+(?:yet\s+)?(?:booked|confirmed|reserved)|not booked|tbd|pending", low):
        ev.setdefault("venue", {})["confirmed"] = False
    elif _yes(r"\b(?:booked|confirmed|reserved)\b", low):
        ev.setdefault("venue", {})["confirmed"] = True

    # features
    if _yes(r"danc|\bdj\b|dance floor|garba|bhangra", low):
        ev["dancing"] = not _no(r"danc", low)
    if _yes(r"ticket|entry fee|admission|sell|selling|charge \$|fundrais", low):
        ev["ticket_sales"] = not _no(r"ticket|sell|charg|admission", low) or _yes(r"sell(?:ing)? tickets", low)
    if _yes(rf"\b(?:{FOOD})\b", low):
        food = ev.setdefault("food", {})
        food["served"] = True
        food["sold"] = (_yes(_SELLS_FOOD + rf"|\bbake sale\b|\bfood sales?\b|\b(?:{FOOD})\s+(?:for|at)\s+\$|sell[^.]{{0,30}}\bfood\b", low)
                        and not _no(_SELLS_FOOD, low)  # 'not selling food'
                        and not _yes(r"free food|food (?:is|will be) free", low))
        if _yes(r"usc hospitality", low):
            food["vendor"], food["vendor_approved"] = "USC Hospitality", True
        else:
            m = re.search(r"(?:from|by|catered by)\s+(?:a\s+)?([\w' ]{3,30}?(?:restaurant|catering|caterer|kitchen|grill|cafe))", low)
            if m:
                food["vendor"] = m[1].strip().capitalize()
            if _yes(r"approved vendor", low) and not _no(r"approved", low):
                food["vendor_approved"] = True

    # funding
    if _yes(r"\bgsg\b|graduate student government", low):
        ev["funding_source"] = "GSG"
    elif _yes(r"\busg\b|undergraduate student government", low):
        ev["funding_source"] = "USG"
    elif _yes(r"no (?:usg |gsg )?funding|self[- ]funded|not asking", low):
        ev["funding_source"] = "none"

    amounts = find_amounts(t)
    for s, e, v in amounts:
        before = low[max(0, s - 40):s]
        if (re.search(r"(ask|request|need|want|apply|applying)\w*\b[^.$]{0,25}$|for\s*$", before)
                and re.search(r"usg|gsg|fund", low[max(0, s - 60):e + 20])) \
                or re.search(r"\b(?:usg|gsg)\b(?:\s+(?:funding|grant|request))?\s*[:=-]?\s*$", before):  # 'GSG $2,000'
            ev["amount_requested"] = v
            break

    # budget lines: '<item> $X', '<item>: $X', '$X for <item>', '<item> (~$X)'
    used, lines = set(), []
    for s, e, v in amounts:
        if ev.get("amount_requested") == v and v not in used and re.search(r"(ask|request|usg|gsg)", low[max(0, s - 40):s]):
            used.add(v)
            continue
        # a ticket/entry price is income, not a cost: '$20 each', 'tickets at $20'
        if re.match(r"\s*(?:each|per\s+(?:person|ticket|head|guest)|a\s+(?:ticket|head|person)|/\s*(?:ticket|person|head))\b", low[e:]) \
                or re.search(r"(?:ticket|admission|entry|cover|door)s?\s*(?:price|fee|charge)?\s*(?:at|for|are|is|cost|costs|of)?\s*$", low[max(0, s - 40):s]):
            continue
        after = re.match(r"\s*(?:for|on)\s+(?:the\s+|a\s+)?([A-Za-z][\w' ]{1,30}?)(?=[,.;)]|\s+and\b|$)", t[e:])
        # words just before the amount, cut at a sentence/list break and never mid-word
        window = re.split(r"[,.;:()]|\band\b", t[max(0, s - 40):s])[-1]
        if s > 40 and not re.match(r"\W", t[s - 41]):
            window = re.sub(r"^\S*\s*", "", window)
        before = re.sub(r"\s*(?:costs?|is|was|will be|about|around|=|-|~)?\s*~?\s*$", "", window.strip())
        before = " ".join(re.findall(r"[A-Za-z][\w']*", before)[-5:])
        item = (after[1] if after else before).strip()
        item = re.sub(r"^(?:(?:and|the|a|an|our|plus|costs|cost|budget|with|including|free|paid)\s+)+", "", item, flags=re.I)
        if not item or re.search(r"usg|gsg|this year|received|got|total|so far|ask|request", item, re.I):
            continue
        lines.append({"item": item[0].upper() + item[1:], "category": _category(item), "amount": v,
                      "quote_attached": _yes(r"\bquotes? (?:attached|in hand)|have (?:a |the )?quotes?", low) and not _no(r"quote", low)})
    if lines:
        ev["budget_lines"] = lines

    # org history
    m = re.search(r"(\d+|" + "|".join(NUM_WORDS) + r")\s+(?:\w+\s+){0,3}(?:funded\s+)?events?\s+(?:\w+\s+){0,3}(?:funded|this semester)", low) \
        or re.search(r"funded\s+(\d+|" + "|".join(NUM_WORDS) + r")\s+(?:of our\s+)?events", low)
    if m:
        ev.setdefault("org", {})["funded_events_this_semester"] = int(m[1]) if m[1].isdigit() else NUM_WORDS[m[1]]
    for s, e, v in amounts:
        if re.search(r"(received|got|gotten|already|so far|this year|total)", low[max(0, s - 40):e + 25]) and v != ev.get("amount_requested"):
            ev.setdefault("org", {})["usg_received_this_year"] = v
            break

    if _yes(r"funds? (?:are |is )?(?:running |getting )?low|low on funds|running out of (?:usg )?(?:money|funds)", low):
        ev.setdefault("org", {})["usg_funds_low"] = True
    if _yes(r"co-?funded|also funded by|(?:another|other) (?:usc )?(?:office|department|school) (?:is )?(?:also )?(?:funding|paying)", low):
        ev.setdefault("org", {})["other_university_funding"] = True

    # a bare answer to one of the engine's questions ("300", "Dec 12", "$2,500")
    if question:
        q = question.lower()
        bare = re.fullmatch(r"\s*~?\$?\s*(\d[\d,]*(?:\.\d+)?)\s*([km])?\s*\.?\s*", t, re.I)
        if "how many people" in q and "attendance" not in ev and bare:
            ev["attendance"] = int(_to_num(bare[1], bare[2]))
        elif "how much are you requesting" in q and "amount_requested" not in ev and bare:
            ev["amount_requested"] = _to_num(bare[1], bare[2])
        elif "where is it" in q and "venue" not in ev and t:
            ev["venue"] = {"name": t.split(",")[0].strip().rstrip("."),
                           **({"on_campus": False} if _yes(r"off[- ]campus", low) else {})}
    return ev


# ------------------------------------------------------------------ verify + merge
def _close(v, nums: set[float]) -> bool:
    try:
        return any(abs(float(v) - n) < 0.51 for n in nums)
    except (TypeError, ValueError):
        return False


def verify(new: dict, old: dict, text: str, today: dt.date) -> tuple[dict, list[str]]:
    """Drop any date/number the model returned that isn't in the text (or already known).
    Returns (cleaned, notes) where notes are questions to ask instead."""
    new = json.loads(json.dumps(new))
    notes: list[str] = []
    nums = numbers_in(text)
    dates = {d.isoformat() for d in find_dates(text, today)}

    if new.get("date") and new["date"] != old.get("date"):
        if dates and new["date"] not in dates:
            new["date"] = sorted(dates)[0] if len(dates) == 1 else None
        elif not dates:
            new["date"] = None
    for key in ("attendance", "amount_requested"):
        v = new.get(key)
        if v is not None and v != old.get(key) and not _close(v, nums):
            new[key] = None
    org, old_org = new.get("org") or {}, old.get("org") or {}
    for key in ("funded_events_this_semester", "usg_received_this_year"):
        v = org.get(key)
        if v is not None and v != old_org.get(key) and not _close(v, nums):
            org[key] = None

    if isinstance(new.get("budget_lines"), list):
        old_lines = {(str(l.get("item", "")).lower(), float(l.get("amount") or 0)) for l in old.get("budget_lines") or []}
        kept = []
        for ln in new["budget_lines"]:
            if not isinstance(ln, dict):
                continue
            key = (str(ln.get("item", "")).lower(), float(ln.get("amount") or 0) if _is_num(ln.get("amount")) else -1)
            if key in old_lines or _close(ln.get("amount"), nums):
                if ln.get("category") not in ("venue", "food", "entertainment", "supplies", "marketing", "other"):
                    ln["category"] = _category(str(ln.get("item", "")))
                kept.append(ln)
            else:
                notes.append(f"How much will \"{ln.get('item') or 'that item'}\" cost?")
        new["budget_lines"] = kept
    return new, notes


def _is_num(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def deep_merge(old: dict, new: dict) -> dict:
    """old <- new, skipping nulls; nested dicts merge; non-empty lists replace."""
    out = dict(old)
    for k, v in (new or {}).items():
        if v is None or k.startswith("_") or k == "questions":
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        elif isinstance(v, list) and not v and out.get(k):
            continue
        else:
            out[k] = v
    return out


def _today(event: dict | None) -> dt.date:
    try:
        return dt.date.fromisoformat(str((event or {}).get("as_of"))[:10])
    except ValueError:
        return dt.date.today()


def _question_in(text: str) -> str | None:
    """Follow-up answers are sent as 'Q: <question>\nA: <answer>'."""
    m = re.match(r"\s*Q:\s*(.+?)\s*\n\s*A:\s*(.*)", text, re.S)
    return m[1] if m else None


@router.post("/extract")
def extract(body: ExtractIn):
    old = body.event or {}
    today = _today(old)
    question = _question_in(body.text)
    answer = re.sub(r"^\s*Q:.*?\n\s*A:\s*", "", body.text, flags=re.S) if question else body.text

    model_qs: list[str] = []
    new: dict = {}
    if llm.available():
        try:
            user = f"TODAY: {WEEKDAYS[today.weekday()].title()} {today.isoformat()}\n"
            if old:
                user += "CURRENT EVENT:\n" + json.dumps({k: v for k, v in old.items() if k not in ("tracking", "id")}) + "\n"
            user += f"TEXT:\n{body.text}"
            out = llm.ask_json(EXTRACT_SYSTEM, user)
            if isinstance(out, dict):
                model_qs = [q for q in out.get("questions") or [] if isinstance(q, str)][:3]
                new = out
        except Exception:  # keep the demo alive
            new = {}
    # code-only reading fills anything the model missed (or everything, with no key)
    new, notes = verify(new, old, answer, today)  # drop what the model made up...
    new = deep_merge(rule_extract(answer, today, question), new)  # ...then let code fill the gaps

    merged = deep_merge(old, new)
    if "date" in old and new.get("date") is None and old.get("date"):
        merged["date"] = old["date"]
    ev = engine.normalize(merged)
    questions = engine.missing_questions(ev)
    for q in notes + model_qs:
        if q not in questions and len(questions) < 6:
            questions.append(q)
    return {"event": ev, "questions": questions}
