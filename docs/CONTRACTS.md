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
  "tracking": {"venue_request": {"status": "submitted"}}   // not_started|submitted|approved|returned
}
```
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

`approvals` come in the order an officer does them (rules.json `step`, then deadline). Each approval
adds `step` and `order` (1, 2, 3… as shown). Inside an approval, `flags` are worst first. Show them in this order.

Optional extra fields (safe to ignore): `/pack` rows add `name, deadline_label, by` ("ai"|"template");
`/reviewer/queue` rows add `by, source` ("submitted"|"demo"), `counts, attendance, venue`; `/ask` adds `by`.
