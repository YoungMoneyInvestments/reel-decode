"""The script formula: gate checks without the network."""
from reeldecode.config import Account, Config
from reeldecode.gate import formula

GOOD = "Down 10% and cooking bigger batches? Five more meals make it 19. Half the cost, 14. Save this."


def cfg_with(**accounts) -> Config:
    c = Config()
    c.accounts = [Account(handle=h, **kw) for h, kw in accounts.items()]
    return c


CFG = cfg_with(long_form={"duration": (45, 60), "method_cap": True, "spoken_ask": True},
               short_form={"duration": (None, 60), "method_cap": True})


def brief(**kw) -> dict:
    d = {"id": "E900", "status": "scripted", "account": "demo_creator", "spoken_script": GOOD}
    d.update(kw)
    d["script_check"] = kw.get("script_check", {"hash": formula.script_hash(d["spoken_script"]), "fails": []})
    return d


def test_good_script_passes():
    assert formula.formula_checks(brief(), CFG) == []


def test_flat_long_opener_fails_both_checks():
    s = "I have been cooking for twenty years and this is what I learned about pans."
    assert any("12 or fewer" in f for f in formula.formula_checks(brief(spoken_script=s), CFG))
    s2 = "This is what I learned about pans. It matters."
    assert any("number or a question" in f for f in formula.formula_checks(brief(spoken_script=s2), CFG))


def test_spelled_number_counts_as_number_opener():
    s = "Ten minutes under the lid changes everything. Here is why."
    assert not any("number or a question" in f for f in formula.formula_checks(brief(spoken_script=s), CFG))


def test_first_max_words_comes_from_config():
    c = cfg_with()
    c.first_max_words = 4
    assert any("4 or fewer" in f for f in formula.formula_checks(brief(), c))


def test_account_duration_bounds():
    lf = brief(account="long_form")
    assert any("set duration_s" in f for f in formula.formula_checks(lf, CFG))
    assert any("outside" in f for f in formula.formula_checks(brief(account="long_form", duration_s=30), CFG))
    assert formula.formula_checks(brief(account="long_form", duration_s=52), CFG) == []
    assert any("outside" in f for f in formula.formula_checks(brief(account="short_form", duration_s=75), CFG))
    assert formula.formula_checks(brief(account="unlisted", duration_s=300), CFG) == []


def test_jev_read_required_and_must_match_script():
    d = brief()
    d.pop("script_check")
    assert any("no Jev read" in f for f in formula.formula_checks(d, CFG))
    stale = brief(script_check={"hash": "0" * 16, "fails": []})
    assert any("changed since" in f for f in formula.formula_checks(stale, CFG))
    jev_fail = brief(script_check={"hash": formula.script_hash(GOOD), "fails": ["x"]})
    assert formula.formula_checks(jev_fail, CFG) == ["formula (Jev): x"]


def test_exception_and_status_scope():
    bad = "This is a flat opener that runs on and on for far too many words."
    assert formula.formula_checks(brief(spoken_script=bad, formula_exception="teaching-lane test"), CFG) == []
    assert formula.formula_checks(brief(spoken_script=bad, status="rendered"), CFG) == []      # advice only
    assert formula.formula_findings(brief(spoken_script=bad, status="rendered"), CFG)
    assert formula.formula_findings(brief(spoken_script=bad, status="posted"), CFG) == []


def test_spoken_text_sources():
    d = {"full_script": {"cold_open": "SHOT 1-1: We are lost. / Walk slower.",
                         "body_vo": "Halve the salt.", "voice": "VO one narrator"}}
    text, src = formula.spoken_text(d)
    assert src == "full_script" and text == "We are lost. Walk slower. Halve the salt."
    beats = {"script": {"hook": "Why 9%?", "sub_hook": "Here is why.", "rehooks": [], "reward": "R.",
                        "cta": {"text": "Comment PAN."}}}
    assert formula.spoken_text(beats) == ("Why 9%? Here is why. R. Comment PAN.", "script beats")


def test_judge_rules():
    sents = ["Why 19?", "Because heat.", "Here is how.", "Step one.", "Step two."]
    roles = ["hook", "setup", "story", "method", "method"]
    reel = {"hook_formula": "question", "register": "neutral_info", "cta_type": "none"}
    fails = formula.judge(CFG.account("long_form"), sents, roles, reel, CFG)
    assert any("proof" in f for f in fails)
    assert any("neutral" in f for f in fails)
    assert any("method is 40%" in f for f in fails)
    assert any("spoken ask" in f for f in fails)
    ok = formula.judge(CFG.account("anyone"), sents, ["hook", "proof", "story", "payoff", "cta"],
                       {"hook_formula": "specific_number", "register": "playful", "cta_type": "save"}, CFG)
    assert ok == []


def test_jev_read_with_a_fake_transport():
    def fake(payload, key):
        if "role" in payload["questions"]:
            s = payload["state"]["sentence"]
            role = "hook" if payload["state"]["position"] == "first sentence" else ("proof" if "19" in s else "method")
            return {"answers": {"role": {"choice": role}}, "usage": {"input_tokens": 100}}
        if "context_spot" in payload["questions"]:
            return {"answers": HOOK_ANSWERS, "usage": {"input_tokens": 300}}
        return {"answers": {"talking": {"noul": 0.97}, "hook_formula": {"choice": "question"},
                            "format": {"choice": "how_to_steps"}, "viewer_payoff": {"choice": "practical_tip"},
                            "cta_type": {"choice": "save"}, "register": {"choice": "playful"},
                            **{k: {"noul": 0.8} for k in ("open_loop", "viewer_addressed", "concrete_detail",
                                                          "proof_shown", "single_idea", "self_promo")}},
                "usage": {"input_tokens": 900}}
    d = brief()
    chk = formula.jev_read(d, CFG, transport=fake)
    assert chk["hash"] == formula.script_hash(GOOD)
    assert chk["fails"] == [] and chk["reel"]["hook_formula"] == "question"
    assert chk["roles"][1].startswith("proof:")
    assert chk["cost_usd"] > 0
    assert chk["hook"]["score"] == 3


HOOK_ANSWERS = {"context_spot": {"choice": "first_words"}, "lean": {"choice": "proof_or_stat"},
                "leans_in": {"noul": 0.9}, "snapback": {"noul": 0.8}, "keyword_ask": {"choice": "no_keyword"}}


def test_gate_read_blocks_a_hook_without_lean_or_snapback():
    def fake(payload, key):
        if "role" in payload["questions"]:
            return {"answers": {"role": {"choice": "proof"}}, "usage": {"input_tokens": 100}}
        if "context_spot" in payload["questions"]:
            return {"answers": {**HOOK_ANSWERS, "lean": {"choice": "none"}, "snapback": {"noul": 0.1}},
                    "usage": {"input_tokens": 300}}
        return {"answers": {"talking": {"noul": 0.97}, "hook_formula": {"choice": "question"},
                            "format": {"choice": "how_to_steps"}, "viewer_payoff": {"choice": "practical_tip"},
                            "cta_type": {"choice": "save"}, "register": {"choice": "playful"},
                            **{k: {"noul": 0.8} for k in ("open_loop", "viewer_addressed", "concrete_detail",
                                                          "proof_shown", "single_idea", "self_promo")}},
                "usage": {"input_tokens": 900}}
    chk = formula.jev_read(brief(), CFG, transport=fake)
    assert any("no lean" in f for f in chk["fails"]) and any("no snapback" in f for f in chk["fails"])
    assert chk["hook"]["score"] == 1
