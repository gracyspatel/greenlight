"""/extract with no LLM key (conftest blanks it): the code-only reader must pull the right
fields out of plain text, and the 3 demo texts must reach the same verdicts as the demo JSON."""
import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from app import engine
from app.main import app
from app.routers import intake

client = TestClient(app)
DEMOS = {d["id"]: d for d in json.loads((engine.BASE / "demo_events.json").read_text())}
TODAY = dt.date(2026, 11, 15)  # a Sunday, same as the demos' as_of


def extract(text, event=None):
    r = client.post("/api/extract", json={"text": text, "event": event or {"as_of": TODAY.isoformat()}})
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------- the demo texts end to end
@pytest.mark.parametrize("demo_id", sorted(DEMOS))
def test_demo_text_gives_the_demo_verdict(demo_id):
    d = DEMOS[demo_id]
    ev = extract(d["text"], {"as_of": d["as_of"]})["event"]
    assert engine.check(ev)["verdict"] == engine.check(d)["verdict"]


@pytest.mark.parametrize("demo_id", sorted(DEMOS))
def test_demo_text_key_fields_match_demo_json(demo_id):
    d = DEMOS[demo_id]
    ev = extract(d["text"], {"as_of": d["as_of"]})["event"]
    assert ev["date"] == d["date"]
    assert ev["attendance"] == d["attendance"]
    assert ev["amount_requested"] == d["amount_requested"]
    assert ev["funding_source"] == d["funding_source"]
    assert ev["dancing"] == d["dancing"] and ev["ticket_sales"] == d["ticket_sales"]
    assert ev["venue"]["confirmed"] == d["venue"]["confirmed"]
    assert sorted(l["amount"] for l in ev["budget_lines"]) == sorted(l["amount"] for l in d["budget_lines"])


# ---------------------------------------------------------------- dates
@pytest.mark.parametrize("text, want", [
    ("on 2027-03-04", dt.date(2027, 3, 4)),
    ("on Dec 12", dt.date(2026, 12, 12)),
    ("on December 12th", dt.date(2026, 12, 12)),
    ("on 12th of December", dt.date(2026, 12, 12)),
    ("on March 4, 2027", dt.date(2027, 3, 4)),
    ("on 3/4/2027", dt.date(2027, 3, 4)),
    ("on 3/4/27", dt.date(2027, 3, 4)),
    ("on Nov 1", dt.date(2027, 11, 1)),          # already passed this year -> next year
    ("tomorrow", dt.date(2026, 11, 16)),
    ("in 2 weeks", dt.date(2026, 11, 29)),
    ("in three days", dt.date(2026, 11, 18)),
    ("this Friday", dt.date(2026, 11, 20)),
    ("next Friday", dt.date(2026, 11, 20)),      # today is Sunday: this week is over, so the coming Friday
])
def test_find_dates(text, want):
    assert intake.find_dates(text, TODAY)[0] == want


def test_this_vs_next_weekday_mid_week():
    wed = dt.date(2026, 11, 18)
    assert intake.find_dates("this Friday", wed) == [dt.date(2026, 11, 20)]
    assert intake.find_dates("next Friday", wed) == [dt.date(2026, 11, 27)]  # skips this week's


def test_find_dates_skips_impossible_dates():
    assert intake.find_dates("on Feb 30 2027 or 13/45", TODAY) == []


# ---------------------------------------------------------------- amounts + numbers
@pytest.mark.parametrize("text, want", [
    ("$3,500", 3500), ("$3.5k", 3500), ("$ 600", 600), ("600 dollars", 600), ("$1.2K", 1200), ("$45.50", 45.5),
])
def test_find_amounts(text, want):
    assert intake.find_amounts(text)[0][2] == want


def test_numbers_in_reads_digits_and_words():
    nums = intake.numbers_in("four events, about 300 people, $3.5k")
    assert {4.0, 300.0, 3500.0} <= nums


# ---------------------------------------------------------------- fields from plain text
def test_full_sentence():
    ev = extract("Holi Fest on March 20 2027 at Alumni Park, around 200 students. Asking USG for $2,000. "
                 "Costs: decorations $500, DJ $700.")["event"]
    assert ev["name"] == "Holi Fest" and ev["date"] == "2027-03-20" and ev["attendance"] == 200
    assert ev["venue"]["name"] == "Alumni Park" and ev["venue"]["on_campus"] is True
    assert ev["funding_source"] == "USG" and ev["amount_requested"] == 2000
    cats = {l["item"].lower(): l["category"] for l in ev["budget_lines"]}
    assert cats.get("decorations") == "supplies" and cats.get("dj") == "entertainment"


@pytest.mark.parametrize("text, field, want", [
    ("There will be dancing.", "dancing", True),
    ("No dancing at this event.", "dancing", False),
    ("We are selling tickets.", "ticket_sales", True),
    ("Free entry, no tickets.", "ticket_sales", False),
])
def test_yes_and_no_features(text, field, want):
    assert extract("Mixer on Dec 12. " + text)["event"][field] is want


