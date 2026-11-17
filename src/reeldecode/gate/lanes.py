"""Content lanes: what each account is for, and whether it is posting often enough to be it.

A lane is one recurring kind of post on one account (a founder story, a trade recap, a quote
carousel). Lanes live in the config under ``[[accounts.lanes]]``. A brief names its lane; the gate
checks that the lane exists, that the brief's funnel stage is one the lane serves, that its format
matches, and that none of the lane's off-limits words appear. ``plan`` counts posted and queued
briefs per lane against its weekly target, so an empty week is visible before it happens.
"""
from __future__ import annotations

import datetime as dt
import math
import re
import sys

from ..config import Config, normalize

POSTED = {"posted", "reviewed"}
QUEUED = {"scripted", "rendered", "scheduled"}


def _text(d: dict) -> str:
    s = d.get("script") or {}
    parts = [d.get("title"), d.get("topic"), d.get("caption"), d.get("spoken_script"), s.get("hook"), s.get("reward")]
    return " ".join(str(p) for p in parts if p)


def lane_checks(d: dict, cfg: Config) -> list[str]:
    """Failures for a brief against its account's lanes. An account with no lanes has no lane rules."""
    acct = cfg.account(d.get("account") or "")
    if not acct.lanes:
        return []
    name = d.get("lane")
    if not name:
        return [f"lane missing: {acct.handle} has lanes ({', '.join(x.name for x in acct.lanes)}); name one"]
    lane = acct.lane(name)
    if lane is None:
        return [f"lane '{name}' is not defined for {acct.handle} ({', '.join(x.name for x in acct.lanes)})"]
    fails = []
    stage = (d.get("funnel") or {}).get("stage")
    if lane.stages and stage not in lane.stages:
        fails.append(f"stage {stage} does not fit lane {lane.name} (it serves {', '.join(lane.stages)})")
    if lane.format and d.get("format") and d["format"] != lane.format:
        fails.append(f"format {d['format']} does not fit lane {lane.name} (it is {lane.format})")
    text = _text(d)
    for term in lane.avoid:
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE):
            fails.append(f"'{term}' does not belong in lane {lane.name}")
    return fails


def _date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.datetime.fromisoformat(str(v)).date()
    except (TypeError, ValueError):
        return None


def plan(cfg: Config, exps: list[dict], today: dt.date, days: int = 7) -> list[dict]:
    """One row per lane: posted in the window, queued, target, shortfall, days since the last post."""
    rows = []
    for acct in cfg.accounts:
        for lane in acct.lanes:
            mine = [d for d in exps if normalize(d.get("account") or "") == acct.handle and d.get("lane") == lane.name]
            posted_dates = sorted(x for x in (_date(d.get("posted_at")) for d in mine
                                              if d.get("status") in POSTED) if x)
            in_window = [x for x in posted_dates if 0 <= (today - x).days < days]
            queued = sum(1 for d in mine if d.get("status") in QUEUED and not d.get("posted_at"))
            target = lane.per_week * days / 7
            short = max(math.ceil(target - len(in_window) - queued - 1e-9), 0) if target else 0
            rows.append({"account": acct.handle, "lane": lane.name, "format": lane.format, "target": round(target, 1),
                         "posted": len(in_window), "queued": queued, "short": short,
                         "days_since": (today - posted_dates[-1]).days if posted_dates else None})
    return rows


def cmd_plan(cfg: Config, days: int, strict: bool, today: dt.date | None = None) -> int:
    from .brief import all_exps
    if not any(a.lanes for a in cfg.accounts):
        print("no lanes defined: add [[accounts.lanes]] to the config (docs/lanes.md)", file=sys.stderr)
        return 2
    rows = plan(cfg, [d for _p, d in all_exps(cfg.path(cfg.experiments))], today or dt.date.today(), days)
    print(f"{'account':22} {'lane':20} {'format':13} target posted queued  short  last post")
    for r in rows:
        last = "never" if r["days_since"] is None else f"{r['days_since']} d ago"
        print(f"{r['account']:22} {r['lane']:20} {r['format'] or '-':13} {r['target']:6} {r['posted']:6} {r['queued']:6} "
              f"{r['short']:6}  {last}")
    gaps = [r for r in rows if r["short"]]
    if gaps:
        print(f"\n{sum(r['short'] for r in gaps)} post(s) short in the next {days} days: " +
              ", ".join(f"{r['account']}/{r['lane']} ({r['short']})" for r in gaps))
    return 1 if (strict and gaps) else 0
