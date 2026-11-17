import json

import pytest

from reeldecode import cli, formats, frames, jev, page
from reeldecode.config import Config
from reeldecode.store import Store


def fake_grab(mp4, t, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"\xff\xd8 still at %.2f" % t)
    return out


def transport_for(shots, hook="headline_text", fail_at=None):
    """Answers the still whose bytes name time t with shots[index of t]."""
    calls = []

    def call(payload, key):
        assert payload["assets"], "a frame request must carry its image"
        ref = payload["state"]["frame"]
        assert ref in payload["assets"] and payload["assets"][ref]["format"] == "jpg"
        i = len(calls)
        calls.append(payload)
        if fail_at is not None and i == fail_at:
            raise jev.JevError("HTTP 500")
        ans = {"shot": {"choice": shots[i % len(shots)], "confidence": 0.8}, "caption": {"noul": 0.9 if i < 3 else 0.1}}
        if "hook_visual" in payload["questions"]:
            ans["hook_visual"] = {"choice": hook}
        return {"answers": ans, "usage": {"input_tokens": 1100}}
    call.calls = calls
    return call


def test_frame_times_cover_opening_and_body_without_duplicates():
    assert frames.frame_times(40) == [0.3, 1.5, 3.0, 10.0, 20.0, 30.0]
    short = frames.frame_times(2.0)
    assert short == sorted(short) and all(t <= 1.9 for t in short)
    assert all(b - a >= 0.25 for a, b in zip(short, short[1:]))


def test_summarize_names_majority_format_and_sequence():
    ans = [{"shot": s, "caption": c} for s, c in
           [("talking_head", 0.9), ("talking_head", 0.8), ("screen_recording", 0.2),
            ("screen_recording", 0.1), ("talking_head", 0.7), ("talking_head", 0.1)]]
    ans[0]["hook_visual"] = "face_closeup"
    s = frames.summarize([0.3, 1.5, 3, 10, 20, 30], ans)
    assert s["visual_format"] == "talking_head" and s["open_shot"] == "talking_head"
    assert s["shot_seq"] == "talking_head > screen_recording > talking_head" and s["shot_changes"] == 2
    assert s["hook_visual"] == "face_closeup" and s["caption_share"] == 0.5
    mixed = frames.summarize([1, 2, 3], [{"shot": x, "caption": 0} for x in ("b_roll", "text_card", "interview")])
    assert mixed["visual_format"] == "mixed"


def test_read_frames_asks_hook_question_only_on_first_still(tmp_path):
    call = transport_for(["person_over_screen"])
    rec = frames.read_frames(tmp_path / "v.mp4", "k", tmp_path, call, fake_grab, duration=40)
    hooks = [("hook_visual" in p["questions"]) for p in call.calls]
    assert hooks.count(True) == 1 and rec["hook_visual"] == "headline_text"
    assert rec["tokens"] == 6 * 1100 and rec["visual_format"] == "person_over_screen"


def _store(tmp_path):
    cfg = Config(root=tmp_path, cache=tmp_path / "cache", data=tmp_path / "data")
    st = Store(cfg)
    st.data.mkdir(parents=True)
    posts = [{"shortcode": f"v{i}", "url": f"https://example.com/reel/v{i}/", "views": 100 + i,
              "posted_at": "2026-01-01T00:00:00+00:00"} for i in range(2)]
    (st.data / "reference_demo.json").write_text(json.dumps({"handle": "demo", "posts": posts}))
    return st


def test_cmd_frames_stores_labels_and_logs_cost(tmp_path):
    st = _store(tmp_path)
    fetch = lambda s, p: tmp_path / f"{p['shortcode']}.mp4"
    grab = fake_grab
    orig = frames.duration_of
    frames.duration_of = lambda mp4: 30.0
    try:
        assert frames.cmd_frames(st, 0, transport=transport_for(["talking_head"]), grab=grab, fetch=fetch) == 0
        posts = json.loads((st.data / "reference_demo.json").read_text())["posts"]
        assert all(p["frames"]["visual_format"] == "talking_head" for p in posts)
        run = json.loads((st.data / "decode_runs.jsonl").read_text().splitlines()[-1])
        assert run["stage"] == "frames" and run["videos"] == 2 and run["input_tokens"] == 2 * 6 * 1100
        # second run: cached, no new calls, no new spend
        again = transport_for(["b_roll"])
        frames.cmd_frames(st, 0, transport=again, grab=grab, fetch=fetch)
        assert again.calls == []
    finally:
        frames.duration_of = orig