def test_free_food_is_served_not_sold():
    food = extract("Study Night on Dec 12 with free food from USC Hospitality.")["event"]["food"]
    assert food["served"] is True and food["sold"] is False
    assert food["vendor"] == "USC Hospitality" and food["vendor_approved"] is True


def test_selling_food_is_sold():
    food = extract("Bake Sale on Dec 12, we sell food from a local restaurant.")["event"]["food"]
    assert food["sold"] is True and food["vendor_approved"] is False


def test_off_campus_event_needs_no_campus_approvals():
    ev = extract("Formal on Dec 12 at a hotel downtown, off-campus, 100 people.")["event"]
    assert ev["venue"]["on_campus"] is False
    ids = {a["id"] for a in engine.check(ev)["approvals"]}
    assert "venue_request" not in ids and "uepa" not in ids


@pytest.mark.parametrize("text, want", [
    ("The room is booked.", True), ("Room not booked yet.", False), ("Venue TBD.", False),
])
def test_venue_confirmed(text, want):
    assert extract("Mixer on Dec 12 in TCC 450. " + text)["event"]["venue"]["confirmed"] is want


@pytest.mark.parametrize("text, want", [("Asking GSG for $500.", "GSG"), ("Asking USG for $500.", "USG"),
                                        ("We are self-funded.", "none")])
def test_funding_source(text, want):
    assert extract("Mixer on Dec 12. " + text)["event"]["funding_source"] == want


def test_org_history_and_flags():
    ev = extract("Mixer on Dec 12. USG has funded 3 of our events this semester, $2,000 total this year. "
                 "We heard USG funds are running low. It's co-funded by another office.")["event"]
    assert ev["org"]["funded_events_this_semester"] == 3 and ev["org"]["usg_received_this_year"] == 2000
    assert ev["org"]["usg_funds_low"] is True and ev["org"]["other_university_funding"] is True


def test_quotes_attached():
    ev = extract("Mixer on Dec 12. Room rental $400, quotes attached.")["event"]
    assert ev["budget_lines"] and all(l["quote_attached"] for l in ev["budget_lines"])


# ---------------------------------------------------------------- follow-up answers
def test_bare_number_answers_attendance_question():
    old = {"as_of": TODAY.isoformat(), "name": "Diwali Night", "date": "2026-12-12"}
    ev = extract("Q: About how many people do you expect?\nA: 300", old)["event"]
    assert ev["attendance"] == 300 and ev["name"] == "Diwali Night" and ev["date"] == "2026-12-12"


def test_bare_amount_answers_request_question():
    old = {"as_of": TODAY.isoformat(), "name": "Mixer", "funding_source": "USG"}
    ev = extract("Q: How much are you requesting?\nA: $2.5k", old)["event"]
    assert ev["amount_requested"] == 2500 and ev["name"] == "Mixer"


VENUE_Q = "Q: Where is it being held, and is that on campus?\nA: "


def test_venue_answer_fills_venue():
    old = {"as_of": TODAY.isoformat(), "name": "Mixer"}
    assert extract(VENUE_Q + "The Lot", old)["event"]["venue"]["name"] == "The Lot"


@pytest.mark.xfail(strict=True, reason="BUG (Split A, intake.rule_extract): the off-campus check creates "
                   "ev['venue'] first, so the follow-up-answer branch ('venue' not in ev) is skipped and the "
                   "name is lost. Remove this marker once fixed.")
def test_venue_answer_with_off_campus_keeps_name():
    old = {"as_of": TODAY.isoformat(), "name": "Mixer"}
    ev = extract(VENUE_Q + "The Lot, off-campus", old)["event"]
    assert ev["venue"]["name"] == "The Lot" and ev["venue"]["on_campus"] is False


def test_follow_up_never_wipes_known_fields():
    old = extract(DEMOS["blockers"]["text"], {"as_of": DEMOS["blockers"]["as_of"]})["event"]
    ev = extract("Q: Anything else?\nA: nope", old)["event"]
    for k in ("name", "date", "attendance", "amount_requested", "budget_lines", "dancing"):
        assert ev[k] == old[k], k


# ---------------------------------------------------------------- questions + robustness
def test_missing_info_becomes_questions():
    q = extract("We want to do a thing.")["questions"]
    assert "What date is the event?" in q and "About how many people do you expect?" in q


def test_complete_text_asks_nothing_essential():
    q = extract(DEMOS["ready"]["text"], {"as_of": DEMOS["ready"]["as_of"]})["questions"]
    assert "What date is the event?" not in q and "About how many people do you expect?" not in q


@pytest.mark.parametrize("text", ["", "   ", "x", "$$$ ,,, ...", "🎉🎉🎉", "a" * 5000, "Q:\nA:"])
def test_odd_text_does_not_crash(text):
    out = extract(text)
    assert "event" in out and isinstance(out["questions"], list)
    engine.check(out["event"])


def test_deep_merge_rules():
    old = {"a": 1, "venue": {"name": "X", "confirmed": True}, "lines": [1]}
    new = {"a": None, "venue": {"confirmed": False}, "lines": [], "_private": 5, "questions": ["q"]}
    assert intake.deep_merge(old, new) == {"a": 1, "venue": {"name": "X", "confirmed": False}, "lines": [1]}
