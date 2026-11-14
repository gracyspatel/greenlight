"""Owner: Split B (rules engine + API). Endpoints: /check, /demo, /demo/{id}."""
import json

from fastapi import APIRouter, HTTPException

from .. import engine

router = APIRouter(tags=["check"])
DEMOS = json.loads((engine.BASE / "demo_events.json").read_text())


@router.post("/check")
def check(event: dict):
    """Event JSON (see docs/CONTRACTS.md) -> full CheckResponse."""
    return engine.check(event)


@router.get("/demo")
def list_demos():
    return [{"id": d["id"], "name": d["name"]} for d in DEMOS]


@router.get("/demo/{demo_id}")
def get_demo(demo_id: str):
    for d in DEMOS:
        if d["id"] == demo_id:
            return d
    raise HTTPException(404, "no such demo")
