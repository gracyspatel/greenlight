"""Owner: Split A (intake). Endpoint: POST /extract  {text, event?} -> {event, questions}.

TODO(Split A):
  1. Write the extraction prompt in EXTRACT_SYSTEM (describe every field in
     docs/CONTRACTS.md -> Event, with types and an example).
  2. If `event` is passed in, MERGE: keep existing fields, fill/overwrite from new text
     (this is how follow-up answers get added).
  3. Return the engine's missing_questions() plus any of the model's own questions.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from .. import engine, llm

router = APIRouter(tags=["intake"])

EXTRACT_SYSTEM = """You turn a USC student club's event description into JSON.
TODO(Split A): list every field of the Event shape from docs/CONTRACTS.md here.
Use null for anything not stated. Never invent amounts or dates."""


class ExtractIn(BaseModel):
    text: str
    event: dict | None = None


@router.post("/extract")
def extract(body: ExtractIn):
    if llm.available():
        try:
            new = llm.ask_json(EXTRACT_SYSTEM, body.text)
        except Exception as e:  # keep the demo alive
            new = {"_error": str(e)}
    else:
        new = {"name": "Stub event (no API key)", "_stub": True}
    merged = {**(body.event or {}), **{k: v for k, v in new.items() if v is not None}}
    ev = engine.normalize(merged)
    return {"event": ev, "questions": engine.missing_questions(ev)}
