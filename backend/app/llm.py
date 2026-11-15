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


# Our calls are short, single-shot rewording/extraction with no tools, so thinking only eats the
# max_tokens budget: Sonnet 5.5 thinks by default, and a 250-token call came back with no text at all.
# On claude-sonnet-5-5, {"type": "disabled"} is a 400; {"type": "between_tools"} is how to turn it off.
THINKING_OFF = {"type": "between_tools"}


def ask_text(system: str, user: str, max_tokens: int = 800) -> str:
    from anthropic import BadRequestError
    client = _client()
    kw = dict(model=MODEL, system=system, messages=[{"role": "user", "content": user}])
    try:
        msg = client.messages.create(max_tokens=max_tokens, thinking=THINKING_OFF, **kw)
    except BadRequestError:
        # another LLM_MODEL may not accept between_tools: let it think, with room to answer
        msg = client.messages.create(max_tokens=max(max_tokens * 4, 2000), **kw)
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if not text:
        raise ValueError(f"LLM returned no text (stop_reason={getattr(msg, 'stop_reason', None)})")
    return text


def ask_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    """Ask for JSON only and parse it. Put the schema/example in `system`."""
    text = ask_text(system + "\n\nReply with ONLY valid JSON, no prose, no code fences.", user, max_tokens)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


# ---------------------------------------------------------------- grounding
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
_WORDS.update({"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6",
               "twice": "2", "half": "0.5", "dozen": "12", "fifteen": "15", "twenty": "20", "thirty": "30"})
_WORD_RE = re.compile(r"\b(" + "|".join(_WORDS) + r")\b", re.I)


def numbers(text: str) -> set[str]:
    """Numbers in text as canonical strings: '$4,500' -> '4500', '4.0' -> '4', 'fifth' -> '5'."""
    out = {_WORDS[w.lower()] for w in _WORD_RE.findall(text or "")}
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
