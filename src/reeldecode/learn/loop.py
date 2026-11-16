"""The learning half of the loop: log numbers on briefs, then write LEARNINGS.md.

"Typical" is the median views of an account's measured posts on the same platform (three
different videos minimum). Trial versions of one video are judged against each other at 72 h:
hold through 3 s first (the leader must be 20% clear), then average watch percent, then sends
plus saves per 1,000 views. See docs/test-and-learn.md.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from ..config import Config
from ..gate import brief

METRICS = ["views", "reach", "avg_watch_s", "likes", "comments", "shares", "saves",
           "follows", "profile_visits", "link_clicks", "keyword_comments",
           "avg_watch_pct", "hold_3s", "non_follower_pct"]
FLOAT_METRICS = {"avg_watch_s", "avg_watch_pct", "hold_3s", "non_follower_pct"}
READ_AT_HOURS = 72


def _median(xs: list) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _platform(url: str | None) -> str:
    u = url or ""
    return ("youtube" if "youtu" in u else "instagram" if "instagram.com" in u else
            "tiktok" if "tiktok.com" in u else "other")


def typical_label(ratio: float | None) -> str:
    if ratio is None:
        return "no baseline yet"
    return ("well above typical" if ratio >= 2 else "above typical" if ratio >= 1.25 else
            "typical" if ratio > 0.75 else "below typical" if ratio > 0.5 else "well below typical")


def rates(m: dict) -> dict:
    v = m.get("views") or 0
    k = (lambda x: round(1000 * (m.get(x) or 0) / v, 1)) if v else (lambda _x: None)
    return {"shares_per_1k": k("shares"), "saves_per_1k": k("saves"),
            "follows_per_1k": k("follows"), "comments_per_1k": k("comments"),
            "leads_per_1k": k("keyword_comments")}


def post_rows(exps: list[dict]) -> list[dict]:
    """One row per live post (a trial version is its own post) at its latest snapshot."""
    rows = []
    for d in exps:
        latest: dict = {}
        for s in d.get("metrics") or []:
            key = s.get("variant")
            if key not in latest or s.get("hours_since_post", 0) >= latest[key].get("hours_since_post", 0):
                latest[key] = s
        for variant, s in latest.items():
            v = s.get("views")
            sends = (s.get("shares") or 0) + (s.get("saves") or 0)
            hv = [str(h) for h in d.get("hook_variants") or []]
            listed = next((h.split(":", 1)[1].strip() for h in hv
                           if variant and h.lower().startswith(str(variant).lower() + ":")), None)
            if listed is None and variant and len(str(variant)) == 1 and hv and not any(
                    re.match(r"^\w{1,3}:", h) for h in hv):  # a plain list is in a, b, c order
                i = ord(str(variant).lower()) - ord("a")
                listed = hv[i] if 0 <= i < len(hv) else None
            top = next((x.get("hook") for x in d.get("variants") or [] if isinstance(x, dict) and variant
                        and str(x.get("id", "")).lower() == str(variant).lower()), None)
            hook = (((d.get("trial") or {}).get("variants") or {}).get(variant) or {}).get("hook") \
                or listed or top or (d.get("script") or {}).get("hook") or ""
            rows.append({
                "id": d.get("id"), "variant": variant, "title": d.get("title"), "hook": hook,
                "account": d.get("account"), "platform": _platform(s.get("url") or d.get("url")),
                "stage": (d.get("funnel") or {}).get("stage"), "variable": d.get("variable"),
                "format": d.get("format"), "hours": s.get("hours_since_post"), "views": v,
                "hold_3s": s.get("hold_3s"), "avg_watch_pct": s.get("avg_watch_pct"),
                "non_follower_pct": s.get("non_follower_pct"), "follows": s.get("follows"),
                "sends_per_1k": round(1000 * sends / v, 1) if v else None, "curve": s.get("curve"),
            })
    base: dict = {}
    ids: dict = {}
    for r in rows:
        base.setdefault((r["account"], r["platform"]), []).append(r["views"])
        ids.setdefault((r["account"], r["platform"]), set()).add(r["id"])
    for r in rows:
        k = (r["account"], r["platform"])
        # under three different videos there is no "typical": three hooks of one video are not a baseline
        med = _median(base[k]) if len(ids[k]) >= 3 else None
        r["vs_typical"] = round(r["views"] / med, 2) if med and r["views"] is not None else None
        r["label"] = typical_label(r["vs_typical"])
    return rows


def pick_winner(variants: list[dict]) -> tuple[dict | None, str]:
    """3 s hold (leader 20% clear), then watch percent, then sends per 1,000 views, then views."""
    for key, name in (("hold_3s", "hold through 3 s"), ("avg_watch_pct", "average watch percent"),
                      ("sends_per_1k", "sends plus saves per 1,000 views"), ("views", "views")):
        have = sorted((v for v in variants if v.get(key) is not None), key=lambda v: -v[key])
        if len(have) < 2 or len(have) < len(variants):
            continue
        lead, second = have[0], have[1]
        if key == "hold_3s" and not (second[key] and lead[key] >= 1.2 * second[key]):
            continue  # not 20% clear: fall through to the next measure
        if lead[key] == second[key]:
            continue
        return lead, name
    return None, "not enough numbers on every variant yet"


def learn_markdown(exps: list[dict], now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now()
    rows = post_rows(exps)
    out = ["# What is working", "",
           f"Generated {now:%Y-%m-%d %H:%M} by `reeldecode learn report` from the logged snapshots. "
           "\"Typical\" is the median views of that account's measured posts on the same platform "
           "(three videos minimum). Small samples: judge a format over ten posts, not one.", ""]
    if not rows:
        out += ["No posted video has numbers yet. Run `reeldecode learn pull` or `reeldecode learn log`.", ""]
    else:
        cols = ["id", "variant", "account", "platform", "stage", "hours", "views", "label", "vs_typical",
                "hold_3s", "avg_watch_pct", "non_follower_pct", "sends_per_1k", "follows"]
        out += ["## Every measured post, best first", "", "| " + " | ".join(cols) + " | hook |",
                "|" + "---|" * (len(cols) + 1)]
        for r in sorted(rows, key=lambda r: -(r["vs_typical"] or 0) or -(r["views"] or 0)):
            out.append("| " + " | ".join("" if r[c] is None else str(r[c]) for c in cols)
                       + " | " + str(r["hook"]).replace("|", "/")[:90] + " |")
        out.append("")
        for field, title in (("stage", "funnel stage"), ("variable", "variable tested"), ("format", "format")):
            groups: dict = {}
            for r in rows:
                groups.setdefault(r[field] or "(unset)", []).append(r)
            out += [f"## By {title}", "", "| " + field + " | posts | median views | median vs typical | "
                    "median sends per 1k | median watch % |", "|---|---|---|---|---|---|"]
            for g, rs in sorted(groups.items(), key=lambda kv: -(_median([r["vs_typical"] for r in kv[1]]) or 0)):
                cells = [g, len(rs)] + [_median([r[k] for r in rs]) for k in
                                         ("views", "vs_typical", "sends_per_1k", "avg_watch_pct")]
                out.append("| " + " | ".join("" if c is None else str(c) for c in cells) + " |")
            out.append("")
        trials: dict = {}
        for r in rows:
            if r["variant"]:
                trials.setdefault(r["id"], []).append(r)
        if trials:
            out += ["## Hook tests", ""]
            for eid, vs in sorted(trials.items()):
                d = next(d for d in exps if d.get("id") == eid)
                planned = max(len((d.get("trial") or {}).get("variants") or {}),
                              len((d.get("trial") or {}).get("posted") or {}),
                              len(re.findall(r"https?://", str(d.get("url") or ""))))
                if len(vs) < max(2, planned):
                    out.append(f"- {eid}: {len(vs)} of {planned} posted versions have numbers; no call yet.")
                    continue
                w, why = pick_winner(vs)
                young = min(v["hours"] or 0 for v in vs)
                if young < READ_AT_HOURS:
                    out.append(f"- {eid}: no call before {READ_AT_HOURS} h (youngest version read at {young} h); "
                               + (f"leader so far **{w['variant']}** on {why}." if w else f"no leader, {why}."))
                    continue
                out.append(f"- {eid}: winner **{w['variant']}** on {why} (\"{w['hook']}\")." if w
                           else f"- {eid}: no winner, {why}.")
            out.append("")
        curves = [r for r in rows if r["curve"]]
        if curves:
            out += ["## Retention curves", ""] + [
                f"- {r['id']}{'/' + r['variant'] if r['variant'] else ''}: {r['curve']}" for r in curves] + [""]
    measured = {r["id"] for r in rows}
    waiting = [d for d in exps if d.get("url") and d.get("id") not in measured]
    if waiting:
        out += ["## Posted, no numbers yet", ""] + [
            f"- {d.get('id')} ({d.get('account')}): {d.get('url')}" for d in waiting] + [""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- commands
def cmd_log(cfg: Config, eid: str, hours: float, values: dict, variant: str | None = None) -> int:
    exp_dir = cfg.path(cfg.experiments)
    p = brief.path_for(exp_dir, eid)
    if p is None:
        print(f"no experiment {eid} in {exp_dir}")
        return 1
    d = brief.load(p)
    snap = {"at": dt.datetime.now().isoformat(timespec="minutes"), "hours_since_post": hours}
    if variant:
        snap["variant"] = variant.upper()
    snap.update({k: v for k, v in values.items() if v is not None})
    d.setdefault("metrics", []).append(snap)
    if d.get("status") in (None, "", "idea", "scripted", "rendered", "scheduled"):
        d["status"] = "posted"
    brief.save(p, d)
    print(f"logged {len([k for k in values if values[k] is not None])} metrics on {eid} at {hours} h")
    return 0


def cmd_report(cfg: Config, out: Path | None = None) -> int:
    exps = [d for _p, d in brief.all_exps(cfg.path(cfg.experiments))]
    text = learn_markdown(exps)
    target = out or (cfg.path(cfg.experiments).parent / "LEARNINGS.md")
    target.write_text(text)
    print(text)
    print(f"[learn] wrote {target}")
    return 0
