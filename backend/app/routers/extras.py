"""Owner: Split B (tracker, reviewer view, Q&A).
Endpoints: GET /reviewer/queue, POST /reviewer/submit, POST /ask.

Tracking needs no endpoint: the frontend stores statuses in event.tracking
({approval_id: {"status": "submitted|approved|returned"}}) and re-calls /check;
the engine already reacts to them.

/ask: keyword search over data/guidelines/*.md, the LLM answers ONLY from the top
      chunks with a citation, else "Not covered — email usgfunds@usc.edu".
/reviewer/queue: engine.check on every submitted + demo event, one summary row each.
      The verdict always comes from the engine; the LLM only writes the summary.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from .. import engine, llm

router = APIRouter(tags=["extras"])
GUIDES = Path(engine.BASE) / "guidelines"
NOT_COVERED = "Not covered by our stored guidelines — email usgfunds@usc.edu."


# ================================================================ /ask
STOP = set("""a an and are as at be by can could do does for from has have how i if in is it its
me my of on or our should so than that the their them then there these they this to us was we
what when where which who why will with would you your about any get got just more much need""".split())


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9$]+", (text or "").lower()):
        if w in STOP or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]  # t-shirts -> t-shirt, quotes -> quote
        for suf in ("ing", "ic", "ed"):  # alcoholic -> alcohol, funded -> fund
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def _frontmatter(text: str) -> tuple[dict, str]:
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            text = text[end + 4:]
    return meta, text


def load_chunks() -> list[dict]:
    """Split every guideline file into ~paragraph chunks under their heading."""
    chunks = []
    for p in sorted(GUIDES.glob("*.md")):
        meta, body = _frontmatter(p.read_text(encoding="utf-8", errors="ignore"))
        title = meta.get("title") or p.stem.replace("-", " ").title()
        source = meta.get("source", "")
        heading, buf = "", []

        def flush():
            text = "\n".join(buf).strip()
            if len(text) > 40:
                chunks.append({"title": title, "source": source, "heading": heading, "text": text})
            buf.clear()

        for line in body.splitlines():
            size = sum(len(b) for b in buf)
            if line.startswith("#"):
                flush()
                heading = line.lstrip("#").strip()
            elif (not line.strip() and size > 500) or size > 900:
                flush()  # keep chunks small so nothing is cut off and search stays precise
                buf.append(line)
            else:
                buf.append(line)
        flush()
    return chunks


def search(question: str, k: int = 4) -> list[dict]:
    chunks = load_chunks()
    q = set(_tokens(question))
    if not q or not chunks:
        return []
    docs = [set(_tokens(c["heading"] + " " + c["text"])) for c in chunks]
    n = len(docs)
    idf = {t: math.log(1 + n / (1 + sum(t in d for d in docs))) for t in q}
    scored = []
    for c, d in zip(chunks, docs):
        hits = q & d
        if hits:
            scored.append((sum(idf[t] for t in hits) / math.sqrt(1 + len(d) / 80), len(hits), c))
    scored.sort(key=lambda x: -x[0])
    best = [c for s, hits, c in scored[:k]]
    # need a real match: either 2+ question words, or 1 rare word
    if not scored or (scored[0][1] < 2 and len(q) > 1 and scored[0][0] < 1.0):
        return []
    return best


ASK_SYSTEM = """You answer USC student club officers' questions about event funding and approvals.
You get numbered excerpts from official USC pages. Answer ONLY from those excerpts.

Strict rules:
- If the excerpts don't clearly answer the question, set "answer" to "NOT_COVERED".
- Never add rules, numbers, dollar amounts, dates or offices that aren't in the excerpts.
- 1–3 short plain sentences. Say "USG makes the final call" when the answer depends on review.
- "cited": the excerpt numbers you used.

