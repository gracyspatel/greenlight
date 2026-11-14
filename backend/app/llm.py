"""Shared LLM helper. Owner: Split B. Everyone imports from here; nobody calls
the SDK directly, so we can swap models/providers in one place.

Rule of the project: the LLM reads and explains, it NEVER decides pass/fail.
"""
import json
import os

MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")


def _client():
    from anthropic import Anthropic  # imported lazily so tests run without a key
    return Anthropic()  # reads ANTHROPIC_API_KEY from env / .env


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
