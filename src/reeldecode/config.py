"""One config file (TOML) for everything: accounts, formula thresholds, paths.

Lookup order: ``--config PATH``, then ``$REELDECODE_CONFIG``, then ``./reeldecode.toml``.
With no file at all the defaults below apply, which is enough for ``reeldecode page --demo``.
Relative paths in the file resolve against the file's own folder. Keys live in env vars only.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

CONFIG_NAME = "reeldecode.toml"

EXAMPLE = '''# reeldecode.toml: one file for the whole pipeline. Keys go in env vars, never here.
#   TYPESAFE_API_KEY   needed by `anatomy` and `gate read` (the Jev script read)

[paths]
data = "data"                 # reference_<handle>.json files plus decode.json / decode.html
cache = ".reeldecode-cache"   # audio, video, transcripts, visual measurements (safe to delete)
experiments = "experiments"   # one YAML brief per video (the brief gate and the learning loop)

[decode]
per_account = 150             # newest N reels per account (0 = all)
min_age_days = 7              # younger reels are still collecting views and are never judged
whisper_model = "small.en"

# Every account you study. Mark the ones that are yours: they are listed first on the page,
# and only they are read by the metrics loop.
[[accounts]]
handle = "your_handle"
yours = true
# Optional per-account formula rules (see docs/formula.md):
# duration = [45, 60]         # seconds; use 0 for "no lower bound"
# method_cap = true           # teaching ("method" sentences) at most a third of the script
# spoken_ask = true           # the script must end on a spoken call to action
# browser_profile = "~/.reeldecode/profiles/your_handle"   # signed-in profile for the metrics loop

# Content lanes: the recurring kinds of post this account makes. Optional. With lanes defined, every
# brief names its lane, the gate checks the lane's funnel stage and off-limits words, and
# `reeldecode lanes` shows which lanes are behind on their weekly target. See docs/lanes.md.
# [[accounts.lanes]]
# name = "founder-story"
# job = "The human side: what I am building and why"
# stages = ["tofu", "mofu"]
# format = "talking_head"     # talking_head, interview, carousel, screen_demo, ... (carousel/image/text_post skip the spoken-script checks)
# per_week = 3
# avoid = ["buy now"]

[[accounts]]
handle = "a_creator_you_study"
yours = false

[formula]
first_max_words = 12
method_max_share = 0.334
good_openers = ["specific_number", "question"]
# Your own names, so the brief gate can tell a viewer-first takeaway from a sales line.
brand_terms = []

[collect.instagram]
# Opt-in. Reads the public Reels grid of an account through YOUR OWN signed-in browser profile.
# Public data only, slow on purpose; Instagram's terms and rate limits are your responsibility.
enabled = false
profile_dir = "~/.reeldecode/browser-profile"
browser = ""                  # optional path to a Chrome/Chromium binary

[metrics]
marks_hours = [24, 72, 168]
youtube_token = ""            # optional: an OAuth authorized-user token JSON for your channel
'''


@dataclass
class Lane:
    """One recurring kind of post on an account: what it is for, and how often it ships."""
    name: str
    job: str = ""
    stages: tuple[str, ...] = ()        # funnel stages this lane may serve (empty = any)
    format: str = ""                    # free label: talking_head, interview, carousel, screen_demo...
    per_week: float = 0                 # target posts per week (0 = no cadence target)
    avoid: tuple[str, ...] = ()         # words and phrases that do not belong in this lane


@dataclass
class Account:
    handle: str
    yours: bool = False
    duration: tuple[float | None, float | None] | None = None
    method_cap: bool = False
    spoken_ask: bool = False
    browser_profile: str = ""
    lanes: list[Lane] = field(default_factory=list)

    def lane(self, name: str) -> Lane | None:
        return next((ln for ln in self.lanes if ln.name == name), None)


@dataclass
class Config:
    root: Path = field(default_factory=Path.cwd)
    data: Path = Path("data")
    cache: Path = Path(".reeldecode-cache")
    experiments: Path = Path("experiments")
    accounts: list[Account] = field(default_factory=list)
    per_account: int = 150
    min_age_days: int = 7
    whisper_model: str = "small.en"
    first_max_words: int = 12
    method_max_share: float = 0.334
    good_openers: tuple[str, ...] = ("specific_number", "question")
    brand_terms: tuple[str, ...] = ()
    ig_enabled: bool = False
    ig_profile_dir: str = "~/.reeldecode/browser-profile"
    ig_browser: str = ""
    marks_hours: tuple[int, ...] = (24, 72, 168)
    youtube_token: str = ""
    source: Path | None = None

    # ------------------------------------------------------------ lookups
    def account(self, handle: str) -> Account:
        h = normalize(handle)
        for a in self.accounts:
            if normalize(a.handle) == h:
                return a
        return Account(handle=h)

    def yours(self) -> set[str]:
        return {normalize(a.handle) for a in self.accounts if a.yours}

    def path(self, p: Path | str) -> Path:
        p = Path(os.path.expanduser(str(p)))
        return p if p.is_absolute() else (self.root / p)


def normalize(handle: str) -> str:
    return str(handle or "").strip().lstrip("@").lower()


def find(explicit: str | None = None) -> Path | None:
    for cand in (explicit, os.environ.get("REELDECODE_CONFIG"), CONFIG_NAME):
        if cand and Path(cand).expanduser().is_file():
            return Path(cand).expanduser().resolve()
    if explicit:
        raise FileNotFoundError(f"config file not found: {explicit}")
    return None


def _duration(v) -> tuple[float | None, float | None] | None:
    if not v:
        return None
    lo, hi = (list(v) + [None, None])[:2]
    return (lo or None, hi or None)


def _lane(src: Path, handle: str, x: dict) -> Lane:
    if not x.get("name"):
        raise ValueError(f"{src}: every lane under {handle} needs a name")
    stages = tuple(x.get("stages", ()))
    bad = [t for t in stages if t not in ("tofu", "mofu", "bofu")]
    if bad:
        raise ValueError(f"{src}: lane {x['name']}: stages must be tofu, mofu or bofu, not {bad}")
    return Lane(name=str(x["name"]), job=str(x.get("job", "")), stages=stages, format=str(x.get("format", "")),
                per_week=float(x.get("per_week", 0)), avoid=tuple(str(t) for t in x.get("avoid", ())))


def load(explicit: str | None = None) -> Config:
    src = find(explicit)
    if src is None:
        return Config()
    raw = tomllib.loads(src.read_text(encoding="utf-8"))
    paths = raw.get("paths", {})
    dec = raw.get("decode", {})
    form = raw.get("formula", {})
    ig = raw.get("collect", {}).get("instagram", {})
    met = raw.get("metrics", {})
    cfg = Config(root=src.parent, source=src)
    cfg.data = Path(paths.get("data", cfg.data))
    cfg.cache = Path(paths.get("cache", cfg.cache))
    cfg.experiments = Path(paths.get("experiments", cfg.experiments))
    cfg.per_account = int(dec.get("per_account", cfg.per_account))
    cfg.min_age_days = int(dec.get("min_age_days", cfg.min_age_days))
    cfg.whisper_model = str(dec.get("whisper_model", cfg.whisper_model))
    cfg.first_max_words = int(form.get("first_max_words", cfg.first_max_words))
    cfg.method_max_share = float(form.get("method_max_share", cfg.method_max_share))
    cfg.good_openers = tuple(form.get("good_openers", cfg.good_openers))
    cfg.brand_terms = tuple(form.get("brand_terms", cfg.brand_terms))
    cfg.ig_enabled = bool(ig.get("enabled", False))
    cfg.ig_profile_dir = str(ig.get("profile_dir", cfg.ig_profile_dir))
    cfg.ig_browser = str(ig.get("browser", ""))
    cfg.marks_hours = tuple(int(x) for x in met.get("marks_hours", cfg.marks_hours))
    cfg.youtube_token = str(met.get("youtube_token", ""))
    for a in raw.get("accounts", []):
        if not a.get("handle"):
            raise ValueError(f"{src}: every [[accounts]] entry needs a handle")
        cfg.accounts.append(Account(
            handle=normalize(a["handle"]), yours=bool(a.get("yours", False)),
            duration=_duration(a.get("duration")), method_cap=bool(a.get("method_cap", False)),
            spoken_ask=bool(a.get("spoken_ask", False)), browser_profile=str(a.get("browser_profile", "")),
            lanes=[_lane(src, a["handle"], x) for x in a.get("lanes", [])]))
    return cfg