def test_one_failed_still_stores_nothing_for_that_video(tmp_path):
    st = _store(tmp_path)
    orig = frames.duration_of
    frames.duration_of = lambda mp4: 30.0
    try:
        post = {"shortcode": "v0", "url": "u"}
        used = frames.frames_one(st, post, "k", transport_for(["b_roll"], fail_at=2), fake_grab,
                                 fetch=lambda s, p: tmp_path / "v0.mp4")
        assert used == 0 and "frames" not in post and "HTTP 500" in post["frames_error"]
        assert not (st.frames / "v0.json").exists()
    finally:
        frames.duration_of = orig


def test_images_header_only_when_assets(monkeypatch):
    sent = {}

    class R:
        status_code = 200

        def json(self):
            return {}

    def post(url, headers, json, timeout):
        sent.update(headers)
        return R()
    import requests
    monkeypatch.setattr(requests, "post", post)
    jev.http_call({"assets": {"x": {}}}, "k")
    assert sent.get("TypeSafe-Danger-Zone-Images") == "true"
    sent.clear()
    jev.http_call({"questions": {}}, "k")
    assert "TypeSafe-Danger-Zone-Images" not in sent


def test_opening_sequence():
    assert formats.opening("HHSfSMPY") == "hook > setup > method"
    assert formats.opening("fH") == "hook"
    assert formats.opening("") is None


def _reel(a, xm, fmt, hook, vis=None, tier="middle"):
    return {"a": a, "sc": f"{a}{xm}{fmt}", "url": None, "xm": xm, "tier": tier,
            "labels": {"format": fmt, "hook_formula": hook}, "dv": {"role_seq": "HPM"},
            "frames": {"visual_format": vis, "open_shot": vis, "hook_visual": "headline_text"} if vis else None}


def test_formats_rank_per_creator_and_count_creators_equally():
    reels = []
    for a in ("big", "small"):
        reels += [_reel(a, x, "tool_demo", "question", "screen_recording", "winner") for x in (2.0, 3.0, 2.5)]
        reels += [_reel(a, x, "personal_story", "statement", "talking_head", "loser") for x in (0.5, 0.6, 0.4)]
    reels.append(_reel("big", None, "tool_demo", "question"))          # unjudged: ignored
    data = {"accounts": [{"handle": "big"}, {"handle": "small"}, {"handle": "me", "ours": True}], "reels": reels}
    rep = formats.build(data)
    big = rep["per_account"]["big"]["script format"]
    assert [r["value"] for r in big] == ["tool_demo", "personal_story"]
    assert big[0]["median_x"] == 2.5 and big[0]["n"] == 3 and big[0]["winners"] == 3
    cc = rep["across_creators"]["visual format"]
    assert cc[0]["value"] == "screen_recording" and cc[0]["beats_typical"] == 2 and cc[0]["creators"] == 2
    assert rep["across_creators"]["opening sequence"][0]["value"] == "hook > proof > method"
    md = formats.markdown(rep)
    assert "1.00x is that creator's typical video" in md and "| tool_demo | 2.50x | 3 | 3 |" in md


def test_formats_respects_min_n_and_explains_missing_frames():
    reels = [_reel("a", 1.0 + i / 10, "tool_demo", "question") for i in range(2)]
    rep = formats.build({"accounts": [{"handle": "a"}], "reels": reels})
    assert rep["per_account"] == {}
    md = formats.markdown(rep)
    assert "No video has frame labels yet" in md and "No creator has enough" in md


def test_formats_demo_runs_offline(tmp_path):
    assert cli.main(["formats", "--demo", "--out", str(tmp_path)]) == 0
    rep = json.loads((tmp_path / "formats.json").read_text())
    assert rep["per_account"] and "script format" in next(iter(rep["per_account"].values()))
    assert (tmp_path / "FORMATS.md").read_text().startswith("# Formats")


def test_page_carries_frame_summary(tmp_path):
    st = Store(Config(), page.demo_dir())
    data = page.build(st, 0, 7, {"demo_creator"})
    assert all("frames" in r for r in data["reels"])


@pytest.mark.parametrize("bad", [{}, {"answers": {"shot": {"choice": "b_roll"}}}])
def test_frame_answers_fail_closed(bad):
    with pytest.raises(jev.JevError):
        frames.frame_answers(bad, first=False)
