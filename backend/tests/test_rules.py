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
def FOOD(amount, item="Catering"):
    return [{"item": item, "category": "food", "amount": amount, "quote_attached": True}]


CASES = {
    "usg_event_cap": (base(org__funded_events_this_semester=4), "reject",
                      base(org__funded_events_this_semester=3)),
    "usg_annual_cap": (base(org__usg_received_this_year=7000), "reject",
                       base(org__usg_received_this_year=1000)),
    "usg_venue_cap": (base(budget_lines=[{"item": "Hall", "category": "venue", "amount": 4001, "quote_attached": True}]),
                      "reject",
                      base(budget_lines=[{"item": "Hall", "category": "venue", "amount": 4000, "quote_attached": True}])),
    # selling food from a vendor that isn't an approved caterer (the list decides for listed vendors)
    "food_vendor": (base(food__sold=True, food__vendor="Local restaurant"), "reject",
                    base(food__sold=True, food__vendor="CAVA")),
    "usg_food_vendor_list": (base(food__vendor="Superette", budget_lines=FOOD(500)), "reject",
                             base(food__vendor="CAVA", budget_lines=FOOD(500))),
    "usg_food_cap": (base(food__vendor="CAVA", budget_lines=FOOD(80 * 36)), "reject",   # 80 people
                     base(food__vendor="CAVA", budget_lines=FOOD(80 * 35))),
    "usg_vendor_docs": (base(food__vendor="Sunlife Organics", budget_lines=FOOD(300)), "risk",
                        base(food__vendor="Cafe Dulce", budget_lines=FOOD(300))),
    "catering_vendor": (base(food__vendor="The Baked Bear", budget_lines=[]), "risk",
                        base(food__vendor="Cafe Dulce", budget_lines=[])),
    "uepa_needs_venue": (base(venue__confirmed=False), "risk", base(venue__confirmed=True)),
    "disc_other_funding": (base(org__other_university_funding=True), "warning", base()),
    "disc_past_misuse": (base(org__past_misuse=True), "warning", base()),
    "disc_low_funds": (base(org__usg_funds_low=True), "warning", base()),
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


def test_annual_cap_near_is_warning():
    f = flags(base(org__usg_received_this_year=5800))  # 5800 + 1200 = 7000 >= 0.85 * 8000
    assert f["usg_annual_cap"]["level"] == "warning"


def test_annual_cap_allows_exactly_the_cap():
    # "maximum of $8,000" (confirmed by the team): exactly 8,000 is allowed, 1 dollar more is not
    f = flags(base(org__usg_received_this_year=6800))  # 6800 + 1200 = 8000
    assert f["usg_annual_cap"]["level"] == "warning"   # allowed, but close to the cap
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
    assert flags(ev)["usg_funding_breaks"]["level"] == "warning"


def test_no_break_no_flag():
    assert "usg_funding_breaks" not in flags(base())


def test_fmt_has_no_leading_zero():
    assert engine.fmt(dt.date(2026, 12, 5)) == "Sat Dec 5, 2026"


# ---------------------------------------------------------------- ordering + tracking
def test_waiting_on_a_step_is_not_a_risk():
    # dancing + tickets, nothing submitted yet: waiting on step 1 is normal planning
    ev = base(dancing=True, ticket_sales=True, date="2027-04-20", as_of="2026-11-15")
    r = engine.check(ev)
    assert not any(f["rule_id"].endswith("_order") for a in r["approvals"] for f in a["flags"])
    assert r["verdict"] == "ready"
    form = next(a for a in r["approvals"] if a["id"] == "social_dance_form")
    assert form["depends_on"] == ["social_dance_start"]  # still shown as information


def test_filed_out_of_order_is_risk():
    ev = base(dancing=True, date="2027-04-20", as_of="2026-11-15",
              tracking={"social_dance_form": {"status": "submitted", "submitted_on": "2026-11-15"}})
    assert flags(ev)["social_dance_form_order"]["level"] == "risk"
    ev["tracking"]["social_dance_start"] = {"status": "approved"}
    assert "social_dance_form_order" not in flags(ev)


def test_approved_clears_flags():
    ev = copy.deepcopy(DEMOS["blockers"])
    ev["tracking"] = {"catering": {"status": "approved"}}
    cat = next(a for a in engine.check(ev)["approvals"] if a["id"] == "catering")
    assert cat["verdict"] == "ready" and cat["flags"] == [] and cat["color"] == "done"


def test_returned_is_risk():
    ev = base(tracking={"venue_request": {"status": "returned"}})
    assert flags(ev)["venue_request_returned"]["level"] == "risk"


def test_submitted_on_time_has_no_deadline_flag():
    # event Mar 4, 2027: USG deadline is in January; submitted on Nov 15 -> on time
    ev = base(tracking={"usg_funding": {"status": "submitted", "submitted_on": "2026-11-15"}})
    assert "usg_funding_deadline" not in flags(ev)


def test_submitted_late_keeps_the_missed_deadline():
    ev = base(date="2026-12-01", tracking={"usg_funding": {"status": "submitted", "submitted_on": "2026-11-15"}})
    f = flags(ev)["usg_funding_deadline"]
    assert f["level"] == "reject" and "Submitted after the deadline" in f["message"]
    # no submitted_on: compare against today (as_of)
    ev["tracking"]["usg_funding"].pop("submitted_on")
    assert flags(ev)["usg_funding_deadline"]["level"] == "reject"
    # approved still clears it
    ev["tracking"]["usg_funding"]["status"] = "approved"
    assert "usg_funding_deadline" not in flags(ev)


def test_marking_diwali_submitted_keeps_its_blockers():
    ev = copy.deepcopy(DEMOS["blockers"])
    before = engine.check(ev)["counts"]["reject"]
    ev["tracking"] = {a: {"status": "submitted", "submitted_on": ev["as_of"]}
                      for a in ("usg_funding", "social_dance_start", "social_dance_form")}
    assert engine.check(ev)["counts"]["reject"] == before


def test_tracking_tolerates_missing_or_odd_entries():
    r = engine.check(base(tracking={"usg_funding": None, "venue_request": {"status": "submitted"}}))
    assert r["verdict"] in ("ready", "risk", "reject")


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
             "food_vendor", "venue_confirmed", "flag",
             "usg_vendor_list", "food_cap", "vendor_docs", "catering_vendor"}
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


