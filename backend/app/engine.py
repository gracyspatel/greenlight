"""Greenlight rules engine.

The AI understands, the rules decide: every pass/fail in here is plain code
reading rules.json. No model calls happen in this file.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "data"
RULES = json.loads((BASE / "rules.json").read_text())
CAL = json.loads((BASE / "calendar.json").read_text())

APPROVALS = {a["id"]: a for a in RULES["approvals"]}
GENERIC = RULES["generic"]
# Food vendor list. SYNTHETIC demo data (see its _note) until the team gets USG's real list.
_VF = BASE / "demo_vendors.json"
VENDOR_DATA = json.loads(_VF.read_text()) if _VF.exists() else {"vendors": []}
VENDORS = VENDOR_DATA["vendors"]
# warning = a risk factor the club can't change (funds running low, a break in the window...).
# It is shown, but it never blocks Ready.
LEVEL_RANK = {"ready": 0, "warning": 1, "risk": 2, "reject": 3}
LEVEL_LABEL = {"ready": "Ready", "warning": "Warning", "risk": "At risk", "reject": "Will be rejected"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BREAKS = [
    (b["name"], dt.date.fromisoformat(b["start"]), dt.date.fromisoformat(b["end"]))
    for b in CAL["breaks"]
]


# ---------------------------------------------------------------- helpers
def _date(v):
    if not v:
        return None
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fmt(d: dt.date | None) -> str:
    # %-d isn't supported on Windows, so build the day number by hand.
    return (d.strftime("%a %b ") + str(d.day) + d.strftime(", %Y")) if d else "—"


def _break_days(start: dt.date, end: dt.date):
    """Days in [start, end) that fall in a break, and the break names touched."""
    days, names = 0, set()
    d = start
    while d < end:
        for name, bs, be in BREAKS:
            if bs <= d <= be:
                days += 1
                names.add(name)
                break
        d += dt.timedelta(days=1)
    return days, names


def academic_weeks_back(event: dt.date, weeks: int, weekday: str):
    """Count back `weeks` academic weeks (a 7-day span mostly inside a break
    doesn't count), then go back to the given weekday."""
    d, counted, touched = event, 0, set()
    for _ in range(80):  # guard
        if counted >= weeks:
            break
        start = d - dt.timedelta(days=7)
        bdays, names = _break_days(start, d)
        touched |= names
        if bdays < 4:
            counted += 1
        d = start
    target = WEEKDAYS.index(weekday)
    while d.weekday() != target:
        d -= dt.timedelta(days=1)
    return d, sorted(touched)


def deadline_for(approval: dict, event_date: dt.date):
    lead = approval.get("lead")
    if not lead:
        return None, []
    if "academic_weeks" in lead:
        return academic_weeks_back(event_date, lead["academic_weeks"], lead.get("weekday", "Wednesday"))
    return event_date - dt.timedelta(days=lead["days"]), []


def break_on(d: dt.date | None):
    """(name, start, end) of the break that day falls in, else None."""
    if d:
        for b in BREAKS:
            if b[1] <= d <= b[2]:
                return b
    return None


def earliest_event_date(approval: dict, today: dt.date):
    """Earliest event date whose deadline for this approval is still open (never inside a break)."""
    d = today
    for _ in range(400):
        dl, _ = deadline_for(approval, d)
        if (dl is None or dl >= today) and not break_on(d):
            return d
        d += dt.timedelta(days=1)
    return None


# ---------------------------------------------------------------- normalize
# ---------------------------------------------------------------- vendors
def _vnorm(s: str) -> str:
    s = (s or "").lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"\(.*?\)", " ", s)                     # "(Catering2Go)"
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find_vendor(text: str):
    """The vendor-list entry named in `text` (longest name/alias that appears), or None."""
    t = f" {_vnorm(text)} "
    if not t.strip():
        return None
    best, best_len = None, 0
    for v in VENDORS:
        for cand in [_vnorm(v["name"])] + [_vnorm(a) for a in v.get("aliases", [])]:
            if cand and f" {cand} " in t and len(cand) > best_len:
                best, best_len = v, len(cand)
    return best


