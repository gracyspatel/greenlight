# Greenlight — instructions for Claude Code (read fully before editing)

Greenlight turns one USC club event description into a full approval plan
(USG funding, venue, UEPA, catering, fundraising, social dance), counts each
deadline back from the event date, checks the request against USC's written
rules, and gives a verdict: **Ready / At risk / Will be rejected**, with the rule and the fix.

## The one principle you must never break
**The AI understands, the rules decide.** Every pass/fail decision is plain Python in
`backend/app/engine.py` reading `data/rules.json`. LLM calls (`backend/app/llm.py`) only
extract fields and explain/rephrase. Never let the model decide a verdict, invent a rule,
a dollar amount, or a date. Explanations may only quote `rule_text` stored with the rule.

## Team ownership — two splits, only edit files your split owns
I am on **Split __** (A or B; the human fills this in. Ask if blank).

### Split A: Officer flow (Plan → Check → Fix)  ·  branch `split-a`
- `backend/app/routers/intake.py`  (/extract)
- `backend/app/routers/assist.py`  (/explain only; /pack belongs to Split B, see below)
- `frontend/src/components/intake/`, `timeline/`, `verdict/`, `fixloop/`
- `data/demo_events.json`

### Split B: Rules, submit, track, review, deploy  ·  branch `split-b`
- `backend/app/engine.py`, `data/rules.json`, `data/calendar.json`, `backend/tests/`
- `backend/app/routers/check.py`, `backend/app/routers/extras.py`, and a NEW `backend/app/routers/pack.py` (move /pack here)
- `backend/app/main.py`, `backend/app/llm.py`, `.replit`
- `frontend/src/App.jsx`, `frontend/src/api.js`
- `frontend/src/components/tracker/`, `reviewer/`, `ask/`, and a NEW `pack/`
- `data/guidelines/`

Shared (both splits, small additive edits only, announce in chat): `docs/CONTRACTS.md`, `frontend/src/styles.css`.
If you need a change in the other split's files, write the exact change as a message
for the human to pass on instead of editing it.

## Contracts
Shapes are in `docs/CONTRACTS.md`. Don't rename or remove fields. Adding an optional
field is OK if `engine.normalize()` tolerates it missing.

## How to run
```bash
# backend (from repo root)
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
# frontend (second terminal)
cd frontend && npm install && npm run dev      # http://localhost:5173
# tests (before every merge)
cd backend && python -m pytest -q
```
No API key? Everything still runs: LLM endpoints fall back to the engine's own text.

## Rules for every change
- Small commits on your split's branch (`split-a` or `split-b`). Pull your partner's commits often.
- `cd backend && python -m pytest -q` must pass and the 3 demo events must still be Ready / At risk / Will be rejected.
- LLM calls: always wrap in try/except and fall back to non-LLM output — the demo must never crash.
- Keep the UI copy plain and short. Keep the disclaimer visible.
- Don't add new dependencies without telling the team.

## DO NOT ADD CLAUDE AS A COLLABORATER IN GITHUB ON ANY PUSH.