# ---------------------------------------------------------------- warnings
def test_warnings_never_block_ready():
    # funds low + close to the cap: things the club can't change -> still Ready, listed as warnings
    r = engine.check(base(org__usg_funds_low=True, org__usg_received_this_year=5800))
    assert r["verdict"] == "ready" and r["verdict_label"] == "Ready"
    assert r["counts"]["warning"] == 1 and r["counts"]["risk"] == 0
    usg = next(a for a in r["approvals"] if a["id"] == "usg_funding")
    assert usg["verdict"] == "warning" and usg["verdict_label"] == "Warning"
    assert {f["level"] for f in usg["flags"]} == {"warning"}


def test_fixable_problems_outrank_warnings():
    r = engine.check(base(org__usg_funds_low=True, venue__confirmed=False))
    assert r["verdict"] == "risk"  # the unconfirmed venue is fixable, so it still counts
    assert r["counts"]["warning"] == 1 and r["counts"]["risk"] == 1


def test_counts_have_all_four_categories():
    c = engine.check(DEMOS["blockers"])["counts"]
    assert set(c) == {"ready", "warning", "risk", "reject"}
    assert sum(c.values()) == len(engine.check(DEMOS["blockers"])["approvals"])


def test_all_warnings_listed_even_next_to_fixable_problems():
    r = engine.check(DEMOS["at_risk"])  # USG card has 'due soon' (fixable) + 3 warnings
    msgs = [w["message"] for w in r["warnings"]]
    assert len(msgs) == 3 and all(w["level"] == "warning" for w in r["warnings"])
    assert any("close to the $8,000 cap" in m for m in msgs)
    assert all(w["approval"] == "USG funding application" for w in r["warnings"])


# ---------------------------------------------------------------- breaks
def test_event_in_a_break_is_flagged_on_the_first_step():
    r = engine.check(base(date="2026-12-28"))  # Winter break
    first = r["approvals"][0]
    f = next(f for f in first["flags"] if f["rule_id"] == "event_in_breaks")
    assert f["level"] == "risk" and "Winter break" in f["fix"] and f["rule_id"].endswith("_breaks")
    assert r["verdict"] != "ready"
    assert sum(f["rule_id"] == "event_in_breaks" for a in r["approvals"] for f in a["flags"]) == 1


