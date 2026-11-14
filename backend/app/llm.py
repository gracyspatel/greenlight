"""Shared LLM helper. Owner: Split B. Everyone imports from here; nobody calls
the SDK directly, so we can swap models/providers in one place.

Rule of the project: the LLM reads and explains, it NEVER decides pass/fail.

How to call it (always wrap in try/except and fall back to non-LLM text):
    from .. import llm
    if llm.available():
        try:
            out = llm.ask_json(SYSTEM, user_text)      # -> dict
            if not llm.grounded(str(out), facts_text):  # model added a number? throw it away
                out = fallback
        except Exception:
            out = fallback
"""
import json
import os
import re

MODEL = os.getenv("LLM_MODEL") or "claude-sonnet-5-5"
TIMEOUT = float(os.getenv("LLM_TIMEOUT") or 30)


def _client():
    from anthropic import Anthropic  # imported lazily so tests run without a key
    # Keys not scoped to one workspace must name it on every request.
    ws = os.getenv("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": ws} if ws else None
    # reads ANTHROPIC_API_KEY from env / .env
    return Anthropic(default_headers=headers, timeout=TIMEOUT, max_retries=1)


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def ask_text(system: str, user: str, max_tokens: int = 800) -> str:
    msg = _client().messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in msg.content if b.type == "text").strip()


def ask_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    """Ask for JSON only and parse it. Put the schema/example in `system`."""
    text = ask_text(system + "\n\nReply with ONLY valid JSON, no prose, no code fences.", user, max_tokens)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


# ---------------------------------------------------------------- grounding
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> set[str]:
    """Numbers in text as canonical strings: '$4,500' -> '4500', '4.0' -> '4'."""
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
    """True if every number in `output` also appears in one of the sources.
    Use it to throw away LLM text that invents an amount, date or limit."""
    allowed = set().union(*(numbers(s) for s in sources)) if sources else set()
    return numbers(output) <= allowed
