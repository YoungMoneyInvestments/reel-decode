"""ideas: turn the videos that crushed their account's normal numbers into idea cards for YOUR next briefs.

An idea card keeps the STRUCTURE of an outlier (how it opens, what format it is, the order of the jobs
its sentences do, how long it runs) and the numbers that prove it was an outlier. It deliberately
keeps no script to reuse: the opener is shown as a reference, and a brief that lists the card in
`inspired_by` is checked by the gate for copied wording (see originality.py).
"""
from __future__ import annotations

import json
from pathlib import Path

MIN_X = 3.0          # a video at least this many times its account's same-year median is an outlier


def idea_cards(data: dict, min_x: float = MIN_X, limit: int = 20, include_yours: bool = False) -> list[dict]:
    """Outlier cards from a page.build() dict, biggest multiple first. Pure and deterministic."""
    ours = {a["handle"] for a in data["accounts"] if a["ours"]}
    cards = []
    for r in data["reels"]:
        if r.get("xm") is None or r["xm"] < min_x or not r.get("script") or not r.get("labels"):
            continue
        if r["a"] in ours and not include_yours:
            continue
        dv = r["dv"] or {}
        cards.append({
            "shortcode": r["sc"], "account": r["a"], "url": r.get("url"), "views": r.get("views"), "x_median": r["xm"],
            "hook_formula": r["labels"].get("hook_formula"), "format": r["labels"].get("format"),
            "viewer_payoff": r["labels"].get("viewer_payoff"), "register": r["labels"].get("register"),
            "seconds": dv.get("seconds"), "role_seq": dv.get("role_seq"),
            "proof_in_first_three": dv.get("proof_in_first_three"), "opener": r["script"][0][2],
            "production": r.get("prod"),
        })
    cards.sort(key=lambda c: -c["x_median"])
    return cards[:limit]


def _production_lines(p: dict | None) -> list[str]:
    """How the outlier was made (rea-video), so the remake keeps its craft, not its footage."""
    if not p:
        return []
    from .production import describe
    out = [f"- how it was made: {describe(p)}"]
    if p.get("remake") and p.get("made_reliable"):
        out.append(f"- remake route: {p['remake']}")
    if p.get("package"):
        out.append(f"- shot-by-shot breakdown: `{p['package']}` (camera, lighting, caption styles, sound cues per shot)")
    return out


def cards_markdown(cards: list[dict], min_x: float) -> str:
    out = ["# Idea cards", "",
           f"Videos at least {min_x:g}x their own account's median for the same year. The structure is the idea; "
           "the wording is not yours to reuse. Write the script for your own audience and voice, then list the "
           "card's shortcode under `inspired_by:` in the brief so the gate can check it is not a copy.", ""]
    if not cards:
        out += [f"No outliers at {min_x:g}x yet. Decode more videos (`fetch`, `transcribe`, `anatomy`) or lower `--min-x`.", ""]
    for i, c in enumerate(cards, 1):
        out += [f"## {i}. {c['x_median']}x median: @{c['account']} ({c['views']} views)", "",
                f"- {c['url']}",
                f"- opens with: **{c['hook_formula']}**; format **{c['format']}**; payoff **{c['viewer_payoff']}**; "
                f"register {c['register']}",
                f"- {c['seconds']} s; sentence jobs in order `{c['role_seq']}` "
                "(H hook, S setup, T story, P proof, M method, Y payoff, C cta)",
                f"- proof in the first three sentences: {'yes' if c['proof_in_first_three'] else 'no'}",
                *_production_lines(c.get("production")),
                f"- their opener (reference only, do not reuse): \"{c['opener']}\"",
                f"- start yours: `reeldecode gate new E___ \"<your title>\" --variable hook --stage <tofu|mofu|bofu> "
                f"--account <you> --lane <lane>` then add `inspired_by: [{c['shortcode']}]`", ""]
    return "\n".join(out)


def cmd_ideas(data: dict, out: Path, min_x: float, limit: int, include_yours: bool) -> int:
    cards = idea_cards(data, min_x, limit, include_yours)
    out.mkdir(parents=True, exist_ok=True)
    (out / "ideas.json").write_text(json.dumps(cards, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "ideas.md").write_text(cards_markdown(cards, min_x), encoding="utf-8")
    print(f"[ideas] {len(cards)} outlier(s) at {min_x:g}x or more -> {out}/ideas.md")
    return 0
