import json
import subprocess

import pytest

from reeldecode import cli, formats, ideas, page, production
from reeldecode.analysis import production_lift, tercile_flags
from reeldecode.config import Config
from reeldecode.store import Store


def breakdown(conf=0.62, vlm=False, mix=None, music=True, beat=True, voice_lean="human_recording", voice_p=0.8):
    """A synthetic rea-video breakdown.json with the keys reel-decode reads (schema rea_video.breakdown.v1)."""
    mix = mix or [{"label": "live_action", "ratio": 0.7}, {"label": "code_render", "ratio": 0.3}]
    return {
        "schema": "rea_video.breakdown.v1", "tool": {"name": "rea-video", "version": "0.1.0"},
        "source": {"duration": 20.0, "fps": 30.0},
        "summary": {"duration": 20.0, "shots": 10, "avg_shot_s": 2.0, "confidence": conf,
                    "production_mix": mix, "transitions": {"start": 1, "cut": 6, "jump": 2, "dissolve": 1},
                    "overlay_kinds": ["subtitle", "label"], "production": "filmed 7 shots -> 1 setup"},
        "analysis": {"vlm": {"used": vlm}},
        "shots": [{}] * 10,
        "packaging": {"counts": {"text": {"subtitle": 12, "label": 3, "huazi": 1}, "stickers": 2},
                      "text_cues": [{"t0": 0.2, "text": "a"}, {"t0": 5.0, "text": "b"},
                                    {"t0": 0.0, "text": "sign", "part_of_picture": True}]},
        "audio": {"voice": {"present": True, "ratio": 0.8},
                  "music": {"present": music, "ratio": 0.5, "tempo_bpm": 120.0},
                  "beat_synced_edit": beat},
        "audio_plan": {"sfx_merged": [{"t": 1, "confidence": "medium", "on": {"type": "cut"}},
                                      {"t": 2, "confidence": "medium", "on": {"type": "label_in"}},
                                      {"t": 3, "confidence": "medium", "on": None},
                                      {"t": 4, "confidence": "low"}]},
        "sound_sources": {"voice": {"leaning": voice_lean, "probs": {voice_lean: voice_p}},
                          "music": {"leaning": "existing_library", "probs": {"existing_library": 0.7}}},
        "aspects": {"framing": {"shot_sizes": {"中景": 0.3, "近景": 0.7}},
                    "camera": {"support_shares": {"fixed": 0.8, "moving": 0.2}},
                    "lighting": {"result": {"setup": "soft_front"}}},
    }


def test_summarize_reads_measured_facts():
    p = production.summarize(breakdown())
    assert p["shots"] == 10 and p["shots_per_10s"] == 5.0 and p["avg_shot_s"] == 2.0
    assert p["jump_cuts"] == 2 and p["effect_transitions"] == 1
    assert p["captions"] == 12 and p["callouts"] == 4 and p["stickers"] == 2
    assert p["text_cues"] == 2 and p["text_first_1s"]            # text that is part of the picture does not count
    assert p["sfx"] == 3 and p["sfx_on_cue"] == 2                 # low-confidence effects are left out
    assert p["voice_source"] == "human_recording" and p["music_source"] == "existing_library"
    assert p["bpm"] == 120.0 and p["beat_synced"]
    assert p["shot_size_main"] == "medium close-up" and p["camera_moving_share"] == 0.2
    assert p["made_main"] == "live_action" and p["rea_video"] == "0.1.0"


def test_method_call_counts_only_when_reliable():
    assert not production.summarize(breakdown(conf=0.6))["made_reliable"]
    assert production.summarize(breakdown(conf=0.85))["made_reliable"]
    assert production.summarize(breakdown(conf=0.4, vlm=True))["made_reliable"]
    p = production.summarize(breakdown(conf=0.4, vlm=True))
    assert p["readers"] == ["tools", "model"]


def test_unsure_sound_source_is_unknown_and_no_music_has_no_bpm():
    p = production.summarize(breakdown(music=False, voice_lean="tts", voice_p=0.5))
    assert p["voice_source"] == "unknown"
    assert p["music"] is False and p["bpm"] is None and p["music_source"] is None


