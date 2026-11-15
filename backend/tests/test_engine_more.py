"""Rules engine, beyond one pass/fail per rule: every approval's trigger and deadline,
boundaries, colors, ordering, input clean-up, and the shape of every flag.
No LLM anywhere in here. Run: cd backend && python -m pytest -q"""
import copy
import datetime as dt
import json

import pytest

from app import engine

DEMOS = {d["id"]: d for d in json.loads((engine.BASE / "demo_events.json").read_text())}
AS_OF = dt.date(2026, 11, 15)
APPROVALS = engine.APPROVALS


def event(**over):
    """A minimal clean event: nothing triggered, far-future date."""
    ev = {"name": "Test", "as_of": AS_OF.isoformat(), "date": "2027-04-28",
          "venue": {"name": "Somewhere", "on_campus": False, "confirmed": True},
          "attendance": 50, "funding_source": "none", "budget_lines": [], "org": {}, "tracking": {}}
    ev.update(over)
    return ev


def approval(result, aid):
    return next(a for a in result["approvals"] if a["id"] == aid)


def ids(result):
    return {a["id"] for a in result["approvals"]}


def all_flags(result):
    return [f for a in result["approvals"] for f in a["flags"]]


# ---------------------------------------------------------------- triggers
TRIGGER_EVENTS = {
    "funding_usg": event(funding_source="USG", amount_requested=100,
                         budget_lines=[{"item": "x", "category": "other", "amount": 100, "quote_attached": True}]),
    "funding_gsg": event(funding_source="GSG", amount_requested=100,
                         budget_lines=[{"item": "x", "category": "other", "amount": 100, "quote_attached": True}]),
    "on_campus_venue": event(venue={"name": "TCC 450", "on_campus": True, "confirmed": True}),
    "food": event(food={"served": True}),
    "ticket_sales": event(ticket_sales=True),
    "dancing": event(dancing=True),
}


def test_plain_event_needs_no_approvals():
    r = engine.check(event())
    assert r["approvals"] == [] and r["verdict"] == "ready"


@pytest.mark.parametrize("aid", sorted(APPROVALS))
def test_each_approval_is_triggered_by_its_feature(aid):
    trigger = APPROVALS[aid]["trigger"]
    assert aid in ids(engine.check(TRIGGER_EVENTS[trigger]))


@pytest.mark.parametrize("trigger", sorted(TRIGGER_EVENTS))
def test_each_feature_triggers_only_its_approvals(trigger):
    expected = {aid for aid, a in APPROVALS.items() if a["trigger"] == trigger}
    assert ids(engine.check(TRIGGER_EVENTS[trigger])) == expected


def test_food_sold_but_not_served_still_triggers_catering():
    assert "catering" in ids(engine.check(event(food={"sold": True})))


def test_gsg_funding_skips_usg_rules():
    ev = copy.deepcopy(TRIGGER_EVENTS["funding_gsg"])
    ev["org"] = {"funded_events_this_semester": 10, "usg_received_this_year": 99999}
    r = engine.check(ev)
    assert "usg_funding" not in ids(r)
    assert not {"usg_event_cap", "usg_annual_cap"} & {f["rule_id"] for f in all_flags(r)}


# ---------------------------------------------------------------- deadlines
DAY_LEADS = sorted(aid for aid, a in APPROVALS.items() if a.get("lead") and "days" in a["lead"])


@pytest.mark.parametrize("aid", DAY_LEADS)
def test_day_based_deadline_is_event_minus_lead(aid):
    trigger = APPROVALS[aid]["trigger"]
    r = engine.check(TRIGGER_EVENTS[trigger])
    want = dt.date(2027, 4, 28) - dt.timedelta(days=APPROVALS[aid]["lead"]["days"])
    assert approval(r, aid)["deadline"] == want.isoformat()


def test_catering_has_no_fixed_deadline():
    a = approval(engine.check(event(food={"served": True})), "catering")
    assert a["deadline"] is None and a["days_left"] is None and a["color"] == "none"
    assert "No fixed lead time" in a["deadline_label"]


def _venue_event(days_left: int):
    """On-campus event whose venue deadline (35 days) is `days_left` days after AS_OF."""
    date = AS_OF + dt.timedelta(days=35 + days_left)
    return event(date=date.isoformat(), venue={"name": "TCC 450", "on_campus": True, "confirmed": True})


@pytest.mark.parametrize("days_left, level, color", [
    (-1, "reject", "red"),
    (0, "risk", "yellow"),
    (7, "risk", "yellow"),
    (8, None, "green"),
])
def test_deadline_boundaries(days_left, level, color):
    a = approval(engine.check(_venue_event(days_left)), "venue_request")
    assert a["days_left"] == days_left and a["color"] == color
    f = next((f for f in a["flags"] if f["rule_id"] == "venue_request_deadline"), None)
    assert (f["level"] if f else None) == level


