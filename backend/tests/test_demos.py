"""Run: cd backend && python -m pytest -q   (everyone runs this before merging)"""
import json

from fastapi.testclient import TestClient

from app import engine
from app.main import app

client = TestClient(app)
DEMOS = {d["id"]: d for d in json.loads((engine.BASE / "demo_events.json").read_text())}


def test_demo_verdicts():
    assert engine.check(DEMOS["ready"])["verdict"] == "ready"
    assert engine.check(DEMOS["at_risk"])["verdict"] == "risk"
    assert engine.check(DEMOS["blockers"])["verdict"] == "reject"


def test_api_check():
    r = client.post("/api/check", json=DEMOS["blockers"])
    assert r.status_code == 200 and r.json()["verdict"] == "reject"


def test_fix_loop_changes_verdict():
    ev = json.loads(json.dumps(DEMOS["at_risk"]))
    ev["venue"]["confirmed"] = True
    ev["org"]["usg_funds_low"] = False
    ev["date"] = "2027-03-04"
    assert engine.check(ev)["verdict"] in ("ready", "risk")


def test_endpoints_alive():
    for path in ["/api/health", "/api/demo", "/api/reviewer/queue"]:
        assert client.get(path).status_code == 200
    assert client.post("/api/extract", json={"text": "x"}).status_code == 200
    assert client.post("/api/ask", json={"question": "x"}).status_code == 200
