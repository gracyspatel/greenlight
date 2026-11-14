# Greenlight — AI@USC Hackathon

One event description → every USC approval it needs, every deadline, and a rule-checked verdict before you submit.

Start here: **PLAN.md** (Split A / Split B, who does what, when) · **CLAUDE.md** (rules for Claude Code) · **docs/CONTRACTS.md** (data shapes).

```bash
pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --reload --port 8000
cd frontend && npm install && npm run dev   # open http://localhost:5173
```