def food_vendor_of(ev: dict):
    """(name as written, list entry or None). Uses food.vendor, else a food budget line's item."""
    named = (ev["food"].get("vendor") or "").strip()
    if named:
        return named, find_vendor(named)
    for l in ev["budget_lines"]:
        if l["category"] == "food":
            v = find_vendor(l["item"])
            if v:
                return v["name"], v
    return "", None


def suggest_vendors(n: int = 3, cap: float = 35) -> str:
    ok = [v["name"] for v in VENDORS if v["usg_vendor"] and v["catering_approved"] and v["health_permit"]
          and v["insurance"] and v.get("per_person", 0) <= cap and v.get("location") != "Off campus"]
    return ", ".join(ok[:n])


def normalize(ev: dict) -> dict:
    ev = dict(ev or {})
    ev.setdefault("name", "Untitled event")
    venue = dict(ev.get("venue") or {})
    venue.setdefault("name", "")
    venue.setdefault("on_campus", True)
    venue.setdefault("confirmed", False)
    ev["venue"] = venue
    food = dict(ev.get("food") or {})
    for k in ("served", "sold", "vendor_approved"):
        food[k] = bool(food.get(k, False))
    food["served"] = food["served"] or food["sold"]  # selling food means food is served
    food.setdefault("vendor", "")
    ev["food"] = food
    ev["dancing"] = bool(ev.get("dancing", False))
    ev["ticket_sales"] = bool(ev.get("ticket_sales", False))
    src = str(ev.get("funding_source") or "none").upper()
    ev["funding_source"] = src if src in ("USG", "GSG") else "none"
    ev["amount_requested"] = _num(ev.get("amount_requested"))
    lines = []
    for ln in ev.get("budget_lines") or []:
        lines.append({
            "item": ln.get("item", ""),
            "category": (ln.get("category") or "other").lower(),
            "amount": _num(ln.get("amount")),
            "quote_attached": bool(ln.get("quote_attached", False)),
        })
    ev["budget_lines"] = lines
    org = dict(ev.get("org") or {})
    org["funded_events_this_semester"] = int(_num(org.get("funded_events_this_semester")))
    org["usg_received_this_year"] = _num(org.get("usg_received_this_year"))
    for k in ("other_university_funding", "past_misuse", "usg_funds_low"):
        org[k] = bool(org.get(k, False))
    ev["org"] = org
    # vendor list lookup: a listed vendor's approval comes from the list, not from a checkbox
    named, v = food_vendor_of(ev)
    ev["food"]["vendor_match"] = v["name"] if v else None
    if v and ev["food"]["served"]:
        ev["food"]["vendor"] = named
        ev["food"]["vendor_approved"] = bool(v["catering_approved"])
    # {approval_id: {"status": ..., "submitted_on": "YYYY-MM-DD" (optional)}}
    ev["tracking"] = {k: dict(v) if isinstance(v, dict) else {} for k, v in (ev.get("tracking") or {}).items()}
    return ev


def features(ev: dict) -> dict:
    return {
        "funding_usg": ev["funding_source"] == "USG",
        "funding_gsg": ev["funding_source"] == "GSG",
        "on_campus_venue": bool(ev["venue"].get("on_campus")),
        "food": ev["food"]["served"] or ev["food"]["sold"],
        "ticket_sales": ev["ticket_sales"],
        "dancing": ev["dancing"],
    }


def missing_questions(ev: dict) -> list[str]:
    q = []
    if not _date(ev.get("date")):
        q.append("What date is the event?")
    if not ev["venue"].get("name"):
        q.append("Where is it being held, and is that on campus?")
    if not ev.get("attendance"):
        q.append("About how many people do you expect?")
    if ev["funding_source"] != "none" and not ev["budget_lines"]:
        q.append("What are the budget lines (item, category, amount)?")
    if ev["funding_source"] != "none" and not ev["amount_requested"]:
        q.append("How much are you requesting?")
    return q