def test_passed_deadline_message_counts_days():
    a = approval(engine.check(_venue_event(-10)), "venue_request")
    f = next(f for f in a["flags"] if f["rule_id"] == "venue_request_deadline")
    assert f["message"] == "Deadline passed 10 day(s) ago."


DATED = sorted(aid for aid, a in APPROVALS.items() if a.get("lead"))


@pytest.mark.parametrize("aid", DATED)
def test_suggested_earliest_date_really_works(aid):
    """When a deadline is missed, the fix suggests a new date. Moving there must clear it."""
    earliest = engine.earliest_event_date(APPROVALS[aid], AS_OF)
    assert earliest is not None and earliest >= AS_OF
    deadline, _ = engine.deadline_for(APPROVALS[aid], earliest)
    assert deadline >= AS_OF                        # that date works...
    before, _ = engine.deadline_for(APPROVALS[aid], earliest - dt.timedelta(days=1))
    assert before < AS_OF                           # ...and it's the earliest one that does


def test_day_based_deadlines_never_report_breaks():
    for aid in DAY_LEADS:
        _, breaks = engine.deadline_for(APPROVALS[aid], dt.date(2027, 1, 20))
        assert breaks == []


def test_thanksgiving_week_is_skipped():
    d, touched = engine.academic_weeks_back(dt.date(2026, 12, 9), 6, "Wednesday")
    assert "Thanksgiving break" in touched
    assert d < dt.date(2026, 12, 9) - dt.timedelta(weeks=6)


def test_as_of_overrides_today():
    ev = event(as_of=None, venue={"name": "TCC 450", "on_campus": True, "confirmed": True})
    r = engine.check(ev, today=dt.date(2027, 4, 1))
    assert r["as_of"] == "2027-04-01"
    assert approval(r, "venue_request")["color"] == "red"


# ---------------------------------------------------------------- ordering
def test_fundraising_bh_waits_on_fundraising_ca():
    r = engine.check(event(ticket_sales=True))
    assert "fundraising_bh_order" in {f["rule_id"] for f in approval(r, "fundraising_bh")["flags"]}
    assert approval(r, "fundraising_bh")["depends_on"] == ["fundraising_ca"]


def test_order_flag_clears_once_dependency_approved():
    ev = event(ticket_sales=True, tracking={"fundraising_ca": {"status": "approved"}})
    flags = {f["rule_id"] for f in approval(engine.check(ev), "fundraising_bh")["flags"]}
    assert "fundraising_bh_order" not in flags


def test_order_flag_stays_while_dependency_only_submitted():
    ev = event(ticket_sales=True, tracking={"fundraising_ca": {"status": "submitted"}})
    flags = {f["rule_id"] for f in approval(engine.check(ev), "fundraising_bh")["flags"]}
    assert "fundraising_bh_order" in flags


def test_uepa_uses_venue_rule_not_order_flag():
    ev = event(venue={"name": "TCC 450", "on_campus": True, "confirmed": False})
    flags = {f["rule_id"] for f in approval(engine.check(ev), "uepa")["flags"]}
    assert "uepa_order" not in flags and "uepa_needs_venue" in flags


def test_depends_on_only_lists_needed_approvals():
    for a in engine.check(DEMOS["blockers"])["approvals"]:
        assert set(a["depends_on"]) <= ids(engine.check(DEMOS["blockers"]))


# ---------------------------------------------------------------- cap boundaries
def _usg(**org):
    ev = copy.deepcopy(DEMOS["ready"])  # asks $1,200, passes everything
    ev["org"].update(org)
    return ev


@pytest.mark.parametrize("received, level", [
    (5599, None),       # 6,799 total: under 85% of 8,000
    (5600, "risk"),     # 6,800 = exactly 85%
    (6800, "risk"),     # 8,000 = exactly the cap (allowed)
    (6801, "reject"),   # 8,001
])
def test_annual_cap_boundaries(received, level):
    f = {f["rule_id"]: f for f in all_flags(engine.check(_usg(usg_received_this_year=received)))}
    assert (f["usg_annual_cap"]["level"] if "usg_annual_cap" in f else None) == level


def test_venue_cap_adds_up_every_venue_line():
    ev = copy.deepcopy(DEMOS["ready"])
    ev["budget_lines"] = [
        {"item": "Hall", "category": "venue", "amount": 2000, "quote_attached": True},
        {"item": "AV room", "category": "venue", "amount": 2001, "quote_attached": True},
        {"item": "Food", "category": "food", "amount": 9000, "quote_attached": True},  # not venue
    ]
    f = {f["rule_id"]: f for f in all_flags(engine.check(ev))}
    assert f["usg_venue_cap"]["level"] == "reject" and "$4,001" in f["usg_venue_cap"]["message"]


