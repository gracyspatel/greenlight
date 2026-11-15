# Contracts — the shapes everyone codes against

**Change these only after telling the whole team in the group chat.**
The source of truth is `backend/app/engine.py` (`normalize()` for input, `check()` for output).
Real examples: `data/demo_events.json` and `frontend/src/mock/check_responses.json`.

## Event (input to /check, output of /extract)
```json
{
  "name": "Diwali Night",
  "date": "2026-12-12",                 // YYYY-MM-DD
  "as_of": "2026-11-15",                // optional: pretend 'today' (use for demos)
  "venue": {"name": "TCC Grand Ballroom", "on_campus": true, "confirmed": false},
  "attendance": 300,
  "food": {"served": true, "sold": true, "vendor": "Local restaurant", "vendor_approved": false},
  "dancing": true,
  "ticket_sales": true,
  "funding_source": "USG",              // "USG" | "GSG" | "none"
  "amount_requested": 3500,
  "budget_lines": [{"item": "Grand Ballroom", "category": "venue", "amount": 4500, "quote_attached": false}],
  "org": {"funded_events_this_semester": 4, "usg_received_this_year": 5200,
          "other_university_funding": false, "past_misuse": false, "usg_funds_low": false},
  "tracking": {"venue_request": {"status": "submitted", "submitted_on": "2026-11-15"}}   // not_started|submitted|approved|returned
}
```
`tracking.*.submitted_on` is optional (YYYY-MM-DD; the Tracker sets it to `as_of` or today when you pick
"Submitted"). A submitted approval keeps its `*_deadline` flag ("Submitted after the deadline") if
`submitted_on` (or today, when missing) is after the deadline. Only "approved" clears flags.
`category` values: venue, food, entertainment, supplies, marketing, other.

## CheckResponse (output of /check)
```json
{
  "event": {...normalized event...},
  "as_of": "2026-11-15",
  "features": {"funding_usg": true, "on_campus_venue": true, "food": true, "ticket_sales": true, "dancing": true, "funding_gsg": false},
  "questions": ["What date is the event?"],
  "verdict": "ready|risk|reject",
  "verdict_label": "Ready|At risk|Will be rejected",
  "counts": {"ready": 1, "risk": 2, "reject": 5},
  "disclaimer": "Ready means your request meets every written rule we check. The final decision is still USG's.",
  "approvals": [{
    "id": "usg_funding", "name": "USG funding application", "office": "...", "system": "EngageSC", "link": "https://...",
    "depends_on": [], "deadline": "2026-10-28", "deadline_label": "Wed Oct 28, 2026, 11:59 PM",
    "days_left": -18, "color": "red|yellow|green|done|none", "status": "not_started",
    "verdict": "reject", "verdict_label": "Will be rejected",
    "flags": [{"rule_id": "usg_venue_cap", "level": "reject|risk", "message": "...", "fix": "...",
               "rule_text": "exact guideline text", "source": "https://..."}]
  }]
}
```

## Endpoints (all under /api)
| Method | Path | Owner | Body → Returns |
|---|---|---|---|
| POST | /extract | Split A | `{text, event?}` → `{event, questions}` |
| POST | /check | Split B | Event → CheckResponse |
| GET | /demo, /demo/{id} | Split B | list / one demo Event |
| POST | /explain | Split A | `{flag, event?}` → `{reason, fix, quote, source}` |
| POST | /pack | Split B | CheckResponse → `[{approval_id, system, link, draft}]` |
| GET | /reviewer/queue | Split B | → `[{id, name, date, requested, verdict, verdict_label, summary}]` |
| POST | /ask | Split B | `{question}` → `{answer, citations:[{title, source}]}` |
| POST | /reviewer/submit | Split B | `{event}` → `{ok, id}` (adds the event to the reviewer queue; in memory) |

**Levels:** `reject` (a rule is broken) · `risk` (the club can fix it) · `warning` (a risk factor the club
can't change, e.g. USG funds running low, a break in the deadline window, close to the yearly cap).
A flag or approval can be `"warning"` (label "Warning"). Warnings never block Ready: the overall `verdict`
is never `"warning"`. `counts` has `ready, warning, risk, reject` (per approval, by its worst flag), and the
response adds `warnings: [{approval_id, approval, ...flag}]`, listing every warning flag. `/calendar` days add
`notes` (warnings), which don't change the day's color.

`approvals` come in the order an officer does them (rules.json `step`, then deadline). Each approval
adds `step` and `order` (1, 2, 3… as shown). Inside an approval, `flags` are worst first. Show them in this order.

Optional extra fields (safe to ignore): `/pack` rows add `name, deadline_label, by` ("ai"|"template");
`/reviewer/queue` rows add `by, source` ("submitted"|"demo"), `counts, attendance, venue`; `/ask` adds `by`.

**Food vendors:** `GET /api/vendors` → `{synthetic, note, food_cap, vendors:[{name, location, type, cuisine,
usg_vendor, catering_approved, health_permit, insurance, per_person, notes}]}`. The list is SYNTHETIC demo data
(`data/demo_vendors.json`) until we get USG's real list, and the UI must say so. The engine matches `food.vendor`
(or a food budget line's item) to the list and adds `food.vendor_match` (the list name, or null). For a listed
vendor, `food.vendor_approved` comes from the list. Rules: `usg_food_vendor_list`, `usg_food_cap` ($35/person),
`usg_vendor_docs`, `catering_vendor`.
