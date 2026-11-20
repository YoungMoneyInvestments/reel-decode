"""Winners vs losers, judged inside one account. See README "The method".

Each video's views are divided by the median of the same account's videos from the same
calendar year (the account-wide median when that year has fewer than 8). Inside the account,
the top third of that ratio are winners and the bottom third losers, among videos at least
``min_age_days`` old. A trait's gap is winners' share with it minus losers' share with it.
Raw views are never compared across accounts or years.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from .questions import REEL_CHOICE_DIMS, REEL_NOUL_DIMS, REEL_Q, ROLE_LETTER, ROLES

MIN_JUDGED = 9        # fewer judged videos in an account = no tiers at all
MIN_PER_SIDE = 4      # fewer winners or losers = no lift table
YEAR_MIN = 8          # a calendar year needs this many videos to be its own baseline


def derived(post: dict) -> dict:
    """Structure facts computed in code from the labelled script (Jev is not a calculator)."""
    script = post.get("script") or []
    n = len(script)
    roles = [s["role"] for s in script]
    dur = post.get("spoken_seconds") or post.get("duration") or 0
    words = post.get("spoken_words") or 0
    first = script[0]["text"] if script else ""

    def first_t(role):
        return next((s["t"] for s in script if s["role"] == role), None)
    substance = [s["t"] for s in script if s["role"] in ("method", "proof", "payoff")]
    return {
        "sentences": n,
        "hook_words": len(first.split()),
        "seconds": round(dur, 1) if dur else None,
        "words_per_sec": round(words / dur, 2) if dur and words else None,
        "t_first_substance": min(substance) if substance else None,
        "t_cta": first_t("cta"),
        "has_cta": "cta" in roles,
        "has_proof": "proof" in roles,
        "proof_in_first_three": "proof" in roles[:3],
        "role_share": {r: round(roles.count(r) / n, 3) for r in ROLES} if n else {},
        "role_seq": "".join(ROLE_LETTER.get(r, "?") for r in roles),
    }


def tercile_flags(rows: list[dict], min_age_days: int = 7, now: datetime | None = None) -> None:
    """Set r["tier"] (winner / middle / loser / unjudged) and r["x_median"] on each row."""
    now = now or datetime.now(timezone.utc)
    judged = []
    for r in rows:
        age = None
        if r.get("posted_at"):
            try:
                ts = datetime.fromisoformat(str(r["posted_at"]).replace("Z", "+00:00"))
                age = (now - (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc))).days
            except ValueError:
                age = None
        r["age_days"] = age
        r["tier"] = "unjudged"
        r["x_median"] = None
        if age is not None and age >= min_age_days and r.get("views"):
            judged.append(r)
    if len(judged) < MIN_JUDGED:
        return
    all_med = statistics.median(r["views"] for r in judged)
    by_year: dict[str, list] = {}
    for r in judged:
        by_year.setdefault(str(r["posted_at"])[:4], []).append(r["views"])
    for r in judged:
        yr = by_year[str(r["posted_at"])[:4]]
        base = statistics.median(yr) if len(yr) >= YEAR_MIN else all_med
        r["x_median"] = round(r["views"] / base, 3) if base else None
    xs = sorted(r["x_median"] for r in judged if r["x_median"] is not None)
    lo, hi = xs[len(xs) // 3 - 1], xs[(2 * len(xs)) // 3]   # equal-sized top and bottom thirds
    for r in judged:
        x = r["x_median"]
        r["tier"] = "unjudged" if x is None else ("winner" if x >= hi else ("loser" if x <= lo else "middle"))


def gap_table(win: list, los: list, tests: list[tuple[str, str, object]], min_hits: int = 3) -> list[dict]:
    """[(dim, value, predicate)] -> rows sorted by absolute gap. Shares in 0..1."""
    out = []
    if len(win) < MIN_PER_SIDE or len(los) < MIN_PER_SIDE:
        return out
    for dim, value, test in tests:
        w = sum(1 for r in win if test(r))
        l_ = sum(1 for r in los if test(r))
        if w + l_ < min_hits:
            continue
        pw, pl = w / len(win), l_ / len(los)
        out.append({"dim": dim, "value": value, "win_n": w, "lose_n": l_, "win_of": len(win),
                    "lose_of": len(los), "win_share": round(pw, 3), "lose_share": round(pl, 3),
                    "gap": round(pw - pl, 3)})
    out.sort(key=lambda x: -abs(x["gap"]))
    return out


def script_tests() -> list[tuple[str, str, object]]:
    t: list[tuple[str, str, object]] = []
    for dim in REEL_CHOICE_DIMS:
        for val in REEL_Q[dim]["criteria"]:
            t.append((dim, val, lambda r, d=dim, v=val: r.get(f"d_{d}") == v))
    for dim in REEL_NOUL_DIMS:
        t.append((dim, "yes", lambda r, d=dim: (r.get(f"d_{d}") or 0) >= 0.5))
    dv = lambda r: r["dv"]
    t += [
        ("structure", "has a spoken CTA", lambda r: dv(r)["has_cta"]),
        ("structure", "has a proof sentence", lambda r: dv(r)["has_proof"]),
        ("structure", "proof in the first three sentences", lambda r: dv(r)["proof_in_first_three"]),
        ("structure", "first sentence is 12 words or fewer", lambda r: dv(r)["hook_words"] <= 12),
        ("structure", "substance starts within 5 seconds",
         lambda r: dv(r)["t_first_substance"] is not None and dv(r)["t_first_substance"] <= 5),
        ("structure", "under 30 seconds", lambda r: (dv(r)["seconds"] or 999) < 30),
        ("structure", "over 60 seconds", lambda r: (dv(r)["seconds"] or 0) > 60),
        ("structure", "setup is over a quarter of the script", lambda r: dv(r)["role_share"].get("setup", 0) > 0.25),
        ("structure", "method is over a third of the script", lambda r: dv(r)["role_share"].get("method", 0) > 0.34),
    ]
    return t


def lift_rows(rows: list[dict]) -> list[dict]:
    """For each script trait: how often winners have it vs losers, with counts."""
    for r in rows:
        if r.get("script") and not r.get("dv"):
            r["dv"] = derived(r)
    win = [r for r in rows if r.get("tier") == "winner" and r.get("script")]
    los = [r for r in rows if r.get("tier") == "loser" and r.get("script")]
    return gap_table(win, los, script_tests())


VIS_TRAITS = [
    ("text on screen in the first 3 seconds (3+ words)", lambda v: v["hook_text_words"] >= 3),
    ("face in the first frame", lambda v: v["face_first_frame"]),
    ("face on screen over half the video", lambda v: v["face_share"] > 0.5),
    ("no face at all", lambda v: v["face_share"] == 0),
    ("2+ cuts in the first 5 seconds", lambda v: v["cuts_first5"] >= 2),
    ("no cut in the first 5 seconds", lambda v: v["cuts_first5"] == 0),
    ("fast pacing (3+ cuts per 10 s)", lambda v: (v["cuts_per_10s"] or 0) >= 3),
    ("slow pacing (under 1 cut per 10 s)", lambda v: (v["cuts_per_10s"] or 0) < 1),
    ("movement in the first half second", lambda v: v["motion_start"] >= 12),
    ("text stays on screen through the video", lambda v: v["text_mid_frames"] >= 2),
]


def visual_lift(rows: list[dict]) -> list[dict]:
    win = [r for r in rows if r.get("tier") == "winner" and r.get("vis")]
    los = [r for r in rows if r.get("tier") == "loser" and r.get("vis")]
    tests = [("visual", name, lambda r, f=fn: bool(f(r["vis"]))) for name, fn in VIS_TRAITS]
    return gap_table(win, los, tests, min_hits=0)


# Production traits from rea-video (the `production` stage). Measured traits count on every decoded video;
# production-method traits count only on videos whose method call is reliable (see production.py).
PROD_TRAITS = [
    ("fast cutting (4+ shots per 10 s)", lambda p: (p.get("shots_per_10s") or 0) >= 4),
    ("long takes (under 1.5 shots per 10 s)", lambda p: p.get("shots_per_10s") is not None and p["shots_per_10s"] < 1.5),
    ("jump cuts (2+)", lambda p: p.get("jump_cuts", 0) >= 2),
    ("transition effects beyond hard cuts", lambda p: p.get("effect_transitions", 0) >= 1),
    ("text on screen in the first second", lambda p: p.get("text_first_1s")),
    ("burned-in captions", lambda p: p.get("captions", 0) >= 3),
    ("styled text callouts (3+)", lambda p: p.get("callouts", 0) >= 3),
    ("stickers or emoji", lambda p: p.get("stickers", 0) >= 1),
    ("added sound effects (3+)", lambda p: p.get("sfx", 0) >= 3),
    ("sound effects land on cuts or text (2+)", lambda p: p.get("sfx_on_cue", 0) >= 2),
    ("background music", lambda p: p.get("music")),
    ("edit cut to the beat", lambda p: p.get("beat_synced")),
    ("voice is a human recording", lambda p: p.get("voice_source") == "human_recording"),
    ("voice is TTS or AI", lambda p: p.get("voice_source") in ("tts", "ai_video_native")),
    ("camera moves over half the time", lambda p: (p.get("camera_moving_share") or 0) > 0.5),
    ("mostly close framing", lambda p: p.get("shot_size_main") in ("medium close-up", "close-up", "extreme close-up")),
]
MADE_TRAITS = [
    ("mostly filmed (over 80% live action)", lambda p: (p.get("made_mix") or {}).get("live_action", 0) > 0.8),
    ("has AI-generated shots", lambda p: (p.get("made_mix") or {}).get("ai_video", 0) > 0),
    ("has code or template graphics", lambda p: (p.get("made_mix") or {}).get("code_render", 0) > 0),
    ("has screen recording", lambda p: (p.get("made_mix") or {}).get("screen_capture", 0) > 0),
    ("has an AI avatar", lambda p: (p.get("made_mix") or {}).get("avatar", 0) > 0),
]


def production_lift(rows: list[dict]) -> list[dict]:
    """Winners vs losers on how the video was made. Method traits use only reliably-judged videos."""
    has = lambda r: bool(r.get("prod"))
    win = [r for r in rows if r.get("tier") == "winner" and has(r)]
    los = [r for r in rows if r.get("tier") == "loser" and has(r)]
    out = gap_table(win, los, [("production", n, lambda r, f=fn: bool(f(r["prod"]))) for n, fn in PROD_TRAITS],
                    min_hits=0)
    rel = lambda rs: [r for r in rs if r["prod"].get("made_reliable")]
    out += gap_table(rel(win), rel(los), [("made", n, lambda r, f=fn: bool(f(r["prod"]))) for n, fn in MADE_TRAITS],
                     min_hits=0)
    out.sort(key=lambda x: -abs(x["gap"]))
    return out
