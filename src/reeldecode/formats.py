"""Which formats, hooks and openings win, per creator and across creators. See docs/formats.md.

Every video is scored by ``x_median``: its views divided by the same account's median for the same
year (analysis.tercile_flags). So 1.0 is that creator's typical video, 2.0 is double. Raw views
are never compared across accounts, which is what makes a small creator and a huge one comparable.

For each grouping (script format, spoken hook, opening sequence of sentence jobs, visual format,
opening shot, what the first frame does) a group is reported for one creator only when it has at
least ``min_n`` judged videos. Across creators, a value counts only from creators where it reached
``min_n``; "beats typical" is the number of those creators where its median is above 1.0.
"""
from __future__ import annotations

import json
import statistics
from collections.abc import Callable
from pathlib import Path

from .questions import ROLE_LETTER

ROLE_NAME = {v: k for k, v in ROLE_LETTER.items()}
MIN_N = 3


def opening(role_seq: str | None, k: int = 3) -> str | None:
    """First k sentence jobs, filler dropped and repeats collapsed: 'HSSMP' -> 'hook > setup > method'."""
    if not role_seq:
        return None
    out: list[str] = []
    for ch in role_seq:
        if ch == "f" or (out and out[-1] == ch):
            continue
        out.append(ch)
        if len(out) == k:
            break
    return " > ".join(ROLE_NAME.get(c, "?") for c in out) if out else None


def _lab(r: dict, d: str):
    return (r.get("labels") or {}).get(d)


def _fr(r: dict, k: str):
    return (r.get("frames") or {}).get(k)


def _hk(r: dict, k: str):
    h = r.get("hook")
    return None if not h else h.get(k)


def _yn(v):
    return None if v is None else ("yes" if v else "no")


def _pair(a, b):
    return f"{a} + {b}" if a and b else None


GROUPINGS: list[tuple[str, Callable[[dict], str | None]]] = [
    ("script format", lambda r: _lab(r, "format")),
    ("spoken hook", lambda r: _lab(r, "hook_formula")),
    ("opening sequence", lambda r: opening((r.get("dv") or {}).get("role_seq"))),
    ("visual format", lambda r: _fr(r, "visual_format")),
    ("opening shot", lambda r: _fr(r, "open_shot")),
    ("first frame", lambda r: _fr(r, "hook_visual")),
    ("triple hook score (0-3)", lambda r: None if _hk(r, "score") is None else f"{_hk(r, 'score')} of 3"),
    ("context in the first words", lambda r: _yn(_hk(r, "context"))),
    ("lean", lambda r: _hk(r, "lean")),
    ("snapback", lambda r: _yn(_hk(r, "snapback_turn"))),
    ("context channels (said, written, shown)",
     lambda r: None if _hk(r, "channels") is None else (" + ".join(_hk(r, "channels")) or "none")),
    ("topic-word comment ask", lambda r: _hk(r, "keyword_ask")),
    ("script format + spoken hook", lambda r: _pair(_lab(r, "format"), _lab(r, "hook_formula"))),
    ("visual format + script format", lambda r: _pair(_fr(r, "visual_format"), _lab(r, "format"))),
    ("opening shot + spoken hook", lambda r: _pair(_fr(r, "open_shot"), _lab(r, "hook_formula"))),
]


def account_groups(reels: list[dict], min_n: int = MIN_N) -> dict[str, list[dict]]:
    """{grouping: [{value, n, median_x, winners, best}]} for one creator, best median first."""
    judged = [r for r in reels if r.get("xm") is not None]
    out: dict[str, list[dict]] = {}
    for name, key in GROUPINGS:
        by: dict[str, list[dict]] = {}
        for r in judged:
            v = key(r)
            if v:
                by.setdefault(v, []).append(r)
        rows = []
        for v, rs in by.items():
            if len(rs) < min_n:
                continue
            best = max(rs, key=lambda r: r["xm"])
            rows.append({"value": v, "n": len(rs), "median_x": round(statistics.median(r["xm"] for r in rs), 2),
                         "winners": sum(r.get("tier") == "winner" for r in rs),
                         "best": {"sc": best["sc"], "url": best.get("url"), "xm": best["xm"]}})
        rows.sort(key=lambda x: (-x["median_x"], -x["n"]))
        if rows:
            out[name] = rows
    return out


