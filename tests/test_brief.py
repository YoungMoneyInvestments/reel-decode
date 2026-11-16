import yaml

from reeldecode.config import Config
from reeldecode.gate import brief

TEMPLATE = brief.template()


def full_script() -> dict:
    d = yaml.safe_load(yaml.safe_dump(TEMPLATE))
    d["script"].update({
        "hook": "Burnt garlic has a temperature.",
        "sub_hook": "In 30 seconds I will show you mine.",
        "story": {"character": "a home cook", "conflict": "kept burning the garlic",
                  "turn": "a thermometer showed why"},
        "rehooks": ["But that was not the worst part."],
        "reward": "160 degrees versus 210.",
        "personal_payoff": "You stop wasting garlic tonight.",
        "cta": {"type": "comment_keyword", "keyword": "PAN", "text": "Comment PAN"},
    })
    d["proof"] = [{"claim": "160 vs 210 degrees", "source": "kitchen thermometer test, 12 batches"}]
    d["caption"] = "Burnt garlic has a temperature. Mine was 210."
    return d


def test_complete_script_scores_ten():
    assert brief.score(full_script()) == (10, [])


def test_blank_template_fails_every_unconditional_check():
    # the keyword and dash checks only apply once a comment CTA or caption exists
    sc, fails = brief.score(TEMPLATE)
    assert sc == 2 and len(fails) == 8


def test_payoff_must_address_viewer():
    d = full_script()
    d["script"]["personal_payoff"] = "Our channel finds habits."
    assert "personal payoff missing or not about the viewer" in brief.score(d)[1]


def test_comment_cta_needs_keyword_and_caption_rejects_dashes():
    d = full_script()
    d["script"]["cta"]["keyword"] = ""
    d["caption"] = "Burnt garlic — brutal."
    fails = brief.score(d)[1]
    assert "comment CTA has no keyword" in fails
    assert "caption contains an em or en dash" in fails


def v2() -> dict:
    d = full_script()
    d["script"]["cta"] = {"type": "question", "keyword": "", "text": "What is yours?"}
    d.update({"account": "demo_creator",
              "funnel": {"stage": "tofu", "audience": "home cook who burns garlic every time",
                         "goal": "turn the heat down before the garlic goes in"},
              "topic": "Garlic burns at a temperature most stoves pass in a minute.",
              "viewer_takeaway": "Add garlic after the pan comes off high heat.",
              "send_to": "the roommate who sets off the smoke alarm",
              "hook_variants": ["Burnt garlic has a temperature.", "Your garlic burns at 210 degrees.",
                                "Why does my garlic always go bitter?"]})
    return d


def test_brief_passes():
    assert brief.brief_checks(v2()) == []


def test_blank_template_fails_the_brief():
    fails = brief.brief_checks(TEMPLATE)
    assert any("funnel.stage" in f for f in fails) and any("viewer_takeaway missing" in f for f in fails)
    assert any("hook_variants" in f for f in fails) and any("send_to" in f for f in fails)


def test_selfish_takeaway_and_branded_tofu_hook_fail_with_configured_brand():
    cfg = Config()
    cfg.brand_terms = ("Pan Club",)
    d = v2()
    d["viewer_takeaway"] = "Pan Club fixes it, free trial in bio."
    d["script"]["hook"] = "Pan Club found my worst habit."
    fails = brief.brief_checks(d, cfg)
    assert any("selfish-content test" in f for f in fails)
    assert any("tofu hook names the brand" in f for f in fails)
    d["script"]["hook"] = "Pan Club found my worst habit."
    assert not any("tofu hook" in f for f in brief.brief_checks(d))   # no brand configured: name passes


def test_cta_must_fit_the_stage():
    d = v2()
    d["script"]["cta"]["type"] = "link_in_bio"
    assert any("does not fit tofu" in f for f in brief.brief_checks(d))
    d["funnel"]["stage"] = "bofu"
    assert brief.brief_checks(d) == []


def test_time_sensitive_skips_the_trial_and_topic_is_one_sentence():
    d = v2()
    d["hook_variants"] = []
    assert any("hook_variants" in f for f in brief.brief_checks(d))
    d["time_sensitive"] = True
    assert brief.brief_checks(d) == []
    d["topic"] = "Garlic burns. Also salt matters. And pans."
    assert any("topic must be one idea" in f for f in brief.brief_checks(d))


def test_stage_mix_counts_recent_briefs():
    a, b = v2(), v2()
    b["funnel"]["stage"] = "bofu"
    assert brief.stage_mix([a, b]) == {"tofu": 1, "mofu": 0, "bofu": 1}


def test_gate_clears_a_passing_experiment_and_names_a_missing_one(tmp_path):
    ok = v2()
    ok["spoken_script"] = "Why does garlic burn at 210 degrees? Here is the test."
    ok["script_check"] = {"hash": brief.formula.script_hash(ok["spoken_script"]), "fails": []}
    (tmp_path / "E900-ok.yaml").write_text(yaml.safe_dump(ok))
    flat = v2()
    flat["spoken_script"] = "Burnt garlic has a temperature."
    (tmp_path / "E902-flat.yaml").write_text(yaml.safe_dump(flat))
    bad = v2()
    bad["funnel"]["stage"] = ""
    (tmp_path / "E901-bad.yaml").write_text(yaml.safe_dump(bad))
    assert any("number or a question" in f for f in brief.gate(tmp_path, "E902"))
    assert brief.gate(tmp_path, "E900") == []
    assert any("funnel.stage" in f for f in brief.gate(tmp_path, "E901"))
    assert "no experiment E999" in brief.gate(tmp_path, "E999")[0]


def test_new_writes_a_brief_from_the_template(tmp_path, capsys):
    cfg = Config(root=tmp_path)
    assert brief.cmd_new(cfg, "E001", "Garlic temperature", "hook", "tofu", "@demo_creator", None) == 0
    p = brief.path_for(tmp_path / "experiments", "E001")
    d = brief.load(p)
    assert d["account"] == "demo_creator" and d["funnel"]["stage"] == "tofu"
    assert brief.cmd_new(cfg, "E001", "again", "hook", "tofu", "x", None) == 1
    assert brief.cmd_check(cfg, "E001") == 1


def test_shipped_example_brief_passes_everything_but_the_jev_read():
    from pathlib import Path
    d = brief.load(Path(__file__).resolve().parent.parent / "examples" / "brief-example.yaml")
    assert brief.score(d) == (10, [])
    assert brief.brief_checks(d) == []
    fails = brief.formula.formula_checks(d)
    assert len(fails) == 1 and "no Jev read" in fails[0]
