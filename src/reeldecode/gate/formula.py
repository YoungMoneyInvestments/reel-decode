"""The script formula as checks a brief must pass before anyone renders it. See docs/formula.md.

Default rules (every account), from the winners-vs-losers study this tool came out of:
  * first spoken sentence is ``first_max_words`` (12) words or fewer
  * it opens on a number or a question, not a flat statement or a call-out
  * a proof sentence (result, figure, named source) sits in the first three sentences   [Jev]
  * the delivery is not a neutral, informational read                                    [Jev]
Optional per-account rules in reeldecode.toml: ``duration``, ``method_cap``, ``spoken_ask``.

Two layers:
  formula_checks(d)  no network; part of ``reeldecode gate check``.
  jev_read(d)        asks Jev to label the spoken script (``reeldecode gate read``). The result is
                     stored in the brief as ``script_check`` with a hash of the script, and
                     formula_checks requires a stored read whose hash matches the current script.

A brief that deliberately tests another shape sets ``formula_exception: "<why>"``; the checks then
report but do not block. These are associations in a sample, not causes: the exception is for a
real test (a new opener, a teaching lane), never to skip the work.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

from .. import jev
from ..config import Account, Config, normalize

DONE_STATUSES = {"posted", "reviewed"}
# The formula blocks scripts, not finished work: a rendered or scheduled video gets advice only.
BLOCKING_STATUSES = {None, "", "idea", "scripted"}

NUM_WORDS = (r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
             r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
             r"eighty|ninety|hundred|thousand|million|billion|half|double|triple")
NUMBER = re.compile(rf"[\d$%€£]|\b({NUM_WORDS})\b", re.IGNORECASE)
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
SHOT_PREFIX = re.compile(r"^\s*SHOT\s+[\w-]+:\s*", re.IGNORECASE)
# full_script keys that are production notes, not spoken words
NOTE_KEYS = re.compile(r"voice|direction|note|music|sfx|visual|broll|b_roll|caption|on_screen|text", re.IGNORECASE)


# ---------------------------------------------------------------- the spoken script
def _flatten(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for i in v for x in _flatten(i)]
    if isinstance(v, dict):
        return [x for k, i in v.items() if not NOTE_KEYS.search(str(k)) for x in _flatten(i)]
    return []


def spoken_text(d: dict) -> tuple[str, str]:
    """(script, source): ``spoken_script`` if set, then ``full_script``, then the script beats."""
    if str(d.get("spoken_script") or "").strip():
        return str(d["spoken_script"]).strip(), "spoken_script"
    if d.get("full_script"):
        parts = []
        for p in _flatten(d["full_script"]):
            for line in p.split(" / "):
                line = SHOT_PREFIX.sub("", line).strip()
                if line:
                    parts.append(line)
        if parts:
            return " ".join(parts), "full_script"
    s = d.get("script") or {}
    beats = [s.get("hook"), s.get("sub_hook"), *(s.get("rehooks") or []), s.get("reward"),
             (s.get("cta") or {}).get("text")]
    return " ".join(str(b).strip() for b in beats if b and str(b).strip()), "script beats"


def sentences(text: str) -> list[str]:
    return [x.strip() for x in SENT_SPLIT.split(text) if x.strip()]


def script_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- gate (no network)
def formula_checks(d: dict, cfg: Config | None = None) -> list[str]:
    """Blocking failures (empty = pass). Only briefs still at idea or scripted are blocked."""
    if d.get("status") not in BLOCKING_STATUSES:
        return []
    return formula_findings(d, cfg)


def formula_findings(d: dict, cfg: Config | None = None) -> list[str]:
    """Everything the formula flags on an unposted brief, blocking or not."""
    cfg = cfg or Config()
    if d.get("status") in DONE_STATUSES:
        return []
    acct = cfg.account(d.get("account") or "")
    text, src = spoken_text(d)
    sents = sentences(text)
    if not sents:
        return [f"formula: no spoken script found (add `spoken_script:`; looked in {src})"]
    fails: list[str] = []
    first = sents[0]
    if len(first.split()) > cfg.first_max_words:
        fails.append(f"formula: first spoken sentence is {len(first.split())} words; keep it to "
                     f"{cfg.first_max_words} or fewer (\"{first[:60]}\")")
    if not (first.rstrip().endswith("?") or NUMBER.search(first)):
        fails.append("formula: open on a number or a question, not a flat statement or a call-out "
                     f"(\"{first[:60]}\")")
    lo, hi = acct.duration or (None, None)
    dur = d.get("duration_s")
    if lo is not None or hi is not None:
        span = f"{lo or 0} to {hi or 'any'} s"
        if not isinstance(dur, (int, float)):
            fails.append(f"formula: set duration_s; @{acct.handle} runs {span}")
        elif (lo and dur < lo) or (hi and dur > hi):
            fails.append(f"formula: duration_s {dur} is outside @{acct.handle}'s {span}")
    chk = d.get("script_check") or {}
    if not chk:
        fails.append(f"formula: no Jev read of the script yet (run `reeldecode gate read {d.get('id', 'E###')}`)")
    elif chk.get("hash") != script_hash(text):
        fails.append("formula: the script changed since the Jev read; run `reeldecode gate read` again")
    else:
        fails += [f"formula (Jev): {f}" for f in chk.get("fails") or []]
    if fails and str(d.get("formula_exception") or "").strip():
        return []  # a declared test of another shape: reported by `gate read`, not blocking
    return fails


def judge(acct: Account, sents: list[str], roles: list[str], reel: dict, cfg: Config | None = None) -> list[str]:
    """The Jev-read half of the formula. Pure, so it is testable without the network."""
    cfg = cfg or Config()
    fails: list[str] = []
    n = len(sents)
    if reel.get("hook_formula") not in cfg.good_openers:
        fails.append(f"opener reads as '{reel.get('hook_formula')}'; open on "
                     + " or ".join(o.replace("_", " ") for o in cfg.good_openers))
    if "proof" not in roles[:3]:
        fails.append("no proof sentence (result, figure, named source) in the first three sentences")
    if reel.get("register") == "neutral_info":
        fails.append("delivery reads neutral and informational; give it energy, edge or play")
    if acct.method_cap and n:
        share = roles.count("method") / n
        if share > cfg.method_max_share:
            fails.append(f"method is {share:.0%} of the script; keep teaching to a third or less on @{acct.handle}")
    if acct.spoken_ask and reel.get("cta_type") in (None, "none"):
        fails.append(f"no spoken ask; @{acct.handle} is set to end every script on one")
    return fails


def jev_read(d: dict, cfg: Config | None = None, transport=None) -> dict:
    """Label the brief's spoken script with Jev and judge it. Returns the ``script_check`` record."""
    cfg = cfg or Config()
    key = jev.api_key()
    if not key and transport is None:
        raise RuntimeError("TYPESAFE_API_KEY is not set")
    acct = cfg.account(d.get("account") or "")
    text, src = spoken_text(d)
    sents = sentences(text)[: jev.MAX_SENTENCES]
    if not sents:
        raise RuntimeError(f"no spoken script found (looked in {src})")
    res = jev.read_script(normalize(acct.handle), sents, key, "", transport)
    reel = res["reel"]
    return {
        "hash": script_hash(text), "source": src, "model": jev.MODEL,
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "cost_usd": jev.cost_usd(res["tokens"]),
        "reel": {k: reel.get(k) for k in ("format", "hook_formula", "register", "cta_type",
                                          "viewer_payoff", "proof_shown", "self_promo")},
        "roles": [f"{r}: {s}" for r, s in zip(res["roles"], sents)],
        "fails": judge(acct, sents, res["roles"], reel, cfg),
    }