# ---------------------------------------------------------------- checks
def _flag(rule_id, level, message, text, source, fix):
    return {"rule_id": rule_id, "level": level, "message": message,
            "rule_text": text, "source": source, "fix": fix}


def run_rule(rule: dict, ev: dict):
    c, p, org = rule["check"], rule["params"], ev["org"]
    lines = ev["budget_lines"]
    if c == "usg_event_cap":
        n = org["funded_events_this_semester"] + 1
        if n > p["max_events"]:
            return rule["level"], f"This would be funded event #{n}; the limit is {p['max_events']}.", rule["fix"].format(n=n)
    elif c == "usg_annual_cap":
        total = org["usg_received_this_year"] + ev["amount_requested"]
        cap = p["cap"]
        if total > cap:  # exactly the cap is allowed ("maximum of $8,000")
            over = total - cap
            return "reject", f"${total:,.0f} for the year breaks the ${cap:,.0f} cap.", rule["fix"].format(total=total, over=over)
        if total >= cap * p["near_ratio"]:
            return "warning", f"${total:,.0f} for the year is close to the ${cap:,.0f} cap.", "Expect closer review. Keep this year's other requests small."
    elif c == "usg_venue_cap":
        venue = sum(l["amount"] for l in lines if l["category"] == "venue")
        if venue > p["cap"]:
            over = venue - p["cap"]
            return rule["level"], f"Venue costs of ${venue:,.0f} are over the ${p['cap']:,.0f} maximum.", rule["fix"].format(venue=venue, over=over)
    elif c == "vendor_quotes":
        missing = [l["item"] or "(unnamed line)" for l in lines if not l["quote_attached"]]
        if missing:
            return rule["level"], f"{len(missing)} budget line(s) have no vendor quote.", rule["fix"].format(items=", ".join(missing))
    elif c == "food_vendor":
        f = ev["food"]
        if f["sold"] and not f["vendor_approved"]:
            v = f["vendor"] or "your vendor"
            return rule["level"], f"Food is being sold, and {v} isn't marked as an approved vendor.", rule["fix"]
    elif c in ("usg_vendor_list", "food_cap", "vendor_docs", "catering_vendor"):
        return _vendor_rule(c, rule, ev)
    elif c == "venue_confirmed":
        if not ev["venue"].get("confirmed"):
            return rule["level"], "The venue isn't confirmed yet.", rule["fix"]
    elif c == "flag":
        if org.get(p["field"]):
            return rule["level"], rule["text"], rule["fix"]
    return None


def _vendor_rule(c: str, rule: dict, ev: dict):
    """Food vendor checks against the vendor list (demo_vendors.json)."""
    food, p = ev["food"], rule["params"]
    if not food["served"]:
        return None
    named, v = food_vendor_of(ev)
    food_lines = [l for l in ev["budget_lines"] if l["category"] == "food"]
    usg_pays_food = bool(food_lines)  # USG rules apply to the food it is asked to pay for
    who = named or "your food vendor"
    sug = suggest_vendors()

    if c == "usg_vendor_list" and usg_pays_food:
        if not named:
            return "risk", "No food vendor is named, so we can't check the USG vendor list.", \
                f"Name the vendor (e.g. {sug}) so we can check it."
        if not v or not v["usg_vendor"]:
            why = "isn't on the USG vendor list" if v else "isn't on our vendor list"
            return rule["level"], f"{who} {why}.", rule["fix"].format(vendor=who, suggest=sug)
    elif c == "food_cap" and usg_pays_food and ev.get("attendance"):
        total = sum(l["amount"] for l in food_lines)
        pp = total / float(ev["attendance"])
        if pp > p["cap"]:
            most = p["cap"] * float(ev["attendance"])
            return rule["level"], f"Food is ${pp:,.2f} per person, over the ${p['cap']:,.0f} maximum.", \
                rule["fix"].format(pp=pp, most=most, attendance=ev["attendance"])
    elif c == "vendor_docs" and usg_pays_food and v and v["usg_vendor"]:
        missing = [d for d, ok in (("health permit", v["health_permit"]),
                                   ("certificate of insurance", v["insurance"])) if not ok]
        if missing:
            return rule["level"], f"{v['name']} has no {' or '.join(missing)} on file.", \
                rule["fix"].format(vendor=v["name"], missing=" and ".join(missing))
    elif c == "catering_vendor" and not food["sold"] and named:  # sold food: the food_vendor rule
        if (v and not v["catering_approved"]) or (not v and not food["vendor_approved"]):
            return rule["level"], f"{who} isn't on the approved caterer list.", \
                rule["fix"].format(vendor=who, suggest=sug)
    return None


