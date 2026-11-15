"""One pass + one fail test per rule id in rules.json, plus deadlines, breaks, ordering
and tracking. Run: cd backend && python -m pytest -q"""
import copy
import datetime as dt
import json

import pytest

from app import engine

DEMOS = {d["id"]: d for d in json.loads((engine.BASE / "demo_events.json").read_text())}
RULE_IDS = {r["id"] for r in engine.RULES["rules"]}


def base(**changes):
    """The 'ready' demo (passes everything) with some fields changed."""
    ev = copy.deepcopy(DEMOS["ready"])
    for path, value in changes.items():
        o, keys = ev, path.split("__")
        for k in keys[:-1]:
            o = o.setdefault(k, {})
        o[keys[-1]] = value
    return ev


def flags(ev):
    return {f["rule_id"]: f for a in engine.check(ev)["approvals"] for f in a["flags"]}


# rule id -> (event that FAILS the rule, expected level, event that PASSES it)
CASES = {
    "usg_event_cap": (base(org__funded_events_this_semester=4), "reject",
                      base(org__funded_events_this_semester=3)),
    "usg_annual_cap": (base(org__usg_received_this_year=7000), "reject",
                       base(org__usg_received_this_year=1000)),
    "usg_venue_cap": (base(budget_lines=[{"item": "Hall", "category": "venue", "amount": 4001, "quote_attached": True}]),
                      "reject",
                      base(budget_lines=[{"item": "Hall", "category": "venue", "amount": 4000, "quote_attached": True}])),
    "food_vendor": (base(food__sold=True, food__vendor_approved=False), "reject",
                    base(food__sold=True, food__vendor_approved=True)),
    "uepa_needs_venue": (base(venue__confirmed=False), "risk", base(venue__confirmed=True)),
    "disc_other_funding": (base(org__other_university_funding=True), "risk", base()),
    "disc_past_misuse": (base(org__past_misuse=True), "risk", base()),
    "disc_low_funds": (base(org__usg_funds_low=True), "risk", base()),
}


def test_every_rule_has_a_test():
    assert set(CASES) == RULE_IDS, f"add a CASES entry for: {RULE_IDS ^ set(CASES)}"


def test_base_event_is_clean():
    assert engine.check(base())["verdict"] == "ready"


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_rule_fails(rule_id):
    bad, level, _ = CASES[rule_id]
    f = flags(bad)
    assert rule_id in f, f"{rule_id} should flag"
    assert f[rule_id]["level"] == level
    # every flag quotes the stored rule text and source, never model text
    rule = next(r for r in engine.RULES["rules"] if r["id"] == rule_id)
    assert f[rule_id]["rule_text"] == rule["text"] and f[rule_id]["source"] == rule["source"]


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_rule_passes(rule_id):
    _, _, good = CASES[rule_id]
    assert rule_id not in flags(good)


def test_annual_cap_near_is_risk():
    f = flags(base(org__usg_received_this_year=5800))  # 5800 + 1200 = 7000 >= 0.85 * 8000
    assert f["usg_annual_cap"]["level"] == "risk"


def test_annual_cap_allows_exactly_the_cap():
    # "maximum of $8,000" (confirmed by the team): exactly 8,000 is allowed, 1 dollar more is not
    f = flags(base(org__usg_received_this_year=6800))  # 6800 + 1200 = 8000
    assert f["usg_annual_cap"]["level"] == "risk"   # allowed, but close to the cap
    f = flags(base(org__usg_received_this_year=6801))  # 8001
    assert f["usg_annual_cap"]["level"] == "reject"
    assert "$1" in f["usg_annual_cap"]["fix"]       # cut by at least $1


def test_event_cap_counts_this_event():
    assert "usg_event_cap" in flags(base(org__funded_events_this_semester=4))  # this = #5


# ---------------------------------------------------------------- deadlines
def test_deadline_passed_rejects_and_suggests_date():
    ev = base(date="2026-12-01")  # as_of 2026-11-15: USG 6-week deadline long gone
    f = flags(ev)["usg_funding_deadline"]
    assert f["level"] == "reject" and "or later" in f["fix"]


def test_deadline_soon_is_risk():
    ev = base(**{"date": "2026-12-27", "as_of": "2026-11-20"})  # venue: 35 days -> Nov 22
    assert flags(ev)["venue_request_deadline"]["level"] == "risk"


def test_venue_deadline_is_35_days():
    r = engine.check(base())
    venue = next(a for a in r["approvals"] if a["id"] == "venue_request")
    assert venue["deadline"] == (dt.date(2027, 3, 4) - dt.timedelta(days=35)).isoformat()


def test_usg_deadline_is_a_wednesday():
    r = engine.check(base())
    usg = next(a for a in r["approvals"] if a["id"] == "usg_funding")
    assert dt.date.fromisoformat(usg["deadline"]).weekday() == 2
    assert "11:59 PM" in usg["deadline_label"]


