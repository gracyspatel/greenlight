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
    from app.routers.pack import PURPOSE, facts
    allowed = "\n".join(facts(res["event"]).values()) + "\n" + PURPOSE
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


def test_calendar_colors_dates_by_deadlines_only():
    ev = DEMOS["blockers"]  # Diwali, as_of 2026-11-15; has a venue-cap problem that is NOT date-related
    days = client.post("/api/calendar", json={"event": ev, "start": "2026-11-10", "days": 62}).json()
    by = {d["date"]: d for d in days}
    assert by["2026-11-12"]["level"] == "past"
    assert by["2026-12-12"]["level"] == "reject" and by["2026-12-12"]["reasons"]
    assert all("Venue costs" not in r for d in days for r in d["reasons"])
    # the calendar never changes the event; /check still sees the original date
    assert client.post("/api/check", json=ev).json()["event"]["date"] == "2026-12-12"


def test_calendar_has_green_days_far_enough_out():
    ev = {**DEMOS["ready"]}
    days = client.post("/api/calendar", json={"event": ev, "start": "2027-03-01", "days": 31}).json()
    assert any(d["level"] == "ready" for d in days)


def test_calendar_never_rates_a_break_day_ready():
    for ev in (DEMOS["ready"], {"name": "x", "as_of": "2026-11-15", "venue": {"on_campus": False}}):
        days = client.post("/api/calendar", json={"event": ev, "start": "2026-12-10", "days": 62}).json()
        for d in days:
            if engine.break_on(engine._date(d["date"])):
                assert d["level"] != "ready", d


def test_ask_never_shows_our_internal_notes():
    from app.routers.extras import load_chunks
    for c in load_chunks():
        assert "rules.json" not in c["text"] and "as fetched" not in c["text"], c["title"]
    r = client.post("/api/ask", json={"question": "What is the venue cap?"}).json()
    assert "rules.json" not in r["answer"] and "$4,000" in r["answer"]


def test_ask_weak_match_falls_back_to_email():
    for q in ("Who is the USG president?", "When is the UEPA due?"):
        r = client.post("/api/ask", json={"question": q}).json()
        assert "usgfunds@usc.edu" in r["answer"] and r["citations"] == [], q


def test_ask_alcohol_is_not_a_generic_gsg_paragraph():
    r = client.post("/api/ask", json={"question": "Can USG pay for alcohol?"}).json()
    assert "GSG" not in r["answer"]
    assert "Alcoholic beverages" in r["answer"] or "usgfunds@usc.edu" in r["answer"]
