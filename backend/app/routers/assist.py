"""Owner: Split A (explain + fix loop).
Endpoint: POST /explain.  (/pack lives in pack.py, owned by Split B)

TODO(Split A):
  /explain: rewrite each flag's message + fix in friendly plain English.
            The model may ONLY use the flag's rule_text as its source; it must not
            add new rules or numbers. Fall back to the engine's text on any error.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from .. import llm

router = APIRouter(tags=["assist"])

EXPLAIN_SYSTEM = """You explain why a USC club event request was flagged.
Use ONLY the rule text given. Do not add rules, numbers or dates that are not given.
Return JSON: {"reason": one sentence, "fix": one sentence}."""


class ExplainIn(BaseModel):
    flag: dict
    event: dict | None = None


@router.post("/explain")
def explain(body: ExplainIn):
    f = body.flag
    fallback = {"reason": f.get("message", ""), "fix": f.get("fix", ""), "quote": f.get("rule_text", ""), "source": f.get("source", "")}
    if not llm.available():
        return fallback
    try:
        out = llm.ask_json(EXPLAIN_SYSTEM, f"Rule text: {f.get('rule_text')}\nProblem: {f.get('message')}\nEngine fix: {f.get('fix')}")
        return {**fallback, **out}
    except Exception:
        return fallback