Return JSON: {"answer": "...", "cited": [1, 2]}"""


class AskIn(BaseModel):
    question: str


def _cite(chunks: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in chunks:
        key = c["source"] or c["title"]
        if key not in seen:
            seen.add(key)
            out.append({"title": c["title"], "source": c["source"]})
    return out


@router.post("/ask")
def ask(body: AskIn):
    question = (body.question or "").strip()
    hits = search(question)
    if not hits:
        return {"answer": NOT_COVERED, "citations": [], "by": "none"}
    # no key: show the best excerpt itself, never an invented answer
    top = hits[0]
    snippet = re.sub(r"\s+", " ", top["text"])[:400].rstrip() + ("…" if len(top["text"]) > 400 else "")
    fallback = {"answer": f"From \"{top['title']}\": {snippet}", "citations": _cite([top]), "by": "excerpt"}
    if not llm.available():
        return fallback
    try:
        ctx = "\n\n".join(f"[{i + 1}] {c['title']} — {c['heading']}\n{c['text']}" for i, c in enumerate(hits))
        out = llm.ask_json(ASK_SYSTEM, f"Excerpts:\n{ctx}\n\nQuestion: {question}", max_tokens=400)
        answer = str(out.get("answer") or "").strip()
        if not answer or "NOT_COVERED" in answer:
            return {"answer": NOT_COVERED, "citations": [], "by": "ai"}
        if not llm.grounded(answer, ctx, question):
            return fallback
        cited = [hits[i - 1] for i in out.get("cited") or [] if isinstance(i, int) and 1 <= i <= len(hits)]
        return {"answer": answer, "citations": _cite(cited or hits[:1]), "by": "ai"}
    except Exception:
        return fallback


# ================================================================ reviewer
SUBMITTED: list[dict] = []   # in memory: resets on restart, fine for a demo
_SUMMARIES: dict[str, str] = {}

SUMMARY_SYSTEM = """You write a 2-sentence summary of a student club's event funding application
for a USG reviewer. Sentence 1: what the event is (name, date, venue, attendance, amount asked).
Sentence 2: what the automated rule check found, naming the 2-3 most serious issues (use ONLY
the listed issues; if none, say it passed every written rule checked). Never add numbers, rules or opinions not given.
Return JSON: {"summary": "..."}"""


def _fallback_summary(ev: dict, r: dict) -> str:
    named = lambda lvl: [f"{a['name']}: {f['message'].rstrip('.')}" for a in r["approvals"]
                         for f in a["flags"] if lvl is None or f["level"] == lvl]
    flags = named("reject") or named(None)
    head = (f"{ev.get('attendance') or '?'} attendees at {ev['venue'].get('name') or 'TBD'}, "
            f"asking {ev['funding_source']} for ${ev['amount_requested']:,.0f}.")
    if not flags:
        return head + " Passes every written rule we check."
    more = f" (+{len(flags) - 2} more)" if len(flags) > 2 else ""
    return head + " Issues: " + "; ".join(flags[:2]) + more


def _summary(ev: dict, r: dict) -> tuple[str, str]:
    fb = _fallback_summary(ev, r)
    if not llm.available():
        return fb, "rules"
    key = hashlib.sha1(json.dumps([ev, r["verdict"]], sort_keys=True, default=str).encode()).hexdigest()
    if key in _SUMMARIES:
        return _SUMMARIES[key], "ai"
    issues = [f"{a['name']}: {f['message']}" for a in r["approvals"] for f in a["flags"]]
    facts = (f"Event: {ev['name']} on {ev.get('date')} at {ev['venue'].get('name')}, "
             f"{ev.get('attendance')} attendees, asking {ev['funding_source']} for ${ev['amount_requested']:,.0f}.\n"
             f"Verdict: {r['verdict_label']}\nNumber of issues: {len(issues)}\nIssues:\n" + ("\n".join(issues) or "(none)"))
    try:
        s = str(llm.ask_json(SUMMARY_SYSTEM, facts, max_tokens=250).get("summary") or "").strip()
        if s and llm.grounded(s, facts):
            _SUMMARIES[key] = s
            return s, "ai"
    except Exception:
        pass
    return fb, "rules"


def _row(d: dict, source: str) -> dict:
    r = engine.check(d)
    ev = r["event"]
    summary, by = _summary(ev, r)
    return {"id": d.get("id") or ev["name"], "name": ev["name"], "date": ev.get("date"),
            "requested": ev["amount_requested"], "verdict": r["verdict"],
            "verdict_label": r["verdict_label"], "summary": summary, "by": by,
            "source": source, "counts": r["counts"], "attendance": ev.get("attendance"),
            "venue": ev["venue"].get("name")}


@router.get("/reviewer/queue")
def reviewer_queue():
    demos = json.loads((engine.BASE / "demo_events.json").read_text())
    items = [(d, "submitted") for d in reversed(SUBMITTED)] + [(d, "demo") for d in demos]
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda x: _row(*x), items))


class SubmitIn(BaseModel):
    event: dict


@router.post("/reviewer/submit")
def reviewer_submit(body: SubmitIn):
    """The officer sends their (checked) event to the USG reviewer queue."""
    ev = {k: v for k, v in body.event.items() if k != "text"}
    ev["id"] = f"sub-{len(SUBMITTED) + 1}"
    SUBMITTED.append(ev)
    return {"ok": True, "id": ev["id"]}