def test_free_food_from_unapproved_vendor_is_fine():
    ev = event(food={"served": True, "sold": False, "vendor": "Pizza place", "vendor_approved": False})
    assert "food_vendor" not in {f["rule_id"] for f in all_flags(engine.check(ev))}


# ---------------------------------------------------------------- verdict + response shape
def test_worst_approval_decides_overall_verdict():
    for d in DEMOS.values():
        r = engine.check(d)
        worst = max((a["verdict"] for a in r["approvals"]), key=engine.LEVEL_RANK.get, default="ready")
        assert r["verdict"] == worst
        assert sum(r["counts"].values()) == len(r["approvals"])


def test_approvals_sorted_by_deadline_with_undated_last():
    r = engine.check(DEMOS["blockers"])
    keys = [a["deadline"] or "9999" for a in r["approvals"]]
    assert keys == sorted(keys) and r["approvals"][-1]["deadline"] is None  # catering


def test_no_date_means_needs_info():
    r = engine.check(event(date=None, food={"served": True}))
    assert r["verdict_label"] == "Needs info" and r["verdict"] == "risk"
    assert "What date is the event?" in r["questions"]


def test_disclaimer_always_present():
    for d in list(DEMOS.values()) + [{}]:
        assert "final decision is still USG's" in engine.check(d)["disclaimer"]


SCENARIOS = list(DEMOS.values()) + [
    _venue_event(-3), _venue_event(3), event(ticket_sales=True, dancing=True, food={"sold": True}),
    event(date="2027-01-27", as_of="2026-10-01", funding_source="USG", amount_requested=5000,
          budget_lines=[{"item": "Hall", "category": "venue", "amount": 5000}],
          org={"funded_events_this_semester": 9, "usg_received_this_year": 7000,
               "past_misuse": True, "usg_funds_low": True, "other_university_funding": True}),
]


@pytest.mark.parametrize("ev", SCENARIOS, ids=lambda e: e.get("name", "?") + "-" + str(e.get("date")))
def test_every_flag_is_complete_and_fully_formatted(ev):
    for f in all_flags(engine.check(ev)):
        assert f["level"] in ("risk", "reject")
        assert f["message"] and f["fix"] and f["rule_text"]
        assert f["source"].startswith("https://"), f["rule_id"]
        for text in (f["message"], f["fix"]):
            assert "{" not in text and "}" not in text, f"unfilled placeholder in {f['rule_id']}: {text}"


def test_flag_text_always_comes_from_rules_json():
    stored = {r["text"] for r in engine.RULES["rules"]} | {a["text"] for a in engine.RULES["approvals"]} \
        | {g["text"] for g in engine.GENERIC.values() if "text" in g}
    for ev in SCENARIOS:
        for f in all_flags(engine.check(ev)):
            assert f["rule_text"] in stored, f["rule_id"]


# ---------------------------------------------------------------- normalize (messy input)
def test_normalize_cleans_messy_types():
    ev = engine.normalize({
        "funding_source": "usg", "amount_requested": "3500", "dancing": 1,
        "budget_lines": [{"item": "Hall", "category": "VENUE", "amount": "abc"}],
        "org": {"funded_events_this_semester": "2", "usg_received_this_year": None},
    })
    assert ev["funding_source"] == "USG" and ev["amount_requested"] == 3500.0 and ev["dancing"] is True
    assert ev["budget_lines"][0] == {"item": "Hall", "category": "venue", "amount": 0.0, "quote_attached": False}
    assert ev["org"]["funded_events_this_semester"] == 2 and ev["org"]["usg_received_this_year"] == 0.0


@pytest.mark.parametrize("src, want", [("GSG", "GSG"), ("gsg", "GSG"), ("Other", "none"), (None, "none"), ("", "none")])
def test_normalize_funding_source(src, want):
    assert engine.normalize({"funding_source": src})["funding_source"] == want


def test_normalize_does_not_change_the_input():
    raw = {"venue": {"name": "X"}, "food": {"served": 1}}
    before = copy.deepcopy(raw)
    engine.normalize(raw)
    engine.check(raw)
    assert raw == before


@pytest.mark.parametrize("bad", [
    {"date": "not a date"}, {"date": "2027-02-30"}, {"amount_requested": None, "funding_source": "USG"},
    {"budget_lines": None, "org": None, "venue": None, "food": None, "tracking": None},
    {"tracking": {"usg_funding": {"status": "weird"}}, "funding_source": "USG"},
])
def test_bad_input_does_not_crash(bad):
    r = engine.check(bad)
    assert r["verdict"] in ("ready", "risk", "reject")


def test_missing_questions_ask_for_each_missing_field():
    q = engine.missing_questions(engine.normalize({"funding_source": "USG"}))
    assert q == ["What date is the event?", "Where is it being held, and is that on campus?",
                 "About how many people do you expect?",
                 "What are the budget lines (item, category, amount)?", "How much are you requesting?"]
    assert engine.missing_questions(engine.normalize(DEMOS["ready"])) == []
