"""/extract with no LLM key: the fix-bugs cases (negated food sales, bare "GSG $2,000", ticket prices aren't costs...)."""
import json

from fastapi.testclient import TestClient

from app import engine
from app.main import app

client = TestClient(app)
AS_OF = {"as_of": "2026-11-15"}


def extract(text, event=AS_OF):
    return client.post("/api/extract", json={"text": text, "event": event}).json()["event"]


def test_negated_food_sale_and_bare_gsg_amount():
    ev = extract("Gala on 12/31, 500 guests, not selling food, no tickets. GSG $2,000.")
    assert ev["food"]["sold"] is False
    assert ev["ticket_sales"] is False
    assert ev["funding_source"] == "GSG" and ev["amount_requested"] == 2000
    assert ev["attendance"] == 500 and ev["date"] == "2026-12-31"


def test_ticket_price_is_not_a_budget_line():
    ev = extract("Off-campus boat party in Long Beach on April 10, 200 people, selling tickets at $20 each")
    assert ev["budget_lines"] == []
    assert ev["ticket_sales"] is True and ev["venue"]["on_campus"] is False


def test_free_popcorn_is_food():
    ev = extract("Movie night next Friday at Bovard, 80 people, free popcorn")
    assert ev["food"]["served"] is True and ev["food"]["sold"] is False
    assert ev["name"] == "Movie night"


def test_bake_sale_sells_food_and_name_has_no_date():
    ev = extract("Bake sale Jan 20 on Trousdale, selling cookies we bake ourselves")
    assert ev["food"]["sold"] is True and ev["food"]["served"] is True
    assert ev["name"] == "Bake sale" and ev["date"] == "2027-01-20"
    assert ev["ticket_sales"] is True  # the fundraising form covers food cash sales


def test_demo_texts_still_extract_to_their_verdicts():
    want = {"ready": "ready", "at_risk": "risk", "blockers": "reject"}
    for d in json.loads((engine.BASE / "demo_events.json").read_text()):
        ev = extract(d["text"], {"as_of": d["as_of"]})
        r = engine.check(ev)
        assert r["verdict"] == want[d["id"]] and r["verdict_label"] != "Needs info", d["id"]
