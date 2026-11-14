"""/pack, /ask, /reviewer with no LLM key (conftest blanks it): the fallbacks must work."""
import json

from fastapi.testclient import TestClient

from app import engine, llm
from app.main import app

client = TestClient(app)
DEMOS = {d["id"]: d for d in json.loads((engine.BASE / "demo_events.json").read_text())}


def test_pack_one_draft_per_approval_with_real_facts():
    res = client.post("/api/check", json=DEMOS["ready"]).json()
    drafts = client.post("/api/pack", json=res).json()
    assert [d["approval_id"] for d in drafts] == [a["id"] for a in res["approvals"]]
    usg = next(d for d in drafts if d["approval_id"] == "usg_funding")
    assert "$1,200" in usg["draft"] and "Spring Career Mixer" in usg["draft"]
    assert all(d["link"].startswith("https://") and d["by"] == "template" for d in drafts)


def test_pack_template_invents_no_numbers():
    res = client.post("/api/check", json=DEMOS["blockers"]).json()
    from app.routers.pack import facts
    allowed = "\n".join(facts(res["event"]).values())
    for d in client.post("/api/pack", json=res).json():
        assert llm.grounded(d["draft"], allowed), d["approval_id"]


def test_grounded():
    assert llm.grounded("Venue is $4,500", "cost 4500 dollars")
    assert not llm.grounded("Cap is $4,000", "cost 4500")


def test_ask_nonsense_is_not_covered():
    r = client.post("/api/ask", json={"question": "zzqx"}).json()
    assert "usgfunds@usc.edu" in r["answer"] and r["citations"] == []


def test_ask_cites_a_source_when_guidelines_match():
    from app.routers.extras import load_chunks
    if not load_chunks():
        return  # no guideline files yet
    r = client.post("/api/ask", json={"question": "Can USG pay for venue costs?"}).json()
    assert r["citations"] and r["citations"][0]["title"]


def test_reviewer_queue_and_submit():
    rows = client.get("/api/reviewer/queue").json()
    assert {r["verdict"] for r in rows} == {"ready", "risk", "reject"}
    assert all(r["summary"] and "TODO" not in r["summary"] for r in rows)
    ev = {**DEMOS["blockers"], "name": "Submitted Diwali"}
    assert client.post("/api/reviewer/submit", json={"event": ev}).json()["ok"]
    rows = client.get("/api/reviewer/queue").json()
    assert rows[0]["name"] == "Submitted Diwali" and rows[0]["source"] == "submitted"
    assert rows[0]["verdict"] == "reject"  # verdict comes from the engine, not the submitter


def test_grounded_catches_number_words():
    assert not llm.grounded("the fifth event", "limit is 4")
    assert llm.grounded("the fifth event", "event #5")