def cross_creator(per_account: dict[str, dict[str, list[dict]]]) -> dict[str, list[dict]]:
    """Pool creators with equal weight: one median per creator, never pooled raw views."""
    pool: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    for handle, groups in per_account.items():
        for name, rows in groups.items():
            for row in rows:
                pool.setdefault((name, row["value"]), []).append((handle, row))
    out: dict[str, list[dict]] = {}
    for (name, value), items in pool.items():
        meds = [row["median_x"] for _, row in items]
        out.setdefault(name, []).append({
            "value": value, "creators": len(items), "beats_typical": sum(m > 1.0 for m in meds),
            "median_of_medians": round(statistics.median(meds), 2), "videos": sum(row["n"] for _, row in items),
            "by_creator": {h: row["median_x"] for h, row in items},
        })
    for rows in out.values():
        rows.sort(key=lambda x: (-x["beats_typical"], -x["median_of_medians"], -x["creators"]))
    return out


def build(data: dict, min_n: int = MIN_N, include_yours: bool = True) -> dict:
    ours = {a["handle"] for a in data["accounts"] if a.get("ours")}
    per: dict[str, dict[str, list[dict]]] = {}
    for a in data["accounts"]:
        h = a["handle"]
        if h in ours and not include_yours:
            continue
        g = account_groups([r for r in data["reels"] if r["a"] == h], min_n)
        if g:
            per[h] = g
    others = {h: g for h, g in per.items() if h not in ours}
    with_frames = sum(1 for r in data["reels"] if r.get("frames"))
    return {"min_n": min_n, "ours": sorted(ours), "videos_with_frames": with_frames,
            "per_account": per, "across_creators": cross_creator(others)}


def _x(v: float) -> str:
    return f"{v:.2f}x"


def markdown(rep: dict, top: int = 5) -> str:
    n = rep["min_n"]
    out = ["# Formats: what wins, per creator and across creators", "",
           "Each video's score is its views divided by the same creator's median for that year, so **1.00x is "
           f"that creator's typical video**. A group needs {n}+ judged videos to show. Small groups are leads to "
           "test, not rules.", ""]
    if not rep["videos_with_frames"]:
        out += ["_No video has frame labels yet, so visual format, opening shot and first frame are empty. Run "
                "`reeldecode frames` to add them._", ""]
    cc = rep["across_creators"]
    if cc:
        out += ["## Across reference creators", "",
                "Counted once per creator. **Beats typical** = creators where that value's median is above 1.00x.", ""]
        for name, rows in cc.items():
            rows = [r for r in rows if r["creators"] >= 2][:top]
            if not rows:
                continue
            out += [f"### {name}", "", "| value | beats typical | creators | median of medians | videos |",
                    "|---|---:|---:|---:|---:|"]
            out += [f"| {r['value']} | {r['beats_typical']} of {r['creators']} | {r['creators']} | "
                    f"{_x(r['median_of_medians'])} | {r['videos']} |" for r in rows]
            out.append("")
    for h, groups in rep["per_account"].items():
        tag = " (yours)" if h in rep["ours"] else ""
        out += [f"## @{h}{tag}", ""]
        for name, rows in groups.items():
            out += [f"**{name}**", "", "| value | median | videos | winners | best example |", "|---|---:|---:|---:|---|"]
            for r in rows[:top]:
                b = r["best"]
                link = f"[{b['sc']}]({b['url']})" if b.get("url") else b["sc"]
                out.append(f"| {r['value']} | {_x(r['median_x'])} | {r['n']} | {r['winners']} | {link} ({_x(b['xm'])}) |")
            out.append("")
    if not rep["per_account"]:
        out += ["No creator has enough judged videos yet. Collect more videos, then `fetch`, `transcribe`, "
                "`anatomy` and `frames`.", ""]
    return "\n".join(out)


def cmd_formats(data: dict, out: Path, min_n: int = MIN_N, top: int = 5) -> int:
    rep = build(data, min_n)
    out.mkdir(parents=True, exist_ok=True)
    (out / "formats.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "FORMATS.md").write_text(markdown(rep, top), encoding="utf-8")
    print(f"[formats] {len(rep['per_account'])} creator(s), {rep['videos_with_frames']} videos with frame labels "
          f"-> {out}/FORMATS.md")
    return 0
