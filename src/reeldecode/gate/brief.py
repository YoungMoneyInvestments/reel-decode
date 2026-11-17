"""Briefs: one YAML file per video, and the checks a brief must pass before production.

``gate(eid)`` = rubric (ten pass/fail script checks) + brief checks (funnel job, one topic,
viewer-first takeaway, an ask that fits the stage, three hooks to test) + the formula.
See docs/test-and-learn.md for the whole loop.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from importlib import resources
from pathlib import Path

import yaml

from ..config import Config
from . import formula, lanes

STATUSES = ["idea", "scripted", "rendered", "scheduled", "posted", "reviewed"]
STAGES = ("tofu", "mofu", "bofu")
# The ask each funnel stage may end on. A stranger (tofu) is never sent to a link or a DM.
STAGE_CTAS = {
    "tofu": {"question", "follow", "send", "save"},
    "mofu": {"question", "follow", "send", "save", "comment_keyword"},
    "bofu": {"comment_keyword", "link_in_bio", "dm"},
}
CTA_TYPES = set().union(*STAGE_CTAS.values())
GENERIC_ASKS = (r"link in bio|free trial|sign up|subscribe|join (us|the|my)|discord|membership|"
                r"use (my|the) code|dm me")
TARGET_MIX = {"tofu": 6, "mofu": 3, "bofu": 1}  # per ten videos; a default, tune it from results
NON_VIDEO = {"carousel", "image", "text_post"}   # no spoken script: the script rubric and formula do not apply
VARIABLES = ["hook", "story", "payoff", "cta", "format", "length", "baseline"]


def template() -> dict:
    return yaml.safe_load((resources.files("reeldecode") / "templates" / "brief.yaml").read_text())


def brand_re(cfg: Config) -> re.Pattern:
    names = "|".join(re.escape(t) for t in cfg.brand_terms if t.strip())
    return re.compile(rf"{names}|{GENERIC_ASKS}" if names else GENERIC_ASKS, re.IGNORECASE)


# ---------------------------------------------------------------- files
def path_for(exp_dir: Path, eid: str) -> Path | None:
    hits = sorted(exp_dir.glob(f"{eid}-*.yaml")) + sorted(exp_dir.glob(f"{eid}.yaml"))
    return hits[0] if hits else None


def load(p: Path) -> dict:
    return yaml.safe_load(p.read_text()) or {}


def save(p: Path, d: dict) -> None:
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=100))


def all_exps(exp_dir: Path) -> list[tuple[Path, dict]]:
    return [(p, load(p)) for p in sorted(exp_dir.glob("E*.yaml"))]


# ---------------------------------------------------------------- checks
def score(d: dict) -> tuple[int, list[str]]:
    """Ten pass/fail script checks. Returns (score, failures)."""
    s = d.get("script") or {}
    fails: list[str] = []

    def check(ok: bool, msg: str) -> None:
        if not ok:
            fails.append(msg)

    hook = (s.get("hook") or "").strip()
    check(bool(hook) and len(hook.split()) <= 12, "hook missing or over 12 words")
    check(bool((s.get("sub_hook") or "").strip()), "no sub-hook promising a payoff")
    check(bool(re.search(r"\b(you|your)\b", s.get("personal_payoff") or "", re.IGNORECASE)),
          "personal payoff missing or not about the viewer")
    story = s.get("story") or {}
    check(all((story.get(k) or "").strip() for k in ("character", "conflict", "turn")),
          "story backbone incomplete (character, conflict, turn)")
    check(len(s.get("rehooks") or []) >= 1, "no re-hook between hook and reward")
    check(bool((s.get("reward") or "").strip()), "no reward (the promised payoff)")
    cta = s.get("cta") or {}
    check(cta.get("type") in CTA_TYPES, "cta type missing")
    check(cta.get("type") != "comment_keyword" or bool(cta.get("keyword")), "comment CTA has no keyword")
    proof = d.get("proof") or []
    check(bool(proof) and all(p.get("source") for p in proof), "claims lack a recorded source")
    check(not re.search(r"[–—]", d.get("caption") or ""), "caption contains an em or en dash")
    return 10 - len(fails), fails


def brief_checks(d: dict, cfg: Config | None = None) -> list[str]:
    """Viewer-first checks: the funnel job, one topic, what a stranger gets, who they would send it
    to, an ask that fits the stage, and three hooks to test. Returns failures (empty = pass)."""
    cfg = cfg or Config()
    brand = brand_re(cfg)
    s = d.get("script") or {}
    video = d.get("format") not in NON_VIDEO
    fails: list[str] = []

    def check(ok: bool, msg: str) -> None:
        if not ok:
            fails.append(msg)

    f = d.get("funnel") or {}
    stage = f.get("stage")
    check(stage in STAGES, "funnel.stage must be tofu, mofu or bofu")
    check(bool((f.get("audience") or "").strip()), "funnel.audience: name the one viewer this is for")
    check(bool((f.get("goal") or "").strip()), "funnel.goal: the one thing the viewer should feel or do")
    topic = (d.get("topic") or "").strip()
    check(bool(topic) and len(topic.split()) <= 20 and len(re.findall(r"[.!?](\s|$)", topic)) <= 1,
          "topic must be one idea in one sentence of 20 words or fewer")
    take = (d.get("viewer_takeaway") or "").strip()
    check(bool(take), "viewer_takeaway missing: what a stranger can use today")
    check(not brand.search(take),
          "viewer_takeaway names you or an ask: it must stand without the brand (selfish-content test)")
    check(bool((d.get("send_to") or "").strip()), "send_to missing: the person a viewer would forward this to")
    if stage == "tofu" and video:
        check(not brand.search(s.get("hook") or ""), "tofu hook names the brand or an ask: strangers stop for themselves")
    cta_type = (s.get("cta") or {}).get("type")
    if stage in STAGES and video:
        check(cta_type in STAGE_CTAS[stage],
              f"cta '{cta_type}' does not fit {stage} (allowed: {', '.join(sorted(STAGE_CTAS[stage]))})")
    variants = [v for v in (d.get("hook_variants") or []) if str(v).strip()]
    if not d.get("time_sensitive") and video:
        check(len(variants) >= 3 and len(set(variants)) == len(variants),
              "need 3 different hook_variants for the trial run (or set time_sensitive: true)")
    if not video:
        proof = d.get("proof") or []
        check(bool(proof) and all(p.get("source") for p in proof),
              "each quote or claim needs a recorded source (who said it, where, and permission)")
        check(not re.search(r"[–—]", d.get("caption") or ""), "caption contains an em or en dash")
    fails += lanes.lane_checks(d, cfg)
    return fails


def all_failures(d: dict, cfg: Config | None = None) -> tuple[int | None, list[str], list[str]]:
    """(rubric score, rubric failures, brief failures). Non-video posts have no spoken script, so the
    script rubric and the formula are skipped for them."""
    if d.get("format") in NON_VIDEO:
        return None, [], brief_checks(d, cfg)
    sc, fails = score(d)
    return sc, fails, brief_checks(d, cfg) + formula.formula_checks(d, cfg)


def gate(exp_dir: Path, eid: str, cfg: Config | None = None) -> list[str]:
    """Everything that stops experiment ``eid`` from production (empty = clear)."""
    p = path_for(exp_dir, eid)
    if p is None:
        return [f"no experiment {eid} in {exp_dir}"]
    d = load(p)
    _sc, fails, bfails = all_failures(d, cfg)
    return fails + bfails


def stage_mix(exps: list[dict], last: int = 10) -> dict:
    mix = {st: 0 for st in STAGES}
    for d in exps[-last:]:
        st = (d.get("funnel") or {}).get("stage")
        if st in mix:
            mix[st] += 1
    return mix


# ---------------------------------------------------------------- commands
def cmd_new(cfg: Config, eid: str, title: str, variable: str, stage: str, account: str, control: str | None,
            lane: str = "", fmt: str = "") -> int:
    exp_dir = cfg.path(cfg.experiments)
    exp_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    p = exp_dir / f"{eid}-{slug}.yaml"
    if p.exists() or path_for(exp_dir, eid):
        print(f"{eid} already exists", file=sys.stderr)
        return 1
    tpl = template()
    tpl.update({"id": eid, "title": title, "variable": variable, "control": control,
                "created": dt.date.today().isoformat(), "account": account.lstrip("@")})
    tpl["funnel"]["stage"] = stage
    if lane:
        tpl["lane"] = lane
    if fmt:
        tpl["format"] = fmt
    save(p, tpl)
    print(p)
    mix = stage_mix([d for _p, d in all_exps(exp_dir)])
    print("last ten briefs: " + ", ".join(f"{k} {v}" for k, v in mix.items())
          + " (target " + ", ".join(f"{k} {v}" for k, v in TARGET_MIX.items()) + ")")
    return 0


def cmd_check(cfg: Config, eid: str) -> int:
    exp_dir = cfg.path(cfg.experiments)
    p = path_for(exp_dir, eid)
    if p is None:
        print(f"no experiment {eid} in {exp_dir}", file=sys.stderr)
        return 1
    d = load(p)
    sc, fails, bfails = all_failures(d, cfg)
    print(f"{eid}: rubric {'n/a (no spoken script)' if sc is None else f'{sc}/10'}, brief " + ("PASS" if not bfails else f"{len(bfails)} FAIL"))
    for f in fails + bfails:
        print("  -", f)
    if d.get("status") not in formula.BLOCKING_STATUSES:
        for f in formula.formula_findings(d, cfg):
            print(f"  advice (not blocking, already {d.get('status')}):", f)
    return 1 if fails or bfails else 0


def cmd_read(cfg: Config, eid: str, transport=None) -> int:
    exp_dir = cfg.path(cfg.experiments)
    p = path_for(exp_dir, eid)
    if p is None:
        print(f"no experiment {eid} in {exp_dir}", file=sys.stderr)
        return 1
    d = load(p)
    text, src = formula.spoken_text(d)
    try:
        chk = formula.jev_read(d, cfg, transport)
    except Exception as exc:  # noqa: BLE001 - surfaced, nothing written
        print(f"{eid}: Jev read failed, nothing stored: {exc}", file=sys.stderr)
        return 1
    d["script_check"] = chk
    save(p, d)
    r = chk["reel"]
    print(f"{eid}: script from {src} ({len(formula.sentences(text))} sentences), ${chk['cost_usd']}")
    print(f"  opener {r.get('hook_formula')} · register {r.get('register')} · format {r.get('format')} "
          f"· ask {r.get('cta_type')} · proof {r.get('proof_shown')}")
    for line in chk["roles"]:
        print("   ", line[:110])
    if chk["fails"]:
        tag = " (formula_exception set: not blocking)" if d.get("formula_exception") else ""
        print(f"  FAIL{tag}:")
        for f in chk["fails"]:
            print("  -", f)
    else:
        print("  formula PASS")
    for f in formula.formula_findings(d, cfg):
        if not f.startswith("formula (Jev)"):
            print("  -", f)
    return 0


def cmd_mix(cfg: Config, last: int) -> int:
    mix = stage_mix([d for _p, d in all_exps(cfg.path(cfg.experiments))], last)
    for st in STAGES:
        print(f"{st}: {mix[st]} (target {TARGET_MIX[st]} per ten)")
    return 0


def cmd_list(cfg: Config) -> int:
    for _p, d in all_exps(cfg.path(cfg.experiments)):
        sc, _ = score(d)
        print(f"{d.get('id', '?'):5} {d.get('status', '?'):9} score {sc:2}/10  "
              f"var={d.get('variable') or '-':8} {d.get('title', '')}")
    return 0
