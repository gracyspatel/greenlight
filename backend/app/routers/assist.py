"""Owner: Split A (explain + fix loop).
Endpoint: POST /explain  {flag, event?} -> {reason, fix, quote, source, by}.
(/pack lives in pack.py, owned by Split B)

The model only REWORDS the engine's message + fix in plain English.
  - quote/source always come from the flag (the rule's stored text), never from the model.
  - Code checks the rewording: if it contains any number that isn't in the rule text,
    the engine message or the engine fix, we throw it away and use the engine's text.
  - `by` is "ai" when the rewording was used, "rules" when it's the engine's own text.
"""
import re

from fastapi import APIRouter
from pydantic import BaseModel

from .. import llm

router = APIRouter(tags=["assist"])

EXPLAIN_SYSTEM = """You explain to a USC student club officer why their event request was flagged.
You get the official rule text, the problem the checker found, and the checker's fix.

Write:
  "reason": ONE short friendly sentence saying what the problem is and why the rule cares.
  "fix":    ONE short sentence telling them exactly what to do next.

Strict rules:
- Use ONLY facts in the given rule text, problem and fix. Do not add rules, offices, numbers,
  dollar amounts, dates, deadlines or percentages that are not written there.
- Copy any number exactly as written in the input.
- Plain words, no jargon, no legal tone, no "As an AI".

Return JSON: {"reason": "...", "fix": "..."}"""

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    """Numbers as canonical strings: '$4,500' -> '4500', '4.0' -> '4'."""
    out = set()
    for m in _NUM.findall(text or ""):
        v = m.replace(",", "").rstrip(".")
        try:
            f = float(v)
        except ValueError:
            continue
        out.add(str(int(f)) if f == int(f) else str(f))
    return out


def grounded(output: str, *sources: str) -> bool:
    """True if every number in `output` appears in one of the sources."""
    allowed = set().union(*(_numbers(s) for s in sources))
    return _numbers(output) <= allowed


class ExplainIn(BaseModel):
    flag: dict
    event: dict | None = None


@router.post("/explain")
def explain(body: ExplainIn):
    f = body.flag
    msg, fix, rule = str(f.get("message", "")), str(f.get("fix", "")), str(f.get("rule_text", ""))
    fallback = {"reason": msg, "fix": fix, "quote": rule, "source": f.get("source", ""), "by": "rules"}
    if not llm.available():
        return fallback
    try:
        out = llm.ask_json(EXPLAIN_SYSTEM, f"Rule text: {rule}\nProblem: {msg}\nChecker's fix: {fix}", max_tokens=300)
        reason, new_fix = str(out.get("reason") or "").strip(), str(out.get("fix") or "").strip()
        if not reason or not new_fix or not grounded(reason + " " + new_fix, rule, msg, fix):
            return fallback
        return {**fallback, "reason": reason, "fix": new_fix, "by": "ai"}
    except Exception:
        return fallback