def test_earliest_event_date_skips_breaks():
    venue = engine.APPROVALS["venue_request"]  # 35 days
    d = engine.earliest_event_date(venue, dt.date(2026, 11, 14))  # +35 = Dec 19, inside winter break
    assert d == dt.date(2027, 1, 11) and not engine.break_on(d)


def test_suggested_dates_are_never_in_a_break():
    r = engine.check(DEMOS["blockers"])
    for a in r["approvals"]:
        for f in a["flags"]:
            if f["rule_id"].endswith("_deadline") and "or later" in f["fix"]:
                assert "Dec 2" not in f["fix"] and "Jan 1, 2027" not in f["fix"], f["fix"]


# ---------------------------------------------------------------- verdict + normalize
def test_reject_beats_needs_info():
    ev = base(date=None, budget_lines=[{"item": "Hall", "category": "venue", "amount": 4500, "quote_attached": True}])
    r = engine.check(ev)
    assert r["verdict"] == "reject" and r["verdict_label"] == "Will be rejected"


def test_no_date_and_nothing_rejected_is_needs_info():
    r = engine.check(base(date=None))
    assert r["verdict_label"] == "Needs info" and r["verdict"] == "risk"


def test_selling_food_means_serving_food():
    ev = engine.normalize({"food": {"sold": True}})
    assert ev["food"]["served"] is True
    assert engine.check(base(food={"sold": True, "served": False}))["features"]["food"]


def test_quoted_rule_text_is_only_usc_words():
    for a in engine.RULES["approvals"]:
        assert "Greenlight" not in a["text"], a["id"]
    f = flags(base(date="2026-12-01"))["venue_request_deadline"]
    assert "Greenlight" not in f["rule_text"] and "five weeks" in f["fix"]


# ---------------------------------------------------------------- vendor list
def test_vendor_names_match_loosely():
    assert engine.find_vendor("Lunch from CAVA")["name"] == "CAVA"
    assert engine.find_vendor("dulce")["name"] == "Cafe Dulce"
    assert engine.find_vendor("Rock and Reilly's")["name"] == "Rock & Reilly's"
    assert engine.find_vendor("Panda Express catering")["name"] == "Panda Express (Catering2Go)"
    assert engine.find_vendor("a local Chinese restaurant") is None


def test_vendor_found_in_budget_line_when_not_named():
    ev = base(food__vendor="", budget_lines=FOOD(400, item="Pizza from Superette"))
    assert "usg_food_vendor_list" in flags(ev)
    assert engine.check(ev)["event"]["food"]["vendor_match"] == "Superette"


def test_unknown_vendor_is_not_on_the_list():
    f = flags(base(food__vendor="Mom's Kitchen", budget_lines=FOOD(300)))
    assert f["usg_food_vendor_list"]["level"] == "reject" and "our vendor list" in f["usg_food_vendor_list"]["message"]


def test_no_vendor_named_is_a_risk():
    f = flags(base(food__vendor="", budget_lines=FOOD(300, item="Snacks")))
    assert f["usg_food_vendor_list"]["level"] == "risk"


def test_vendor_rules_skip_events_without_usg_food_lines():
    # food served but USG isn't paying for it: the USG vendor rules don't apply
    f = flags(base(food__vendor="Superette", budget_lines=[{"item": "Room", "category": "venue", "amount": 100, "quote_attached": True}]))
    assert not {"usg_food_vendor_list", "usg_food_cap", "usg_vendor_docs"} & set(f)


def test_list_overrides_the_checkbox():
    ev = engine.normalize(base(food__vendor="The Baked Bear", food__vendor_approved=True))
    assert ev["food"]["vendor_approved"] is False   # the list says it can't cater


def test_fix_suggests_vendors_that_pass():
    sug = engine.suggest_vendors()
    for name in sug.split(", "):
        v = engine.find_vendor(name)
        assert v["usg_vendor"] and v["catering_approved"] and v["per_person"] <= 35
