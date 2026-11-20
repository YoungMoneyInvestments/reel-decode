"""reeldecode: decode what separates your winning short-form videos from your losing ones.

Pipeline (each step caches, so reruns only do new work):
  collect     get the list of videos and their view counts (CSV import, or opt-in Instagram grid)
  fetch       download audio + public metadata with yt-dlp
  transcribe  local Whisper, word timestamps -> sentences
  anatomy     Jev labels every sentence and every script (needs TYPESAFE_API_KEY)
  visual      cuts, faces, opening motion and on-screen text, measured locally
  frames      Jev looks at six stills per video: shot type, captions, what the first frame does
  production  rea-video: shot-by-shot forensics (cuts, captions, SFX, voice, music, filmed/AI/code)
  hooks       Jev scores each opening on the triple hook: context, lean, snapback, topic-word ask
  formats     which formats, hooks and openings beat each creator's typical video, and across creators
  taste       reference videos -> tastebook.md (pacing rules with timestamps)
  edit-plan   Jev keep/delete/move verdict per script line, for an editing tool to apply
  page        the interactive decode page (decode.html); `page --demo` needs nothing else

Then the loop that uses what you learned:
  gate        briefs: write one per video, check it against the formula before you film
  ideas       idea cards from outlier videos (structure to learn from, never wording to copy)
  lanes       what each account is for, and which lanes are behind on their weekly target
  learn       log or pull each post's numbers, pick trial winners, write LEARNINGS.md
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import __version__, config


def _cfg(a) -> config.Config:
    return config.load(a.config)


def _store(a, cfg: config.Config):
    from .store import Store
    only = {h.strip() for h in (a.only or "").split(",") if h.strip()}
    return Store(cfg, Path(a.data).resolve() if a.data else None, only)


def _per(a, cfg) -> int:
    return cfg.per_account if a.per_account is None else a.per_account


# ------------------------------------------------------------------ commands
def c_init(a) -> int:
    p = Path(a.path)
    if p.exists() and not a.force:
        print(f"{p} exists (use --force to overwrite)", file=sys.stderr)
        return 1
    p.write_text(config.EXAMPLE)
    print(f"wrote {p}. Edit [[accounts]], then: reeldecode collect --from-csv videos.csv --handle you")
    return 0


def c_collect(a) -> int:
    cfg = _cfg(a)
    if a.from_csv:
        if not a.handle:
            print("--from-csv needs --handle", file=sys.stderr)
            return 2
        from .store import import_csv
        import_csv(cfg, Path(a.from_csv), a.handle)
        return 0
    from .collect import instagram
    if not cfg.ig_enabled:
        print(instagram.RESPONSIBLE_USE, file=sys.stderr)
        return 2
    if a.login:
        return instagram.login(cfg)
    if not a.handle:
        print("name an account: reeldecode collect HANDLE", file=sys.stderr)
        return 2
    instagram.collect(cfg, a.handle, a.max_items)
    return 0


def c_fetch(a) -> int:
    from .decode import cmd_fetch
    cfg = _cfg(a)
    return cmd_fetch(_store(a, cfg), _per(a, cfg), a.workers or 3)


def c_transcribe(a) -> int:
    from .decode import cmd_transcribe
    cfg = _cfg(a)
    return cmd_transcribe(_store(a, cfg), _per(a, cfg), a.model or cfg.whisper_model, a.device, a.shard, a.reverse)


def c_anatomy(a) -> int:
    from .decode import cmd_anatomy
    cfg = _cfg(a)
    return cmd_anatomy(_store(a, cfg), _per(a, cfg), a.force, a.workers or 4)


def c_visual(a) -> int:
    from .visual import cmd_visual
    cfg = _cfg(a)
    return cmd_visual(_store(a, cfg), _per(a, cfg), cfg.min_age_days, cfg.yours(), a.workers or 3)


def c_frames(a) -> int:
    from .frames import cmd_frames
    cfg = _cfg(a)
    return cmd_frames(_store(a, cfg), _per(a, cfg), a.force, a.workers or 4)


def c_production(a) -> int:
    from . import production
    try:
        if a.one:
            return production.cmd_production_one(a.one, Path(a.out), a.vlm)
        cfg = _cfg(a)
        return production.cmd_production(_store(a, cfg), _per(a, cfg), cfg.min_age_days, cfg.yours(),
                                         a.workers or 2, a.vlm, a.force)
    except production.ProductionError as exc:
        print(f"[production] {exc}", file=sys.stderr)
        return 1


def c_hooks(a) -> int:
    from .hooks import cmd_hooks
    cfg = _cfg(a)
    return cmd_hooks(_store(a, cfg), _per(a, cfg), a.force, a.workers or 6)


def c_formats(a) -> int:
    from . import page
    from .formats import cmd_formats
    from .store import Store
    if a.demo:
        st, yours, per, min_age = Store(config.Config(), page.demo_dir()), {"demo_creator"}, 0, 7
        out = Path(a.out or "reeldecode-demo")
    else:
        cfg = _cfg(a)
        st, yours, per, min_age = _store(a, cfg), cfg.yours(), _per(a, cfg), cfg.min_age_days
        out = Path(a.out) if a.out else st.data
    return cmd_formats(page.build(st, per, min_age, yours), out, a.min_n, a.top)


def c_taste(a) -> int:
    from .taste import cmd_taste
    cfg = _cfg(a)
    return cmd_taste(a.videos, Path(a.out), Path(a.work), a.model or cfg.whisper_model)


def c_edit_plan(a) -> int:
    from . import jev
    from .edit import cmd_edit_plan
    return cmd_edit_plan(Path(a.script), Path(a.out), jev.api_key())


def c_page(a) -> int:
    from . import page
    from .store import Store
    cfg = _cfg(a)
    if a.demo:
        st = Store(config.Config(), page.demo_dir())
        yours = {"demo_creator"}
        out = Path(a.out or "reeldecode-demo")
        per, min_age = 0, 7
    else:
        st = _store(a, cfg)
        yours = cfg.yours()
        out = Path(a.out) if a.out else st.data
        per, min_age = _per(a, cfg), cfg.min_age_days
    path = page.cmd_page(st, per, min_age, yours, out)
    if a.open:
        webbrowser.open(path.resolve().as_uri())
    return 0


def c_ideas(a) -> int:
    from . import page
    from .ideas import cmd_ideas
    from .store import Store
    if a.demo:
        st, yours, per, min_age = Store(config.Config(), page.demo_dir()), {"demo_creator"}, 0, 7
        out = Path(a.out or "reeldecode-demo")
    else:
        cfg = _cfg(a)
        st, yours, per, min_age = _store(a, cfg), cfg.yours(), _per(a, cfg), cfg.min_age_days
        out = Path(a.out) if a.out else st.data
    return cmd_ideas(page.build(st, per, min_age, yours), out, a.min_x, a.limit, a.include_yours)


def c_gate(a) -> int:
    from .gate import brief
    cfg = _cfg(a)
    if a.gate_cmd == "new":
        return brief.cmd_new(cfg, a.id, a.title, a.variable, a.stage, a.account, a.control, a.lane, a.format)
    if a.gate_cmd == "check":
        return brief.cmd_check(cfg, a.id)
    if a.gate_cmd == "read":
        return brief.cmd_read(cfg, a.id)
    if a.gate_cmd == "mix":
        return brief.cmd_mix(cfg, a.last)
    return brief.cmd_list(cfg)


def c_lanes(a) -> int:
    from .gate import lanes
    return lanes.cmd_plan(_cfg(a), a.days, a.strict)


def c_learn(a) -> int:
    from .learn import loop
    cfg = _cfg(a)
    if a.learn_cmd == "log":
        vals = {m: getattr(a, m) for m in loop.METRICS}
        return loop.cmd_log(cfg, a.id, a.hours, vals, a.variant)
    if a.learn_cmd == "pull":
        from .learn import metrics
        return metrics.cmd_pull(cfg, a.ids, a.all, a.dry_run)
    return loop.cmd_report(cfg, Path(a.out) if a.out else None)


# ------------------------------------------------------------------ parser
def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="path to reeldecode.toml (default: ./reeldecode.toml or $REELDECODE_CONFIG)")
    data = argparse.ArgumentParser(add_help=False)
    data.add_argument("--data", help="dataset folder (overrides [paths] data)")
    data.add_argument("--only", default="", help="comma-separated handles; default every account in the folder")
    data.add_argument("--per-account", type=int, default=None, help="newest N videos per account (0 = all)")
    data.add_argument("--workers", type=int, default=0, help="parallel workers")

    ap = argparse.ArgumentParser(prog="reeldecode", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"reeldecode {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    p = sub.add_parser("init", help="write a starter reeldecode.toml", parents=[common])
    p.add_argument("path", nargs="?", default=config.CONFIG_NAME)
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=c_init)

    p = sub.add_parser("collect", parents=[common], help="list an account's videos and view counts",
                       description="Build data/reference_<handle>.json. From a CSV (url, views[, posted_at, "
                       "caption, likes, comments]) or, opt-in, from Instagram's public Reels grid through "
                       "your own signed-in browser profile ([collect.instagram] in the config).")
    p.add_argument("handle", nargs="?")
    p.add_argument("--from-csv", help="import a CSV instead of using a browser")
    p.add_argument("--handle", dest="handle_opt", help="account handle for --from-csv")
    p.add_argument("--max-items", type=int, default=600)
    p.add_argument("--login", action="store_true", help="open a window to sign in to the browser profile")
    p.set_defaults(fn=c_collect)

    p = sub.add_parser("fetch", parents=[common, data], help="download audio + metadata with yt-dlp")
    p.set_defaults(fn=c_fetch)

    p = sub.add_parser("transcribe", parents=[common, data], help="local Whisper transcripts with timestamps")
    p.add_argument("--model", default="", help="Whisper model (default from config, small.en)")
    p.add_argument("--device", default="", help="cpu (default), cuda, or mps (Apple GPU, no word timestamps)")
    p.add_argument("--shard", default="", help="i/n: this process takes every n-th file, for parallel runs")
    p.add_argument("--reverse", action="store_true", help="work the list from the end (a second lane)")
    p.set_defaults(fn=c_transcribe)

    p = sub.add_parser("anatomy", parents=[common, data], help="Jev labels every sentence and script")
    p.add_argument("--force", action="store_true", help="redo scripts already decoded")
    p.set_defaults(fn=c_anatomy)

    p = sub.add_parser("visual", parents=[common, data], help="cuts, faces, motion, on-screen text")
    p.set_defaults(fn=c_visual)

    p = sub.add_parser("frames", parents=[common, data], help="Jev looks at stills: shot type, captions, first frame")
    p.add_argument("--force", action="store_true", help="look again at videos already labelled")
    p.set_defaults(fn=c_frames)

    p = sub.add_parser("production", parents=[common, data],
                       help="rea-video: shots, cuts, captions, sound effects, voice, music, how each video was made")
    p.add_argument("--vlm", action="store_true",
                   help="let rea-video's vision model judge each shot (REA_VLM_BASE_URL / _API_KEY / _MODEL); "
                        "without it the filmed/AI/code call is counted only when the tools are sure")
    p.add_argument("--force", action="store_true", help="decode again videos already decoded")
    p.add_argument("--one", default="", help="decode one video (file or URL) instead of the dataset")
    p.add_argument("--out", default="production-one", help="output folder for --one")
    p.set_defaults(fn=c_production)

    p = sub.add_parser("hooks", parents=[common, data], help="Jev scores each opening: context, lean, snapback, ask")
    p.add_argument("--force", action="store_true", help="score again videos already scored")
    p.set_defaults(fn=c_hooks)

    p = sub.add_parser("formats", parents=[common, data], help="which formats, hooks and openings win, per creator and across")
    p.add_argument("--min-n", type=int, default=3, help="videos a group needs before it is shown (default 3)")
    p.add_argument("--top", type=int, default=5, help="rows per table (default 5)")
    p.add_argument("--demo", action="store_true", help="use the bundled synthetic dataset (offline)")
    p.add_argument("--out", help="output folder (default: the data folder)")
    p.set_defaults(fn=c_formats)

    p = sub.add_parser("taste", parents=[common], help="reference videos in, tastebook.md out (pacing rules with timestamps)")
    p.add_argument("videos", nargs="+", help="3 to 5 URLs or local files of edits you want to copy")
    p.add_argument("--out", default="tastebook.md")
    p.add_argument("--work", default="taste-work", help="folder for downloads and before/after cut frames")
    p.add_argument("--model", default="", help="Whisper model (default from config)")
    p.set_defaults(fn=c_taste)

    p = sub.add_parser("edit-plan", parents=[common], help="Jev: keep, delete or move each script line")
    p.add_argument("script", help="text file, one script line per line")
    p.add_argument("--out", default="edit-plan", help="folder for edit-plan.json and edit-plan.md")
    p.set_defaults(fn=c_edit_plan)

    p = sub.add_parser("page", parents=[common, data], help="build the interactive decode page")
    p.add_argument("--demo", action="store_true", help="use the bundled synthetic dataset (offline)")
    p.add_argument("--out", help="output folder (default: the data folder, or ./reeldecode-demo)")
    p.add_argument("--open", action="store_true", help="open the page in your browser")
    p.set_defaults(fn=c_page)

    p = sub.add_parser("ideas", parents=[common, data], help="idea cards from videos that crushed their account's median")
    p.add_argument("--min-x", type=float, default=3.0, help="times the account's same-year median (default 3)")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--include-yours", action="store_true", help="also cards from your own best videos")
    p.add_argument("--demo", action="store_true", help="use the bundled synthetic dataset (offline)")
    p.add_argument("--out", help="output folder (default: the data folder)")
    p.set_defaults(fn=c_ideas)

    g = sub.add_parser("gate", parents=[common], help="briefs and the script formula check")
    gs = g.add_subparsers(dest="gate_cmd", required=True, metavar="ACTION")
    x = gs.add_parser("new", parents=[common], help="start a brief from the template")
    x.add_argument("id", help="experiment id, e.g. E001")
    x.add_argument("title")
    x.add_argument("--variable", required=True, choices=["hook", "story", "payoff", "cta", "format", "length", "baseline"])
    x.add_argument("--stage", required=True, choices=["tofu", "mofu", "bofu"],
                   help="funnel job: tofu reaches strangers, mofu builds trust, bofu asks")
    x.add_argument("--account", required=True)
    x.add_argument("--control", help="the experiment this one is compared against")
    x.add_argument("--lane", default="", help="the content lane this post belongs to (see docs/lanes.md)")
    x.add_argument("--format", default="", help="talking_head, interview, carousel, screen_demo, ...")
    x = gs.add_parser("check", parents=[common], help="exit 1 unless the brief passes every check")
    x.add_argument("id")
    x = gs.add_parser("read", parents=[common], help="Jev reads the spoken script; stored on the brief")
    x.add_argument("id")
    x = gs.add_parser("mix", parents=[common], help="funnel-stage mix of the recent briefs")
    x.add_argument("--last", type=int, default=10)
    gs.add_parser("list", parents=[common], help="every brief with its rubric score")
    g.set_defaults(fn=c_gate)

    p = sub.add_parser("lanes", parents=[common], help="content lanes per account: posted, queued, short of target")
    p.add_argument("--days", type=int, default=7, help="window to plan, in days (default 7)")
    p.add_argument("--strict", action="store_true", help="exit 1 if any lane is short")
    p.set_defaults(fn=c_lanes)

    from .learn.loop import FLOAT_METRICS, METRICS
    lp = sub.add_parser("learn", parents=[common], help="log numbers, pull numbers, write LEARNINGS.md")
    ls = lp.add_subparsers(dest="learn_cmd", required=True, metavar="ACTION")
    x = ls.add_parser("log", parents=[common], help="type in one snapshot of a post's numbers")
    x.add_argument("id")
    x.add_argument("--hours", type=float, required=True, help="hours since posting")
    x.add_argument("--variant", help="trial version letter (A, B, C)")
    for m in METRICS:
        x.add_argument("--" + m.replace("_", "-"), dest=m, type=float if m in FLOAT_METRICS else int)
    x = ls.add_parser("pull", parents=[common], help="read your own posts' numbers at 24 h / 72 h / 7 d")
    x.add_argument("ids", nargs="*")
    x.add_argument("--all", action="store_true", help="snapshot now, whatever the mark")
    x.add_argument("--dry-run", action="store_true")
    x = ls.add_parser("report", parents=[common], help="write LEARNINGS.md")
    x.add_argument("--out")
    lp.set_defaults(fn=c_learn)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if a.cmd == "collect":
        a.handle = a.handle or a.handle_opt
    return int(a.fn(a) or 0)


if __name__ == "__main__":
    sys.exit(main())