def test_winter_break_weeks_do_not_count():
    # Event Jan 27, 2027: six plain weeks back lands inside winter break; break weeks are skipped,
    # so the deadline is pushed weeks earlier, and the window is flagged.
    d, touched = engine.academic_weeks_back(dt.date(2027, 1, 27), 6, "Wednesday")
    naive = dt.date(2027, 1, 27) - dt.timedelta(weeks=6)
    assert d < naive - dt.timedelta(days=14)
    assert "Winter break" in touched
    assert d.weekday() == 2


def test_break_crossing_flag():
    ev = base(date="2027-01-27", as_of="2026-10-01")
    assert flags(ev)["usg_funding_breaks"]["level"] == "risk"


def test_no_break_no_flag():
    assert "usg_funding_breaks" not in flags(base())


def test_fmt_has_no_leading_zero():
    assert engine.fmt(dt.date(2026, 12, 5)) == "Sat Dec 5, 2026"


# ---------------------------------------------------------------- ordering + tracking
def test_social_dance_form_waits_on_start():
    ev = base(dancing=True, date="2027-04-20", as_of="2026-11-15")
    assert flags(ev)["social_dance_form_order"]["level"] == "risk"
    ev["tracking"] = {"social_dance_start": {"status": "approved"}}
    assert "social_dance_form_order" not in flags(ev)


def test_approved_clears_flags():
    ev = copy.deepcopy(DEMOS["blockers"])
    ev["tracking"] = {"catering": {"status": "approved"}}
    cat = next(a for a in engine.check(ev)["approvals"] if a["id"] == "catering")
    assert cat["verdict"] == "ready" and cat["flags"] == [] and cat["color"] == "done"


def test_returned_is_risk():
    ev = base(tracking={"venue_request": {"status": "returned"}})
    assert flags(ev)["venue_request_returned"]["level"] == "risk"


def test_submitted_stops_deadline_flag():
    ev = base(date="2026-12-01", tracking={"usg_funding": {"status": "submitted"}})
    assert "usg_funding_deadline" not in flags(ev)


# ---------------------------------------------------------------- triggers + robustness
def test_triggers():
    ids = {a["id"] for a in engine.check(DEMOS["blockers"])["approvals"]}
    assert {"usg_funding", "venue_request", "uepa", "catering", "fundraising_ca",
            "fundraising_bh", "social_dance_start", "social_dance_form"} <= ids
    assert "gsg_funding" not in ids


def test_off_campus_needs_no_venue_or_uepa():
    ids = {a["id"] for a in engine.check(base(venue__on_campus=False))["approvals"]}
    assert "venue_request" not in ids and "uepa" not in ids


def test_empty_event_does_not_crash():
    r = engine.check({})
    assert r["verdict_label"] == "Needs info" and r["questions"]


def test_every_rule_has_source_and_known_check():
    known = {"usg_event_cap", "usg_annual_cap", "usg_venue_cap", "vendor_quotes",
             "food_vendor", "venue_confirmed", "flag"}
    for r in engine.RULES["rules"]:
        assert r["source"].startswith("https://") and r["text"]
        assert r["check"] in known
        assert r["approval"] in engine.APPROVALS


def test_missing_facts_are_never_ready():
    # a date but no venue, attendance or budget: open questions mean "Needs info", not Ready
    ev = {"name": "Movie night", "date": "2027-03-10", "as_of": "2026-11-15",
          "funding_source": "USG", "amount_requested": 300}
    r = engine.check(ev)
    assert r["questions"] and r["verdict"] != "ready"
    # off campus: no venue/UEPA flags, so only the missing facts stand between it and Ready
    r = engine.check({**ev, "venue": {"on_campus": False}})
    assert r["questions"] and r["verdict_label"] == "Needs info" and r["verdict"] == "risk"


def test_approvals_come_in_the_order_they_are_done():
    ids = [a["id"] for a in engine.check(DEMOS["blockers"])["approvals"]]
    # the USG application needs the venue confirmation, the food form and the UEPA ID first
    assert ids.index("venue_request") < ids.index("catering") < ids.index("uepa") < ids.index("usg_funding")
    assert ids.index("social_dance_start") < ids.index("social_dance_form")
    assert ids.index("fundraising_ca") < ids.index("fundraising_bh")
    assert ids[0] == "social_dance_start"  # longest lead time: start it first
    orders = [a["order"] for a in engine.check(DEMOS["blockers"])["approvals"]]
    assert orders == list(range(1, len(orders) + 1))


def test_worst_flag_first_inside_an_approval():
    for a in engine.check(DEMOS["blockers"])["approvals"]:
        levels = [engine.LEVEL_RANK[f["level"]] for f in a["flags"]]
        assert levels == sorted(levels, reverse=True)


def test_every_approval_has_a_step():
    assert all(isinstance(a.get("step"), int) for a in engine.RULES["approvals"])
