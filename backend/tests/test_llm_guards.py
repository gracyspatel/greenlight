"""The guards around every LLM call, tested with a FAKE model that lies on purpose.

We can't make the real model hallucinate on demand, so `fake_llm` swaps in a stand-in that
returns whatever reply the test scripts (or raises). No network calls ever happen here.
Each test proves one promise of the project: the AI understands, the rules decide."""
import copy
import inspect
import json

import pytest
from fastapi.testclient import TestClient

from app import engine, llm
from app.main import app
from app.routers import assist, extras, pack

client = TestClient(app)
DEMOS = {d["id"]: d for d in json.loads((engine.BASE / "demo_events.json").read_text())}


@pytest.fixture
def fake_llm(monkeypatch):
    """fake_llm(reply) makes every llm.ask_json call return `reply` (a dict, or an
    Exception to raise, or a function(system, user) -> dict). Records each call."""
    calls = []

    def install(reply):
        def ask_json(system, user, max_tokens=1500):
            calls.append({"system": system, "user": user})
            r = reply(system, user) if callable(reply) else reply
            if isinstance(r, Exception):
                raise r
            return copy.deepcopy(r)
        monkeypatch.setattr(llm, "available", lambda: True)
        monkeypatch.setattr(llm, "ask_json", ask_json)
        return calls

    def no_network(*a, **k):
        raise AssertionError("tests must never reach the real API")
    monkeypatch.setattr(llm, "_client", no_network)
    monkeypatch.setattr(extras, "_SUMMARIES", {})  # summary cache must not leak between tests
    return install


DIWALI = DEMOS["blockers"]


def diwali_check():
    return client.post("/api/check", json=DIWALI).json()


def first_flag(rule_id=None):
    for a in diwali_check()["approvals"]:
        for f in a["flags"]:
            if rule_id is None or f["rule_id"] == rule_id:
                return f
    raise LookupError(rule_id)


# ================================================================ the rules never ask the AI
def test_engine_has_no_llm_code():
    src = inspect.getsource(engine)
    assert "import llm" not in src and "anthropic" not in src and not hasattr(engine, "llm")


def test_check_never_calls_the_model(fake_llm):
    calls = fake_llm(AssertionError("the rules engine must never call the model"))
    for d in DEMOS.values():
        assert client.post("/api/check", json=d).json()["verdict"] in ("ready", "risk", "reject")
    assert calls == []


def test_model_cannot_change_a_verdict_anywhere(fake_llm):
    """A model that claims everything is fine changes no verdict."""
    fake_llm({"summary": "Ready. Passes every rule.", "reason": "All good.", "fix": "Nothing to do.",
              "answer": "Everything is approved.", "cited": [1], "verdict": "ready"})
    rows = {r["id"]: r for r in client.get("/api/reviewer/queue").json()}
    assert rows["blockers"]["verdict"] == "reject"
    assert client.post("/api/check", json=DIWALI).json()["verdict"] == "reject"


# ================================================================ /extract
DIWALI_TEXT = DIWALI["text"]  # 300 people, Dec 12, $3,500 asked, ballroom $4,500, DJ $600


def extract(text=DIWALI_TEXT, event=None):
    return client.post("/api/extract", json={"text": text, "event": event or {"as_of": DIWALI["as_of"]}}).json()


def test_extract_drops_invented_numbers_and_dates(fake_llm):
    fake_llm({"name": "Diwali Night", "date": "2026-12-25", "attendance": 350, "amount_requested": 9999,
              "org": {"funded_events_this_semester": 7, "usg_received_this_year": 123},
              "budget_lines": [{"item": "Photo booth", "category": "other", "amount": 777}]})
    out = extract()
    ev = out["event"]
    assert ev["date"] == "2026-12-12"           # the only date in the text
    assert ev["attendance"] == 300              # 350 isn't in the text
    assert ev["amount_requested"] == 3500       # 9999 isn't in the text
    assert ev["org"]["funded_events_this_semester"] == 4 and ev["org"]["usg_received_this_year"] == 5200
    assert 777 not in [l["amount"] for l in ev["budget_lines"]]
    assert 'How much will "Photo booth" cost?' in out["questions"]  # asks instead of guessing


def test_extract_keeps_numbers_that_are_in_the_text(fake_llm):
    fake_llm({"attendance": 300, "amount_requested": 3500, "date": "2026-12-12",
              "budget_lines": [{"item": "Grand Ballroom", "category": "venue", "amount": 4500, "quote_attached": False}]})
    ev = extract()["event"]
    assert ev["attendance"] == 300 and ev["amount_requested"] == 3500
    assert ev["budget_lines"] == [{"item": "Grand Ballroom", "category": "venue", "amount": 4500.0, "quote_attached": False}]


def test_extract_fixes_a_bad_category(fake_llm):
    fake_llm({"budget_lines": [{"item": "DJ", "category": "party stuff", "amount": 600}]})
    lines = extract()["event"]["budget_lines"]
    assert lines and all(l["category"] in ("venue", "food", "entertainment", "supplies", "marketing", "other")
                         for l in lines)


