import json

import pytest

from reeldecode import cli, config
from reeldecode.collect import instagram

COMMANDS = ["init", "collect", "fetch", "transcribe", "anatomy", "visual", "frames", "formats", "taste", "edit-plan", "ideas", "page", "gate", "lanes", "learn"]


@pytest.mark.parametrize("cmd", COMMANDS)
def test_every_command_has_help(cmd, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main([cmd, "--help"])
    assert e.value.code == 0
    assert "usage: reeldecode " + cmd in capsys.readouterr().out


def test_demo_page_builds_offline(tmp_path):
    assert cli.main(["page", "--demo", "--out", str(tmp_path)]) == 0
    html = (tmp_path / "decode.html").read_text()
    data = json.loads((tmp_path / "decode.json").read_text())
    assert "__DATA__" not in html and "demo_creator" in html
    assert {a["handle"] for a in data["accounts"]} == {"demo_creator", "demo_fitcoach", "demo_studyhacks"}
    creator = next(a for a in data["accounts"] if a["handle"] == "demo_creator")
    assert creator["ours"] and creator["lift"]


def test_init_writes_a_config_that_loads(tmp_path):
    p = tmp_path / "reeldecode.toml"
    assert cli.main(["init", str(p)]) == 0
    cfg = config.load(str(p))
    assert cfg.yours() == {"your_handle"} and not cfg.ig_enabled
    assert cfg.root == tmp_path and cfg.path(cfg.data) == tmp_path / "data"
    assert cli.main(["init", str(p)]) == 1


def test_config_account_rules(tmp_path):
    p = tmp_path / "reeldecode.toml"
    p.write_text('[[accounts]]\nhandle = "@Me"\nyours = true\nduration = [0, 60]\nspoken_ask = true\n'
                 '[formula]\nfirst_max_words = 10\nbrand_terms = ["Me Inc"]\n')
    cfg = config.load(str(p))
    a = cfg.account("me")
    assert a.yours and a.duration == (None, 60) and a.spoken_ask and not a.method_cap
    assert cfg.first_max_words == 10 and cfg.brand_terms == ("Me Inc",)


def test_instagram_collection_is_opt_in(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.main(["collect", "someone"]) == 2
    assert "opt-in" in capsys.readouterr().err
    with pytest.raises(instagram.NotEnabled):
        instagram.grid_scrape(config.Config(), "someone")


def test_instagram_json_parsing_flags_missing_play_counts():
    body = {"data": {"items": [
        {"media": {"pk": "1", "code": "aaa", "like_count": 10, "play_count": 900, "taken_at": 1767225600,
                   "user": {"username": "someone"}, "caption": {"text": "hi"}}},
        {"media": {"pk": "2", "code": "bbb", "like_count": 3, "taken_at": 1767225600,
                   "user": {"username": "someone"}}}]}}
    got = {p["shortcode"]: p for p, _u in instagram.extract_posts(body)}
    assert got["aaa"]["views"] == 900 and got["aaa"]["views_source"] == "grid_play_count"
    assert got["bbb"]["views"] is None and got["bbb"]["views_source"] == "missing"