def test_decompose_command_is_english_and_vlm_explicit():
    cmd = production.decompose_cmd("rea-video", "a.mp4", "out", vlm=False)
    assert cmd[:2] == ["rea-video", "decompose"] and "--lang" in cmd and cmd[cmd.index("--lang") + 1] == "en"
    assert "--no-vlm" in cmd and "--vlm" not in cmd
    assert "--vlm" in production.decompose_cmd("rea-video", "a.mp4", "out", vlm=True)


def test_run_decompose_fails_loud(tmp_path):
    def bad(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 2, "", "Traceback: boom")
    with pytest.raises(production.ProductionError, match="exit 2"):
        production.run_decompose(tmp_path / "a.mp4", tmp_path / "o", runner=bad, exe="rea-video")

    def good(cmd, **kw):
        out = cmd[cmd.index("-o") + 1]
        (tmp_path / "o2" / "breakdown.json").write_text(json.dumps(breakdown()))
        assert out.endswith("o2")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    assert production.run_decompose(tmp_path / "a.mp4", tmp_path / "o2", runner=good, exe="rea-video")["summary"]


def test_missing_tool_names_the_install(monkeypatch):
    monkeypatch.delenv("REEL_DECODE_REA_VIDEO", raising=False)
    monkeypatch.setattr(production.shutil, "which", lambda _: None)
    with pytest.raises(production.ProductionError, match=r"reel-decode\[production\]"):
        production.rea_video_bin()


def test_production_one_caches(tmp_path):
    st = Store(Config(root=tmp_path), tmp_path / "data")
    calls = []

    def dec(mp4, out, vlm):
        calls.append(mp4)
        return breakdown()
    post = {"shortcode": "abc", "url": "https://example.com/v/abc"}
    rec = production.production_one(st, post, decompose=dec, fetch=lambda s, p: tmp_path / "abc.mp4")
    again = production.production_one(st, post, decompose=dec, fetch=lambda s, p: tmp_path / "abc.mp4")
    assert rec == again and len(calls) == 1 and rec["package"].endswith("abc/VIDEO.md")


def _rows(n=30):
    rows = []
    for i in range(n):
        win = i >= n * 2 // 3
        prod = production.summarize(breakdown(beat=win, conf=0.9 if i % 2 else 0.5))
        rows.append({"shortcode": f"s{i}", "views": 100 + i * 50, "posted_at": "2025-01-01T00:00:00+00:00",
                     "prod": prod})
    tercile_flags(rows, 7)
    return rows


def test_production_lift_finds_planted_trait_and_gates_method_traits():
    table = production_lift(_rows())
    beat = next(x for x in table if x["value"] == "edit cut to the beat")
    assert beat["gap"] == 1.0 and beat["dim"] == "production"
    made = [x for x in table if x["dim"] == "made"]
    assert made and all(x["win_of"] < 10 for x in made)       # only the reliably-judged half is counted


def test_demo_page_formats_and_ideas_carry_production(tmp_path):
    st = Store(Config(root=tmp_path), page.demo_dir())
    data = page.build(st, 0, 7, {"demo_creator"})
    assert all(r["prod"] for r in data["reels"])
    assert any(a["prod_lift"] for a in data["accounts"])
    rep = formats.build(data)
    assert rep["videos_with_production"] == len(data["reels"])
    assert any("edit pace" in g for g in rep["per_account"].values())
    cards = ideas.idea_cards(data, min_x=2.0)
    md = ideas.cards_markdown(cards, 2.0)
    assert cards and "how it was made:" in md and "shot-by-shot breakdown" in md
    html = page.render(data, tmp_path).read_text()
    assert "How winners are made vs losers" in html


def test_cli_production_without_tool_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("REEL_DECODE_REA_VIDEO", raising=False)
    monkeypatch.setattr(production.shutil, "which", lambda _: None)
    monkeypatch.chdir(tmp_path)
    assert cli.main(["production", "--one", str(tmp_path / "x.mp4"), "--out", str(tmp_path / "o")]) == 1
    assert "not installed" in capsys.readouterr().err
