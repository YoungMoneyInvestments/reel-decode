import datetime as dt

from reeldecode.learn import loop, metrics


def _exp(eid, views, **snap):
    return {"id": eid, "account": "a", "url": "https://www.instagram.com/reel/x/", "funnel": {"stage": "tofu"},
            "variable": "hook", "format": "f", "script": {"hook": "h " + eid},
            "metrics": [{"hours_since_post": 24, "views": 1}, {"hours_since_post": 72, "views": views, **snap}]}


def test_rates_per_thousand_views():
    r = loop.rates({"views": 2000, "shares": 10, "follows": 4})
    assert r["shares_per_1k"] == 5.0 and r["follows_per_1k"] == 2.0 and r["saves_per_1k"] == 0.0
    assert loop.rates({})["shares_per_1k"] is None


def test_typical_needs_three_videos_and_uses_latest_snapshot():
    rows = loop.post_rows([_exp("E1", 100), _exp("E2", 300)])
    assert [r["label"] for r in rows] == ["no baseline yet"] * 2 and rows[1]["views"] == 300
    rows = {r["id"]: r for r in loop.post_rows([_exp("E1", 100), _exp("E2", 300), _exp("E3", 700)])}
    assert rows["E3"]["label"] == "well above typical" and rows["E1"]["label"] == "well below typical"
    assert rows["E2"]["label"] == "typical"


def test_winner_follows_the_measure_order():
    a = {"variant": "A", "hold_3s": 60, "avg_watch_pct": 40, "sends_per_1k": 9, "views": 10}
    b = {"variant": "B", "hold_3s": 55, "avg_watch_pct": 50, "sends_per_1k": 2, "views": 20}
    assert loop.pick_winner([a, b])[0]["variant"] == "B"       # hold not 20% clear, watch percent decides
    a["hold_3s"] = 70
    assert loop.pick_winner([a, b]) == (a, "hold through 3 s")  # 70 >= 1.2 * 55
    c = {"variant": "C", "views": 5}
    assert loop.pick_winner([a, b, c])[0]["variant"] == "B"     # a measure must exist on every variant: views
    assert loop.pick_winner([{"variant": "A"}, {"variant": "B"}])[0] is None


def test_learn_lists_trial_variants_and_unmeasured_posts():
    d = _exp("E9", 0)
    d["trial"] = {"variants": {"A": {"hook": "ha"}, "B": {"hook": "hb"}}}
    d["metrics"] = [{"variant": "A", "hours_since_post": 72, "views": 1000, "shares": 5, "saves": 5},
                    {"variant": "B", "hours_since_post": 72, "views": 1000, "shares": 1, "saves": 1}]
    md = loop.learn_markdown([d, {"id": "E8", "account": "a", "url": "https://youtube.com/shorts/abc"}])
    assert "winner **A** on sends plus saves per 1,000 views" in md and "- E8 (a)" in md


def test_no_trial_call_before_72_hours_and_top_level_variant_hooks():
    d = _exp("E9", 0)
    d["variants"] = [{"id": "a", "hook": "ha"}, {"id": "b", "hook": "hb"}]
    d["metrics"] = [{"variant": "A", "hours_since_post": 50, "views": 1000, "shares": 5, "saves": 5},
                    {"variant": "B", "hours_since_post": 49.5, "views": 1000, "shares": 1, "saves": 1}]
    md = loop.learn_markdown([d])
    assert "E9: no call before 72 h (youngest version read at 49.5 h); leader so far **A**" in md
    assert "| ha |" in md and "| hb |" in md


def test_plain_hook_list_maps_to_a_b_c_and_unread_versions_block_the_call():
    d = _exp("E9", 0)
    d["hook_variants"] = ["first hook", "second hook", "third hook"]
    d["url"] = ("c https://www.instagram.com/reel/x1/ | b https://www.instagram.com/reel/x2/ | "
                "a https://www.instagram.com/reel/x3/")
    d["metrics"] = [{"variant": "C", "hours_since_post": 80, "views": 100},
                    {"variant": "A", "hours_since_post": 80, "views": 50}]
    rows = {r["variant"]: r for r in loop.post_rows([d])}
    assert rows["C"]["hook"] == "third hook" and rows["A"]["hook"] == "first hook"
    assert "E9: 2 of 3 posted versions have numbers; no call yet." in loop.learn_markdown([d])


def _shortcode_for(when: dt.datetime) -> str:
    """Encode a synthetic Instagram-style shortcode whose media id carries `when`."""
    n = (int(when.timestamp() * 1000) - metrics.IG_EPOCH_MS) << 23
    out = ""
    while n:
        n, r = divmod(n, 64)
        out = metrics.IG_ALPHABET[r] + out
    return out


def test_instagram_post_time_comes_from_the_shortcode():
    when = dt.datetime(2026, 3, 14, 15, 9, 26, 535000, tzinfo=dt.timezone.utc)
    code = _shortcode_for(when)
    assert metrics.ig_posted_at(f"https://www.instagram.com/reel/{code}/") == when
    assert metrics.ig_posted_at("https://youtube.com/shorts/abcdefghijk") is None
    early, late = _shortcode_for(when), _shortcode_for(when + dt.timedelta(minutes=9))
    d = {"posted_at": "~22:31 2026-03-14 (C, A)",
         "url": f"c https://www.instagram.com/reel/{early}/ | a https://www.instagram.com/reel/{late}/"}
    posts = metrics.posts_of(d)
    assert [p["variant"] for p in posts] == ["C", "A"]
    assert posts[0]["posted_at"] < posts[1]["posted_at"]


def test_due_mark_and_hand_written_times():
    assert metrics.due_mark(10, [], None, "u") is None
    assert metrics.due_mark(80, [], None, "u") == 72
    assert metrics.due_mark(80, [{"mark": 72, "variant": None, "url": "u"}], None, "u") is None
    assert metrics.parse_when("posted 2026-03-14 around 9:05").hour == 9


def test_insights_panel_parse_skips_blank_labels():
    body = "Views\n12,345\nViewers\n--\nLikes\n410\nNon-followers\n63.5%\nShares\n22"
    m = metrics.parse_ig_panel(body)
    assert m == {"views": 12345, "likes": 410, "non_follower_pct": 63.5, "shares": 22}


def test_curve_shapes():
    cliff = [1.0] + [0.4 - i * 0.001 for i in range(99)]
    assert metrics.curve_shape(cliff, 30).startswith("hook failed")
    good = [1.0 - 0.2 * min(i, 10) / 10 - 0.002 * i for i in range(100)]
    assert metrics.curve_shape(good, 30).startswith("good")
    assert metrics.curve_shape([1.0] * 5, 30) is None
    assert metrics.iso_seconds("PT1M5S") == 65
