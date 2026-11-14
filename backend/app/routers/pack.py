"""Owner: Split B. Endpoint: POST /pack  CheckResponse -> [{approval_id, system, link, draft}].

TODO(Split B): LLM-draft the text an officer pastes into each system (EngageSC funding
form, TES venue request, UEPA...). Use only facts from the event. Fall back to the template.
"""
from fastapi import APIRouter

from .. import llm  # noqa: F401

router = APIRouter(tags=["pack"])


@router.post("/pack")
def pack(check_result: dict):
    # TODO(Split A): LLM-drafted text per approval. Stub returns a template.
    ev = check_result.get("event", {})
    return [
        {"approval_id": a["id"], "system": a["system"], "link": a["link"],
         "draft": f"{ev.get('name','')} on {ev.get('date','')} at {ev.get('venue',{}).get('name','')}, ~{ev.get('attendance','?')} attendees."}
        for a in check_result.get("approvals", [])
    ]
