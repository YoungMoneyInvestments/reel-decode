import json

from reeldecode import ideas, page
from reeldecode.config import Config
from reeldecode.gate import brief, originality
from reeldecode.learn import loop
from reeldecode.store import Store

REF = ("Is cardio killing your gains? Most people run before they lift and burn the very fuel their "
       "muscles need to grow, so lift first and do cardio after.")


def test_ideas_from_demo_are_outliers_without_scripts_to_reuse():
    data = page.build(Store(Config(), page.demo_dir()), 0, 7, {"demo_creator"})
    cards = ideas.idea_cards(data, min_x=2, limit=5)
    assert cards and all(c["x_median"] >= 2 for c in cards)
    assert all(c["account"] != "demo_creator" for c in cards)          # yours are left out by default
    assert [c["x_median"] for c in cards] == sorted((c["x_median"] for c in cards), reverse=True)
    assert set(cards[0]) >= {"shortcode", "hook_formula", "format", "role_seq", "opener"}
    assert "do not reuse" in ideas.cards_markdown(cards, 2)
    assert "No outliers" in ideas.cards_markdown([], 99)


def test_originality_compare():
    own = "Lift before you run, because your muscles need that fuel to grow."
    assert originality.compare(own, REF)["longest_run"] < originality.MAX_RUN
    copy = "Most people run before they lift and burn the very fuel their muscles need to grow."
    c = originality.compare(copy, REF)
    assert c["longest_run"] >= originality.MAX_RUN and c["shared_share"] > originality.MAX_SHARED_SHARE


def _setup(tmp_path, script):
    cfg = Config(root=tmp_path, cache=tmp_path / "cache")
    st = Store(cfg)
    st.trans.mkdir(parents=True)
    (st.trans / "ref1.json").write_text(json.dumps({"text": REF, "sentences": []}))
    return cfg, st, {"inspired_by": ["ref1"], "spoken_script": script}


def test_gate_blocks_a_copy_and_passes_a_rewrite(tmp_path):
    cfg, st, d = _setup(tmp_path, "Most people run before they lift and burn the very fuel their muscles need to grow.")
    assert any("copied wording" in f or "too close" in f for f in originality.checks(d, cfg, st))
    d["spoken_script"] = "Lift before you run, because your muscles need that fuel to grow."
    assert originality.checks(d, cfg, st) == []


def test_gate_fails_closed_without_a_transcript(tmp_path):
    cfg, st, d = _setup(tmp_path, "Something fresh and original here today.")
    d["inspired_by"] = ["missing"]
    assert "cannot verify" in originality.checks(d, cfg, st)[0]
    assert originality.checks({"spoken_script": "x"}, cfg, st) == []     # no inspired_by, no check


def test_brief_checks_run_the_originality_gate(tmp_path):
    cfg, _st, d = _setup(tmp_path, "Most people run before they lift and burn the very fuel their muscles need to grow.")
    assert any("copied wording" in f or "too close" in f for f in brief.brief_checks(d, cfg))


def test_report_lists_promotion_candidates_without_spending():
    exps = [{"id": "E1", "account": "a", "url": "https://instagram.com/reel/x/", "status": "posted", "funnel": {"stage": "tofu"},
             "script": {"hook": "A hook"}, "metrics": [{"hours": 72, "views": 150_000}]},
            {"id": "E2", "account": "a", "url": "https://instagram.com/reel/y/", "status": "posted", "funnel": {"stage": "tofu"},
             "script": {"hook": "Small"}, "metrics": [{"hours": 72, "views": 900}]}]
    md = loop.learn_markdown(exps)
    assert "Promotion candidates" in md and "E1" in md.split("Promotion candidates")[1].split("##")[0]
    assert "never spends money" in md
    assert "E2" not in md.split("Promotion candidates")[1].split("##")[0]
