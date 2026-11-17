import shutil
import subprocess

import pytest

from reeldecode import edit, jev, taste

SHOWINFO = "n:0 pts_time:0.4 x\nn:1 pts_time:0.5 y\nn:2 pts_time:2.1 z\nn:3 pts_time:4.0 w"


def test_parse_cuts_merges_flash_frames():
    assert taste.parse_cuts(SHOWINFO) == [0.4, 2.1, 4.0]


def test_pacing_and_shots():
    p = taste.pacing([2.0, 4.0], 6.0)
    assert p["shots"] == 3 and p["avg_shot"] == 2.0 and p["cuts_first_10s"] == 2
    assert p["opening_hold"] == 2.0 and p["longest"][1] == 2.0


def test_tastebook_cites_videos_and_admits_gaps():
    st = [{"name": "ref1", "url": "u", "pacing": taste.pacing([1.8, 3.6, 5.4], 7.2),
           "speech": taste.cuts_on_speech([1.8, 3.6, 5.4], [{"t": 1.9}, {"t": 5.3}])}]
    md = taste.build_tastebook(st)
    assert "Cut about every 1.8 s" in md and "ref1" in md and "0:01.8" in md
    assert "2 of 3 cuts" in md and "Not measured" in md
    with pytest.raises(ValueError):
        taste.build_tastebook([])


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_detect_cuts_on_a_real_clip(tmp_path):
    f = tmp_path / "c.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=red:s=160x90:d=1:r=10",
                    "-f", "lavfi", "-i", "color=blue:s=160x90:d=1:r=10", "-f", "lavfi", "-i", "color=green:s=160x90:d=1:r=10",
                    "-filter_complex", "[0][1][2]concat=n=3", "-y", str(f)], check=True)
    cuts = taste.detect_cuts(f)
    assert len(cuts) == 2 and abs(cuts[0] - 1.0) < 0.2 and abs(cuts[1] - 2.0) < 0.2
    assert abs(taste.duration_of(f) - 3.0) < 0.2


def _fake(verdicts):
    it = iter(verdicts)

    def call(payload, key):
        v, w, r = next(it)
        return {"answers": {"verdict": {"choice": v}, "where": {"choice": w}, "reason": {"choice": r}}}
    return call


def test_plan_applies_in_order():
    lines = ["Hook line.", "Throat clearing.", "Takeaway buried.", "Ask."]
    plan = edit.make_plan(lines, "k", _fake([("keep", "stay", "does_its_job"), ("delete", "stay", "weak"),
                                              ("move", "after_hook", "buries_the_point"),
                                              ("keep", "stay", "does_its_job")]))
    assert [p["n"] for p in edit.apply_order(plan)] == [1, 3, 4]
    assert "deleted 1" in edit.change_list(plan)


def test_move_that_goes_nowhere_is_a_keep_and_stay_is_forced_for_keep():
    plan = edit.make_plan(["a"], "k", _fake([("move", "stay", "weak")]))
    assert plan[0]["verdict"] == "keep"
    plan = edit.make_plan(["a"], "k", _fake([("keep", "end", "does_its_job")]))
    assert plan[0]["where"] == "stay"


def test_missing_answer_fails_closed():
    with pytest.raises(jev.JevError):
        edit.make_plan(["a"], "k", lambda p, k: {"answers": {"verdict": {"choice": "keep"}}})


def test_repeated_line_keeps_its_first_copy_and_odd_keeps_are_flagged():
    plan = edit.make_plan(["Same idea.", "Um, so.", "Same idea."], "k",
                          _fake([("delete", "stay", "repeats"), ("keep", "stay", "weak"),
                                 ("delete", "stay", "repeats")]))
    assert [p["verdict"] for p in plan] == ["keep", "keep", "delete"]
    assert plan[1]["flag"] and "Check by hand" in edit.change_list(plan)
