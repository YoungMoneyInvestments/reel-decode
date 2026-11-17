"""Build decode.json and the single-file interactive page (decode.html) from the dataset."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from . import analysis, jev, store
from .decode import run_costs
from .questions import REEL_CHOICE_DIMS, REEL_NOUL_DIMS, REEL_Q, ROLES
from .store import Store

FRAME_KEYS = ("visual_format", "open_shot", "hook_visual", "shot_seq", "shot_changes", "caption_share")


def demo_dir() -> Path:
    return Path(str(resources.files("reeldecode") / "demo_data"))


def build(st: Store, per_account: int, min_age_days: int, yours: set[str],
          now: datetime | None = None) -> dict:
    accounts, reels = [], []
    for path in st.files():
        payload = store.load(path)
        handle = store.handle_of(payload, path)
        rows = store.selected(payload, per_account)
        if not rows:
            continue
        for r in rows:
            r["dv"] = analysis.derived(r) if r.get("script") else None
        analysis.tercile_flags(rows, min_age_days, now)
        decoded = [r for r in rows if r.get("script")]
        judged = [r for r in rows if r["tier"] != "unjudged"]
        accounts.append({
            "handle": handle, "ours": handle in yours, "reels": len(rows), "decoded": len(decoded),
            "no_speech": sum(1 for r in rows if r.get("script_status") == "no_speech"),
            "judged": len(judged),
            "median_views": statistics.median([r["views"] for r in judged]) if judged else None,
            "lift": analysis.lift_rows(rows),
        })
        for r in rows:
            sc = r.get("script")
            reels.append({
                "a": handle, "sc": r["shortcode"], "url": r.get("url"), "views": r.get("views"),
                "likes": r.get("likes"), "comments": r.get("comments"), "posted": str(r.get("posted_at") or "")[:10],
                "age": r.get("age_days"), "tier": r["tier"], "xm": r.get("x_median"),
                "status": r.get("script_status") or "not_fetched",
                "caption": (r.get("caption") or "")[:280],
                "labels": {d: r.get(f"d_{d}") for d in REEL_CHOICE_DIMS} if sc else None,
                "checks": {d: (round(r.get(f"d_{d}"), 2) if isinstance(r.get(f"d_{d}"), (int, float)) else None)
                           for d in REEL_NOUL_DIMS} if sc else None,
                "dv": r["dv"],
                "hook": {k: v for k, v in r["hook"].items()} if r.get("hook") else None,
                "frames": {k: r["frames"].get(k) for k in FRAME_KEYS} if r.get("frames") else None,
                "script": [[s["t"], s["role"], s["text"]] for s in sc] if sc else None,
            })
    cost, tokens = run_costs(st.data)
    return {"generated_at": (now or datetime.now(timezone.utc)).isoformat(), "model": jev.MODEL,
            "min_age_days": min_age_days, "jev_cost_usd": round(cost, 4), "jev_input_tokens": tokens,
            "roles": ROLES, "dims": {d: list(REEL_Q[d]["criteria"]) for d in REEL_CHOICE_DIMS},
            "accounts": accounts, "reels": reels}


def render(data: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decode.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tpl = (resources.files("reeldecode") / "templates" / "decode_page.html").read_text(encoding="utf-8")
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = out_dir / "decode.html"
    page.write_text(tpl.replace("__DATA__", blob), encoding="utf-8")
    return page


def cmd_page(st: Store, per_account: int, min_age_days: int, yours: set[str], out_dir: Path,
             now: datetime | None = None) -> Path:
    data = build(st, per_account, min_age_days, yours, now)
    page = render(data, out_dir)
    print(f"[page] wrote {page}: {len(data['reels'])} videos, "
          f"{sum(a['decoded'] for a in data['accounts'])} with a decoded script, Jev ${data['jev_cost_usd']:.4f}")
    for a in data["accounts"]:
        print(f"   @{a['handle']}: {a['reels']} videos, {a['decoded']} decoded, {a['no_speech']} no speech, "
              f"{a['judged']} judged, median {a['median_views']}")
    return page
