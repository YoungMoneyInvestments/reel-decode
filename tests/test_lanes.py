import datetime as dt

from reeldecode import cli
from reeldecode.config import Account, Config, Lane
from reeldecode.gate import brief, lanes

TODAY = dt.date(2026, 11, 17)


def cfg():
    return Config(accounts=[Account(handle="acme", yours=True, lanes=[
        Lane("founder-story", stages=("tofu", "mofu"), format="talking_head", per_week=3),
        Lane("quote-carousel", stages=("mofu",), format="carousel", per_week=2, avoid=("buy now",)),
    ]), Account(handle="nolanes")])


def d(**kw):
    base = {"account": "acme", "lane": "founder-story", "format": "talking_head", "funnel": {"stage": "tofu"},
            "topic": "t", "status": "scripted"}
    base.update(kw)
    return base


def test_no_lanes_no_rules():
    assert lanes.lane_checks(d(account="nolanes", lane=""), cfg()) == []


def test_lane_required_known_stage_format_and_avoid():
    c = cfg()
    assert lanes.lane_checks(d(), c) == []
    assert "lane missing" in lanes.lane_checks(d(lane=""), c)[0]
    assert "not defined" in lanes.lane_checks(d(lane="nope"), c)[0]
    assert "stage bofu" in lanes.lane_checks(d(funnel={"stage": "bofu"}), c)[0]
    assert "format carousel" in lanes.lane_checks(d(format="carousel"), c)[0]
    bad = d(lane="quote-carousel", format="carousel", funnel={"stage": "mofu"}, caption="Buy now!")
    assert "'buy now'" in lanes.lane_checks(bad, c)[0]


def test_plan_counts_posted_queued_and_shortfall():
    exps = [d(status="posted", posted_at="2026-11-15T12:00:00+00:00"),
            d(status="posted", posted_at="2026-11-01T12:00:00+00:00"),   # outside the window
            d(status="rendered")]
    rows = {r["lane"]: r for r in lanes.plan(cfg(), exps, TODAY)}
    f = rows["founder-story"]
    assert (f["posted"], f["queued"], f["target"], f["short"], f["days_since"]) == (1, 1, 3.0, 1, 2)
    assert rows["quote-carousel"]["short"] == 2 and rows["quote-carousel"]["days_since"] is None


def test_carousel_skips_the_spoken_script_rubric():
    car = {"id": "E1", "account": "acme", "lane": "quote-carousel", "format": "carousel", "status": "scripted",
           "funnel": {"stage": "mofu", "audience": "a member", "goal": "see real results"},
           "topic": "Three members on their first week.", "viewer_takeaway": "What a first week looks like.",
           "send_to": "a friend who is on the fence", "proof": [{"claim": "quote", "source": "member, discord, ok to use"}],
           "caption": "Three first weeks."}
    sc, fails, bfails = brief.all_failures(car, cfg())
    assert sc is None and fails == [] and bfails == []
    car["proof"] = []
    assert any("source" in f for f in brief.all_failures(car, cfg())[2])


def test_lanes_command_needs_lanes(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["lanes"]) == 2
