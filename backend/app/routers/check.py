"""Owner: Split B (rules engine + API). Endpoints: /check, /calendar, /demo, /demo/{id}."""
import datetime as dt
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import engine

router = APIRouter(tags=["check"])
DEMOS = json.loads((engine.BASE / "demo_events.json").read_text())


@router.post("/check")
def check(event: dict):
    """Event JSON (see docs/CONTRACTS.md) -> full CheckResponse."""
    return engine.check(event)


class CalendarIn(BaseModel):
    event: dict
    start: str  # YYYY-MM-DD, first day to rate
    days: int = 42


@router.post("/calendar")
def calendar(body: CalendarIn):
    """Rate every candidate event date: does it meet every DEADLINE rule?
    Only date-driven flags (deadlines, breaks) count here; other problems (venue cap,
    vendor...) don't depend on the date, so they'd make every day look the same.
    The user picks the date; this only colors the calendar."""
    try:
        start = dt.date.fromisoformat(body.start[:10])
    except ValueError:
        raise HTTPException(400, "start must be YYYY-MM-DD")
    ev = engine.normalize(body.event)
    today = engine._date(ev.get("as_of")) or dt.date.today()
    out = []
    for i in range(max(1, min(body.days, 62))):
        d = start + dt.timedelta(days=i)
        if d < today:
            out.append({"date": d.isoformat(), "level": "past", "reasons": [], "notes": []})
            continue
        r = engine.check({**ev, "date": d.isoformat()})
        flags = [(a["name"], f) for a in r["approvals"] for f in a["flags"]
                 if f["rule_id"].endswith(("_deadline", "_breaks"))]
        # warnings (e.g. the window crosses a break) don't change the color; they become notes
        fixable = [(n, f) for n, f in flags if f["level"] != "warning"]
        level = max((f["level"] for _, f in fixable), key=engine.LEVEL_RANK.get, default="ready")
        reasons = [f"{name}: {f['message']}" for name, f in
                   sorted(fixable, key=lambda x: -engine.LEVEL_RANK[x[1]["level"]])]
        notes = [f"{name}: {f['message']}" for name, f in flags if f["level"] == "warning"]
        out.append({"date": d.isoformat(), "level": level, "reasons": reasons[:4], "notes": notes[:3]})
    return out


@router.get("/demo")
def list_demos():
    return [{"id": d["id"], "name": d["name"]} for d in DEMOS]


@router.get("/demo/{demo_id}")
def get_demo(demo_id: str):
    for d in DEMOS:
        if d["id"] == demo_id:
            return d
    raise HTTPException(404, "no such demo")
