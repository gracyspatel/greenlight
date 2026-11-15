"""Owner: Split B. Endpoint: POST /pack  CheckResponse -> [{approval_id, system, link, draft, by, ...}].

Drafts the text an officer pastes into each system (EngageSC funding form, TES venue
request, UEPA...). Every draft starts from a code-built template that uses only facts
from the event. If an LLM key is set, the model may polish the wording; the polished
version is thrown away if it contains any number that isn't in the facts.
`by` is "ai" when the polished text was used, "template" otherwise.
"""
from __future__ import annotations

import re

from fastapi import APIRouter

from .. import llm

router = APIRouter(tags=["pack"])

PURPOSE = "[One or two sentences: what the event is and who it's for]"
_PLACEHOLDER = re.compile(r"\[[^\]]+\]")


def _money(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "$0"


def _yn(v) -> str:
    return "Yes" if v else "No"


def facts(ev: dict) -> dict:
    """Plain-text facts from the event. The only facts a draft may use."""
    venue, food, org = ev.get("venue") or {}, ev.get("food") or {}, ev.get("org") or {}
    lines = ev.get("budget_lines") or []
    budget = "\n".join(
        f"  - {l.get('item') or '(item)'} ({l.get('category', 'other')}): {_money(l.get('amount'))}"
        f"{', quote attached' if l.get('quote_attached') else ', quote NOT attached'}"
        for l in lines) or "  - (no budget lines)"
    total = sum(float(l.get("amount") or 0) for l in lines)
    food_txt = "No food"
    if food.get("served") or food.get("sold"):
        food_txt = (("Sold" if food.get("sold") else "Served free")
                    + f" by {food.get('vendor') or '(vendor not named)'}"
                    + (" (USC-approved vendor)" if food.get("vendor_approved") else ""))
    return {
        "name": ev.get("name") or "Untitled event",
        "date": ev.get("date") or "(date not set)",
        "venue": venue.get("name") or "(venue not set)",
        "venue_status": "confirmed" if venue.get("confirmed") else "not yet confirmed",
        "on_campus": _yn(venue.get("on_campus", True)),
        "attendance": str(ev.get("attendance") or "(not set)"),
        "food": food_txt,
        "dancing": _yn(ev.get("dancing")),
        "tickets": _yn(ev.get("ticket_sales")),
        "funding": ev.get("funding_source") or "none",
        "requested": _money(ev.get("amount_requested")),
        "budget": budget,
        "total": _money(total),
        "funded_events": str(org.get("funded_events_this_semester", 0)),
    }


def template(approval: dict, f: dict) -> str:
    aid = approval["id"]
    head = f"Event: {f['name']}\nDate: {f['date']}\nVenue: {f['venue']} ({f['venue_status']})\nExpected attendance: {f['attendance']}"
    if aid in ("usg_funding", "gsg_funding"):
        quotes = "\n\nVendor quotes: attached for each line above." if aid == "gsg_funding" else ""
        return (f"{head}\n\nPurpose: {PURPOSE}\n\nAmount requested from {f['funding']}: {f['requested']}\n"
                f"Itemized budget (total {f['total']}):\n{f['budget']}\n\nFood: {f['food']}\n"
                f"Ticket sales: {f['tickets']}{quotes}")
    if aid == "venue_request":
        return (f"{head}\n\nRoom requested: {f['venue']}\nEvent description: {PURPOSE}\n"
                f"Food: {f['food']}\nDancing: {f['dancing']}\nTicket sales: {f['tickets']}\n"
                "Setup needs: [tables, chairs, AV, stage]")
    if aid == "uepa":
        return (f"{head}\n\nOn campus: {f['on_campus']}\nDescription: {PURPOSE}\nFood: {f['food']}\n"
                f"Dancing: {f['dancing']}\nTicket sales: {f['tickets']}\n"
                "Venue confirmation: [attach the Trojan Event Services confirmation]")
    if aid == "catering":
        return f"{head}\n\nFood: {f['food']}\nService style: [buffet / boxed / plated]"
    if aid in ("fundraising_ca", "fundraising_bh"):
        return (f"{head}\n\nTicket sales: {f['tickets']}\nFood: {f['food']}\n"
                "Ticket price and where sales happen: [fill in]\nWhere the money goes: [fill in]")
    if aid in ("social_dance_start", "social_dance_form"):
        return (f"{head}\n\nDancing: {f['dancing']}\nDescription: {PURPOSE}\n"
                "Security / staffing plan: [fill in]")
    return f"{head}\n\nDescription: {PURPOSE}"


POLISH_SYSTEM = """You help a USC student club officer fill in approval forms.
For each form you get a draft built from the club's facts. Rewrite each draft so it reads
clearly and professionally, as text the officer will paste into that form.

Strict rules:
- Use ONLY the facts in the draft. Never add numbers, dollar amounts, dates, rooms,
  vendors, rules or promises that are not in the draft.
- Keep every number exactly as written.
- Keep every [bracketed placeholder] as is, so the officer knows what to fill in.
- Keep the field labels (e.g. "Date:", "Amount requested"). Plain text, no markdown headings.

Return JSON: {"<approval_id>": "<rewritten draft>", ...} with the same keys you were given."""


def _polish(drafts: dict[str, str], facts_text: str) -> dict[str, str]:
    """Returns {approval_id: polished} for the drafts that passed the number check."""
    if not llm.available() or not drafts:
        return {}
    try:
        user = "\n\n".join(f"### {aid}\n{text}" for aid, text in drafts.items())
        out = llm.ask_json(POLISH_SYSTEM, user, max_tokens=3000)
    except Exception:
        return {}
    good = {}
    for aid, text in (out or {}).items():
        text = str(text or "").strip()
        # every [placeholder] must survive word for word: a dropped one means the model
        # deleted it or filled in something it made up (e.g. an invented purpose)
        if aid in drafts and text and llm.grounded(text, drafts[aid], facts_text) \
                and set(_PLACEHOLDER.findall(drafts[aid])) <= set(_PLACEHOLDER.findall(text)):
            good[aid] = text
    return good


@router.post("/pack")
def pack(check_result: dict):
    ev = check_result.get("event", {}) or {}
    f = facts(ev)
    approvals = check_result.get("approvals", []) or []
    drafts = {a["id"]: template(a, f) for a in approvals}
    polished = _polish(drafts, "\n".join(f.values()))
    return [
        {"approval_id": a["id"], "name": a.get("name", a["id"]), "system": a.get("system", ""),
         "link": a.get("link", ""), "deadline_label": a.get("deadline_label", ""),
         "draft": polished.get(a["id"], drafts[a["id"]]),
         "by": "ai" if a["id"] in polished else "template"}
        for a in approvals
    ]
