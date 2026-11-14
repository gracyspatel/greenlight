"""Owner: Split B (tracker, reviewer view, Q&A). Endpoints: /reviewer/queue, /ask.

Tracking needs no endpoint: the frontend stores statuses in event.tracking
({approval_id: {"status": "submitted|approved|returned"}}) and re-calls /check;
the engine already reacts to them.

TODO(Split B):
  /ask: keyword search over data/guidelines/*.md, send top chunks to the LLM,
        answer ONLY from them with a citation, else "Not covered — email usgfunds@usc.edu".
  /reviewer/queue: run engine.check on each demo event and return a summary row each.
"""
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from .. import engine, llm

router = APIRouter(tags=["extras"])
GUIDES = Path(engine.BASE) / "guidelines"


@router.get("/reviewer/queue")
def reviewer_queue():
    demos = json.loads((engine.BASE / "demo_events.json").read_text())
    rows = []
    for d in demos:
        r = engine.check(d)
        rows.append({"id": d["id"], "name": d["name"], "date": d.get("date"),
                     "requested": d.get("amount_requested"), "verdict": r["verdict"],
                     "verdict_label": r["verdict_label"],
                     "summary": "TODO(Split B): one-paragraph LLM summary"})
    return rows


class AskIn(BaseModel):
    question: str


@router.post("/ask")
def ask(body: AskIn):
    return {"answer": "Not covered by our stored guidelines yet — email usgfunds@usc.edu.", "citations": []}