def test_extract_with_no_date_in_text_drops_model_date(fake_llm):
    fake_llm({"date": "2027-01-01", "attendance": 50})
    ev = extract("Board game night, about 50 people.")["event"]
    assert ev.get("date") is None and ev["attendance"] == 50


@pytest.mark.parametrize("reply", [RuntimeError("API down"), ValueError("bad JSON"), ["not", "a", "dict"], {}])
def test_extract_survives_a_broken_model(fake_llm, reply):
    fake_llm(reply)
    ev = extract()["event"]
    assert ev["attendance"] == 300 and ev["date"] == "2026-12-12"   # the code-only reader took over
    assert engine.check(ev)["verdict"] == "reject"


def test_extract_caps_model_questions(fake_llm):
    fake_llm({"questions": ["Q1?", "Q2?", "Q3?", "Q4?", "Q5?", 42, None]})
    qs = extract()["questions"]
    assert "Q4?" not in qs and 42 not in qs and len(qs) <= 6


def test_extract_sends_today_and_current_event_to_model(fake_llm):
    calls = fake_llm({})
    extract("Q: About how many people do you expect?\nA: 300", {"as_of": "2026-11-15", "name": "Diwali Night"})
    assert "TODAY: Sunday 2026-11-15" in calls[0]["user"] and "Diwali Night" in calls[0]["user"]


# ================================================================ /explain
def explain(flag):
    return client.post("/api/explain", json={"flag": flag, "event": DIWALI}).json()


def test_explain_uses_a_grounded_rewording(fake_llm):
    f = first_flag("usg_venue_cap")  # "$4,500 ... over the $4,000 maximum"
    fake_llm({"reason": "Your venue costs $4,500, but USG pays at most $4,000 for venues.",
              "fix": "Cut the venue cost to $4,000 or less."})
    out = explain(f)
    assert out["by"] == "ai" and "$4,500" in out["reason"]


@pytest.mark.parametrize("reason, fix", [
    ("Venue costs over $3,000 are rejected.", "Cut it."),         # invented dollar amount
    ("Too expensive.", "Submit 10 days earlier."),               # invented number of days
    ("Too expensive.", "Get five quotes."),                      # invented number written as a word
    ("Too expensive.", "Apply by 2026-12-01."),                  # invented date
])
def test_explain_rejects_invented_numbers(fake_llm, reason, fix):
    f = first_flag("usg_venue_cap")
    fake_llm({"reason": reason, "fix": fix})
    out = explain(f)
    assert out["by"] == "rules" and out["reason"] == f["message"] and out["fix"] == f["fix"]


def test_explain_quote_and_source_never_come_from_the_model(fake_llm):
    f = first_flag("usg_venue_cap")
    fake_llm({"reason": "Too expensive.", "fix": "Cut it.", "quote": "USG pays for anything.",
              "source": "https://evil.example.com"})
    out = explain(f)
    assert out["quote"] == f["rule_text"] and out["source"] == f["source"]


@pytest.mark.parametrize("reply", [{}, {"reason": "", "fix": ""}, {"reason": "Only a reason."},
                                   RuntimeError("API down"), ValueError("bad JSON")])
def test_explain_falls_back_on_empty_or_broken_model(fake_llm, reply):
    f = first_flag()
    fake_llm(reply)
    out = explain(f)
    assert out["by"] == "rules" and out["reason"] == f["message"]


def test_explain_with_no_key_is_engine_text():
    f = first_flag()
    out = explain(f)
    assert out == {"reason": f["message"], "fix": f["fix"], "quote": f["rule_text"],
                   "source": f["source"], "by": "rules"}


# ================================================================ /pack
def pack_rows(check=None):
    return client.post("/api/pack", json=check or diwali_check()).json()


def test_pack_uses_grounded_polish(fake_llm):
    check = diwali_check()
    drafts = {a["id"]: pack.template(a, pack.facts(check["event"])) for a in check["approvals"]}
    fake_llm({aid: "Please review.\n" + text for aid, text in drafts.items()})
    assert all(r["by"] == "ai" for r in pack_rows(check))


def test_pack_rejects_polish_with_invented_numbers(fake_llm):
    check = diwali_check()
    drafts = {a["id"]: pack.template(a, pack.facts(check["event"])) for a in check["approvals"]}
    fake_llm({aid: text + "\nWe expect a $9,999 profit." for aid, text in drafts.items()})
    rows = pack_rows(check)
    assert all(r["by"] == "template" and "9,999" not in r["draft"] for r in rows)


def _drop_placeholders(aid):
    check = diwali_check()
    a = next(a for a in check["approvals"] if a["id"] == aid)
    draft = pack.template(a, pack.facts(check["event"]))
    return check, draft, draft.replace("[", "").replace("]", "")  # hides every [fill in] spot


def test_pack_rejects_polish_that_drops_placeholders(fake_llm):
    check, draft, stripped = _drop_placeholders("venue_request")
    assert draft.count("[") >= 2
    fake_llm({"venue_request": stripped})
    row = next(r for r in pack_rows(check) if r["approval_id"] == "venue_request")
    assert row["by"] == "template" and pack.PURPOSE in row["draft"]


