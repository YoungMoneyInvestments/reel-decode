"""Decode stages without the network: analysis maths, sentence building, the anatomy pass with a fake Jev."""
import json
from datetime import datetime, timedelta, timezone

from reeldecode import analysis, decode, store
from reeldecode.config import Config
from reeldecode.questions import REEL_NOUL_DIMS
from reeldecode.store import Store

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def rows(n=12, year="2026"):
    out = []
    for i in range(n):
        out.append({"shortcode": f"s{i}", "views": 100 * (i + 1),
                    "posted_at": f"{year}-0{1 + i % 4}-1{i % 9}T12:00:00+00:00"})
    return out


def test_terciles_inside_one_account():
    rs = rows()
    analysis.tercile_flags(rs, 7, NOW)
    tiers = [r["tier"] for r in rs]
    assert tiers.count("winner") == 4 and tiers.count("loser") == 4
    assert rs[-1]["tier"] == "winner" and rs[0]["tier"] == "loser"


def test_too_young_and_too_few_are_unjudged():
    rs = rows(12)
    rs[0]["posted_at"] = (NOW - timedelta(days=2)).isoformat()
    analysis.tercile_flags(rs, 7, NOW)
    assert rs[0]["tier"] == "unjudged"
    few = rows(5)
    analysis.tercile_flags(few, 7, NOW)
    assert {r["tier"] for r in few} == {"unjudged"}


def test_same_year_baseline():
    old = rows(8, "2024")      # small era
    new = rows(8, "2026")
    for r in new:
        r["views"] *= 100          # a big later era must not make every old video a loser
    rs = old + new
    analysis.tercile_flags(rs, 7, NOW)
    assert {r["tier"] for r in old} >= {"winner", "loser"}


def test_sentences_from_words():
    words = [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4}
             for i, w in enumerate(["Why", "does", "rice", "stick?", "Rinse", "it", "first."])]
    s = decode.sentences_from_words(words)
    assert [x["text"] for x in s] == ["Why does rice stick?", "Rinse it first."]
    assert s[1]["t"] == 2.0


def test_spoken_filters_music_and_loops():
    assert not decode.spoken({"word_count": 5, "sentences": []})
    assert not decode.spoken({"word_count": 40, "no_speech_prob": 0.9, "sentences": []})
    loop = [{"text": "la la la"}] * 6
    assert not decode.spoken({"word_count": 40, "no_speech_prob": 0.1, "sentences": loop})
    real = [{"text": f"sentence {i}"} for i in range(6)]
    assert decode.spoken({"word_count": 40, "no_speech_prob": 0.1, "sentences": real})


def fake_jev(payload, key):
    if "role" in payload["questions"]:
        pos = payload["state"]["position"]
        return {"answers": {"role": {"choice": "hook" if pos == "first sentence" else "method"}},
                "usage": {"input_tokens": 50}}
    ans = {"talking": {"noul": 0.95}, "format": {"choice": "how_to_steps", "confidence": 0.8},
           "hook_formula": {"choice": "question"}, "viewer_payoff": {"choice": "practical_tip"},
           "cta_type": {"choice": "none"}, "register": {"choice": "calm"}}
    ans.update({k: {"noul": 0.7} for k in REEL_NOUL_DIMS})
    return {"answers": ans, "usage": {"input_tokens": 500}}


def test_anatomy_labels_scripts_and_logs_cost(tmp_path):
    cfg = Config(root=tmp_path)
    st = Store(cfg)
    st.trans.mkdir(parents=True)
    sents = [{"t": i * 2.0, "text": f"Sentence number {i} about rice.", "words": 5} for i in range(5)]
    (st.trans / "abc.json").write_text(json.dumps({"shortcode": "abc", "sentences": sents, "word_count": 25,
                                                   "no_speech_prob": 0.05, "audio_end": 10.0}))
    store.save(st.data / "reference_demo.json", {"handle": "demo", "posts": [
        {"shortcode": "abc", "url": "https://example.com/v/abc", "views": 500, "posted_at": "2026-01-01"},
        {"shortcode": "zzz", "url": "https://example.com/v/zzz", "views": 90, "posted_at": "2026-01-02"}]})
    assert decode.cmd_anatomy(st, 0, transport=fake_jev) == 0
    posts = {p["shortcode"]: p for p in store.load(st.data / "reference_demo.json")["posts"]}
    assert posts["abc"]["script_status"] == "decoded"
    assert [s["role"] for s in posts["abc"]["script"]] == ["hook"] + ["method"] * 4
    assert posts["abc"]["d_hook_formula"] == "question" and posts["abc"]["d_format_conf"] == 0.8
    assert posts["zzz"]["script_status"] == "no_transcript"
    run = json.loads((st.data / "decode_runs.jsonl").read_text().splitlines()[-1])
    assert run["input_tokens"] == 500 + 5 * 50 and run["errors"] == 0


def test_anatomy_fails_closed_on_a_bad_answer(tmp_path):
    cfg = Config(root=tmp_path)
    st = Store(cfg)
    st.trans.mkdir(parents=True)
    sents = [{"t": 0.0, "text": "One two three four five six.", "words": 6}] * 3
    (st.trans / "abc.json").write_text(json.dumps({"shortcode": "abc", "sentences": [dict(s, text=f"{s['text']} {i}") for i, s in enumerate(sents)],
                                                   "word_count": 18, "no_speech_prob": 0.05}))
    store.save(st.data / "reference_demo.json", {"handle": "demo", "posts": [
        {"shortcode": "abc", "url": "https://example.com/v/abc", "views": 500, "posted_at": "2026-01-01"}]})

    def broken(payload, key):
        return {"answers": {}, "usage": {}}
    decode.cmd_anatomy(st, 0, transport=broken)
    post = store.load(st.data / "reference_demo.json")["posts"][0]
    assert post["script_status"] == "error" and "script" not in post


def test_csv_import_keeps_decode_work(tmp_path):
    cfg = Config(root=tmp_path)
    csv = tmp_path / "v.csv"
    csv.write_text("url,views,posted_at\nhttps://www.tiktok.com/@someone/video/123,1,500\n"
                   "https://example.com/reel/abc/,900,2026-02-01\n")
    out = store.import_csv(cfg, csv, "@Demo")
    payload = store.load(out)
    assert payload["handle"] == "demo" and len(payload["posts"]) == 2
    payload["posts"][0]["script_status"] = "decoded"
    store.save(out, payload)
    csv.write_text("url,views\nhttps://example.com/reel/abc/,950\n")
    store.import_csv(cfg, csv, "demo")
    post = next(p for p in store.load(out)["posts"] if p["shortcode"] == "abc")
    assert post["views"] == 950
    assert any(p.get("script_status") == "decoded" for p in store.load(out)["posts"])


def test_estimated_views_are_never_selected():
    payload = {"posts": [{"shortcode": "a", "views": 10, "views_source": "estimate"},
                         {"shortcode": "b", "views": 10, "views_source": "csv"}]}
    assert [p["shortcode"] for p in store.selected(payload, 0)] == ["b"]