def _with_note(fix: str, approval: dict) -> str:
    """Greenlight's own lead-time choice (rules.json lead_note) goes in the fix, never in the quote."""
    note = approval.get("lead_note")
    return f"{fix} ({note})" if note else fix


def check(raw_event: dict, today: dt.date | None = None) -> dict:
    ev = normalize(raw_event)
    today = _date(ev.get("as_of")) or today or dt.date.today()
    event_date = _date(ev.get("date"))
    feats = features(ev)
    questions = missing_questions(ev)

    needed = [a for a in RULES["approvals"] if feats.get(a["trigger"])]
    needed_ids = {a["id"] for a in needed}
    results = []

    for a in needed:
        track = ev["tracking"].get(a["id"], {})
        status = track.get("status", "not_started")
        flags = []
        deadline, breaks = (deadline_for(a, event_date) if event_date else (None, []))
        days_left = (deadline - today).days if deadline else None
        done = status in ("submitted", "approved")
        # a submitted step still missed its deadline if it went in late (no date given: assume today)
        submitted_on = _date(track.get("submitted_on")) or today
        late = bool(deadline and status == "submitted" and submitted_on > deadline)

        # deadlines
        if late:
            g = GENERIC["deadline_passed"]
            flags.append(_flag(f"{a['id']}_deadline", g["level"],
                               f"Submitted after the deadline ({(submitted_on - deadline).days} day(s) late).",
                               a["text"], a["source"],
                               _with_note(g["fix"].format(deadline=fmt(deadline),
                                                          earliest=fmt(earliest_event_date(a, today))), a)))
        elif deadline and not done:
            if days_left < 0:
                earliest = earliest_event_date(a, today)
                g = GENERIC["deadline_passed"]
                flags.append(_flag(f"{a['id']}_deadline", g["level"],
                                   f"Deadline passed {-days_left} day(s) ago.",
                                   a["text"], a["source"],
                                   _with_note(g["fix"].format(deadline=fmt(deadline), earliest=fmt(earliest)), a)))
            elif days_left <= 7:
                g = GENERIC["deadline_soon"]
                flags.append(_flag(f"{a['id']}_deadline", g["level"],
                                   f"Due in {days_left} day(s).", a["text"], a["source"],
                                   _with_note(g["fix"].format(days=days_left, deadline=fmt(deadline)), a)))
        if breaks and not done:
            g = GENERIC["break_crossing"]
            flags.append(_flag(f"{a['id']}_breaks", g["level"],
                               "The deadline window crosses a break.", g["text"], a["source"],
                               g["fix"].format(breaks=", ".join(breaks))))
        # ordering: waiting on an earlier step is normal planning (shown via depends_on).
        # It's only a risk when this step was filed while its prerequisite isn't approved yet.
        for dep in a.get("depends_on", []):
            if dep in needed_ids and status == "submitted":
                dep_status = ev["tracking"].get(dep, {}).get("status", "not_started")
                if dep_status != "approved" and a["id"] != "uepa":  # uepa uses its own venue rule
                    g = GENERIC["depends_pending"]
                    flags.append(_flag(f"{a['id']}_order", g["level"],
                                       f"Filed before \"{APPROVALS[dep]['name']}\" was approved.",
                                       a["text"], a["source"],
                                       g["fix"].format(dep=APPROVALS[dep]["name"])))
        # specific rules
        for r in RULES["rules"]:
            if r["approval"] != a["id"]:
                continue
            out = run_rule(r, ev)
            if out:
                level, msg, fix = out
                flags.append(_flag(r["id"], level, msg, r["text"], r["source"], fix))
        if status == "returned":
            g = GENERIC["returned"]
            flags.append(_flag(f"{a['id']}_returned", g["level"], "Returned by the office.",
                               a["text"], a["source"], g["fix"]))

        if status == "approved":
            verdict = "ready"
            flags = []
        else:
            verdict = max((f["level"] for f in flags), key=LEVEL_RANK.get, default="ready")

        if late:
            color = "red"
        elif done:
            color = "done"
        elif deadline is None:
            color = "none"
        elif days_left < 0:
            color = "red"
        elif days_left <= 7:
            color = "yellow"
        else:
            color = "green"

        # most serious problem first inside each approval (stable: keeps rule order otherwise)
        flags.sort(key=lambda f: -LEVEL_RANK[f["level"]])

        results.append({
            "id": a["id"], "step": a.get("step", 99), "name": a["name"], "office": a["office"],
            "system": a["system"], "link": a["link"],
            "depends_on": [d for d in a.get("depends_on", []) if d in needed_ids],
            "deadline": deadline.isoformat() if deadline else None,
            "deadline_label": (fmt(deadline) + (f", {a['lead']['time'].replace('23:59', '11:59 PM')}" if a.get("lead", {}).get("time") else "")) if deadline else "No fixed lead time in our rulebook. Confirm with the office.",
            "days_left": days_left, "color": color, "status": status,
            "verdict": verdict, "verdict_label": LEVEL_LABEL[verdict], "flags": flags,
        })

    # the order an officer does things in (rules.json "step"), then by deadline
    results.sort(key=lambda r: (r["step"], r["deadline"] or "9999"))
    # the event day itself falls in a break: one flag, on the first step
    brk = break_on(event_date)
    if brk and results and results[0]["status"] != "approved":
        g, r0 = GENERIC["event_in_break"], results[0]
        name, bs, be = brk
        r0["flags"].append(_flag("event_in_breaks", g["level"], f"Your event falls in {name}.",
                                 g["text"].format(name=name, start=fmt(bs), end=fmt(be)), g["source"],
                                 g["fix"].format(name=name)))
        r0["flags"].sort(key=lambda f: -LEVEL_RANK[f["level"]])
        r0["verdict"] = max((f["level"] for f in r0["flags"]), key=LEVEL_RANK.get)
        r0["verdict_label"] = LEVEL_LABEL[r0["verdict"]]
    for i, r in enumerate(results, 1):
        r["order"] = i  # 1, 2, 3... as shown to the user
    worst = max((r["verdict"] for r in results), key=LEVEL_RANK.get, default="ready")
    overall = "ready" if worst == "warning" else worst  # warnings alone still mean Ready
    # Missing facts (date, venue, attendance, budget...) mean we can't call it Ready yet.
    # A reject always wins; otherwise a missing date or open questions mean "Needs info".
    needs_info = overall != "reject" and (not event_date or bool(questions))
    overall_label = "Needs info" if needs_info else LEVEL_LABEL[overall]

    return {
        "event": ev,
        "as_of": today.isoformat(),
        "features": feats,
        "questions": questions,
        "approvals": results,
        "verdict": "risk" if needs_info else overall,
        "verdict_label": overall_label,
        "counts": {k: sum(1 for r in results if r["verdict"] == k) for k in LEVEL_RANK},
        # every warning flag, even inside approvals that also have fixable problems
        "warnings": [{"approval_id": r["id"], "approval": r["name"], **f}
                     for r in results for f in r["flags"] if f["level"] == "warning"],
        "disclaimer": "Ready means your request meets every written rule we check. The final decision is still USG's.",
    }


if __name__ == "__main__":
    demos = json.loads((BASE / "demo_events.json").read_text())
    for d in demos:
        r = check(d)
        print(f"\n=== {d['name']}  ->  {r['verdict_label']}")
        for a in r["approvals"]:
            print(f"  [{a['verdict_label']:16}] {a['name']:45} {a['deadline_label']}")
            for f in a["flags"]:
                print(f"       - {f['message']}  FIX: {f['fix']}")