def test_pack_keeps_the_only_placeholder(fake_llm):
    check, draft, stripped = _drop_placeholders("usg_funding")
    assert draft.count("[") == 1
    fake_llm({"usg_funding": stripped})
    row = next(r for r in pack_rows(check) if r["approval_id"] == "usg_funding")
    assert row["by"] == "template"


def test_pack_ignores_unknown_keys_and_broken_model(fake_llm):
    fake_llm({"made_up_form": "Event: x"})
    assert all(r["by"] == "template" for r in pack_rows())
    fake_llm(RuntimeError("API down"))
    rows = pack_rows()
    assert len(rows) == len(diwali_check()["approvals"]) and all(r["by"] == "template" for r in rows)


# ================================================================ /ask
QUESTION = "Can USG pay for venue costs?"


def ask(q=QUESTION):
    return client.post("/api/ask", json={"question": q}).json()


def test_ask_uses_grounded_answer_and_only_valid_citations(fake_llm):
    if not extras.search(QUESTION):
        pytest.skip("no guideline match")
    fake_llm({"answer": "Yes, venue costs can be funded. USG makes the final call.", "cited": [1, 99, "x", -1]})
    out = ask()
    assert out["by"] == "ai" and len(out["citations"]) >= 1
    sources = {c["source"] for c in extras._cite(extras.search(QUESTION))}
    assert all(c["source"] in sources for c in out["citations"])


def test_ask_rejects_invented_numbers(fake_llm):
    if not extras.search(QUESTION):
        pytest.skip("no guideline match")
    fake_llm({"answer": "Yes, up to $123,456 per event.", "cited": [1]})
    out = ask()
    assert out["by"] == "excerpt" and "123,456" not in out["answer"]


def test_ask_not_covered_from_model(fake_llm):
    if not extras.search(QUESTION):
        pytest.skip("no guideline match")
    fake_llm({"answer": "NOT_COVERED", "cited": []})
    out = ask()
    assert out["answer"] == extras.NOT_COVERED and out["citations"] == []


def test_ask_does_not_call_model_without_matching_guidelines(fake_llm):
    calls = fake_llm({"answer": "Made up.", "cited": [1]})
    out = ask("zzqx qqzz")
    assert out["answer"] == extras.NOT_COVERED and calls == []


def test_ask_survives_broken_model(fake_llm):
    if not extras.search(QUESTION):
        pytest.skip("no guideline match")
    fake_llm(RuntimeError("API down"))
    out = ask()
    assert out["by"] == "excerpt" and out["citations"]


def test_ask_only_sends_retrieved_excerpts(fake_llm):
    hits = extras.search(QUESTION)
    if not hits:
        pytest.skip("no guideline match")
    calls = fake_llm({"answer": "NOT_COVERED"})
    ask()
    assert all(h["text"] in calls[0]["user"] for h in hits)


# ================================================================ reviewer summaries
def queue():
    return {r["id"]: r for r in client.get("/api/reviewer/queue").json()}


def test_summary_with_invented_numbers_is_replaced(fake_llm):
    fake_llm({"summary": "A $999,999 event for 5,000 people."})
    assert all(r["by"] == "rules" and "999,999" not in r["summary"] for r in queue().values())


def test_grounded_summary_is_used(fake_llm):
    fake_llm({"summary": "The club asks USG for help with this event."})
    assert all(r["by"] == "ai" for r in queue().values())


def test_summary_survives_broken_model(fake_llm):
    fake_llm(RuntimeError("API down"))
    rows = queue()
    assert all(r["by"] == "rules" and r["summary"] for r in rows.values())


# ================================================================ the number checker itself
CASES = [
    ("Venue is $4,500", "cost 4500 dollars", True),
    ("Cap is $4,000", "cost 4500", False),
    ("4.0 events", "4 events", True),
    ("the fifth event", "limit is 4", False),
    ("the fifth event", "event #5", True),
    ("three months", "3 months", True),
    ("no numbers here", "", True),
    ("Due 2026-12-01", "Due 2026-12-02", False),
]


@pytest.mark.parametrize("out, src, ok", CASES)
@pytest.mark.parametrize("fn", [llm.grounded, assist.grounded], ids=["llm.grounded", "assist.grounded"])
def test_both_number_checkers_agree(fn, out, src, ok):
    """/explain uses its own copy of the checker (assist.py); everything else uses llm.py.
    Both copies must behave the same."""
    assert fn(out, src) is ok


def test_number_checkers_agree_on_half():
    assert llm.grounded("half the venue", "cap 4000") == assist.grounded("half the venue", "cap 4000")


def test_ask_json_strips_code_fences(monkeypatch):
    monkeypatch.setattr(llm, "ask_text", lambda *a, **k: '```json\n{"a": 1}\n```')
    assert llm.ask_json("s", "u") == {"a": 1}


def test_ask_json_raises_on_prose(monkeypatch):
    monkeypatch.setattr(llm, "ask_text", lambda *a, **k: "Sure! Here you go.")
    with pytest.raises(ValueError):
        llm.ask_json("s", "u")
