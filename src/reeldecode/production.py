"""The production stage: how each video was made, shot by shot, measured by rea-video.

rea-video (https://github.com/JuneYaooo/rea-video, Apache-2.0) breaks one video into shots and sound
stems and measures it: where the cuts are and what kind, captions and styled text with their timing,
stickers, sound effects and what they land on, voice and music and whether the edit hits the beat,
framing, camera support and lighting. It also judges each shot's production method (filmed, AI video,
code or template render, screen recording, avatar, 3D) and writes a remake plan.

This stage runs ``rea-video decompose`` on every selected video (one process per video, cached), keeps
the full breakdown package (``VIDEO.md``, ``report.html``, ``breakdown.json``) next to the cache, and
stores a compact record of the measured facts on each post as ``prod``. The winners-vs-losers tables,
the formats report and the idea cards read that record.

The production-method call is only counted when it can be trusted: a vision model or an agent
reviewed the shots, or the tools' own confidence is high. On a platform download, recompression wipes
the sensor-noise evidence the tools rely on, and a phone-shot video can come back as "AI". Everything
else here is measured, not judged, and is used as is.

Needs: ``pip install 'reel-decode[production]'`` (or ``rea-video`` on PATH) and ffmpeg.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import analysis, store
from .store import Store

MADE_MIN_CONF = 0.8        # tools-only production-method calls below this are not counted
SOURCE_MIN_PROB = 0.6      # a voice or music source call below this is "unknown"
TIMEOUT_S = 1800           # one decompose; a 60 s video takes about 3 minutes on a laptop CPU
MADE_LABELS = ("live_action", "ai_video", "code_render", "screen_capture", "avatar", "cg_3d", "anim_2d",
               "still_motion", "static_hold", "stop_motion", "film_footage")
SHOT_SIZES = {"远景": "wide", "全景": "full", "中景": "medium", "近景": "medium close-up", "特写": "close-up",
              "wide shot": "wide", "full shot": "full", "medium shot": "medium", "medium close-up": "medium close-up",
              "close-up": "close-up", "extreme close-up": "extreme close-up"}
HARD_TRANSITIONS = ("cut", "start", "jump")

Runner = Callable[..., subprocess.CompletedProcess]


class ProductionError(RuntimeError):
    pass


def rea_video_bin() -> str:
    """The rea-video executable: $REEL_DECODE_REA_VIDEO, else rea-video on PATH."""
    exe = os.environ.get("REEL_DECODE_REA_VIDEO") or shutil.which("rea-video")
    if not exe:
        raise ProductionError("rea-video is not installed: pip install 'reel-decode[production]' "
                              "(or set REEL_DECODE_REA_VIDEO to its executable). It also needs ffmpeg on PATH.")
    return exe


def decompose_cmd(exe: str, mp4: Path, out: Path, vlm: bool = False, workers: int | None = None) -> list[str]:
    cmd = [exe, "decompose", str(mp4), "-o", str(out), "--lang", "en", "--no-moments"]
    cmd.append("--vlm" if vlm else "--no-vlm")
    if workers:
        cmd += ["--workers", str(workers)]
    return cmd


def run_decompose(mp4: Path, out: Path, vlm: bool = False, runner: Runner = subprocess.run,
                  exe: str | None = None) -> dict:
    """Run rea-video on one file and return its breakdown.json. Raises on any failure; never half-records."""
    out.mkdir(parents=True, exist_ok=True)
    r = runner(decompose_cmd(exe or rea_video_bin(), mp4, out, vlm), capture_output=True, text=True, timeout=TIMEOUT_S)
    bd = out / "breakdown.json"
    if r.returncode != 0 or not bd.exists():
        tail = (r.stderr or r.stdout or "rea-video failed").strip()[-300:]
        raise ProductionError(f"rea-video decompose exit {r.returncode}: {tail}")
    return json.loads(bd.read_text(encoding="utf-8"))


def _share(d: dict | None, keys) -> float:
    return round(sum((d or {}).get(k, 0) for k in keys), 3)


def _source(node: dict | None) -> str:
    """A sound-source leaning, or "unknown" when rea-video is not sure of it."""
    if not node:
        return "unknown"
    lean = node.get("leaning") or node.get("source") or "unknown"
    p = (node.get("probs") or {}).get(lean)
    return lean if p is None or p >= SOURCE_MIN_PROB else "unknown"


def summarize(b: dict) -> dict:
    """breakdown.json -> the compact record kept on a post as ``prod``. Pure; reads machine keys only."""
    s = b.get("summary") or {}
    src = b.get("source") or {}
    dur = float(s.get("duration") or src.get("duration") or 0) or None
    shots = int(s.get("shots") or len(b.get("shots") or []))
    an = b.get("analysis") or {}
    vlm_used = bool((an.get("vlm") or {}).get("used"))
    reviewed = bool((an.get("review") or {}).get("shots"))
    conf = s.get("confidence")
    mix = {m["label"]: round(float(m["ratio"]), 3) for m in s.get("production_mix") or [] if m.get("label")}
    trans = {k: int(v) for k, v in (s.get("transitions") or {}).items()}
    pk = b.get("packaging") or {}
    counts = (pk.get("counts") or {})
    text_kinds = counts.get("text") or {}
    cues = [c for c in pk.get("text_cues") or [] if not c.get("part_of_picture")]
    au = b.get("audio") or {}
    voice, music = au.get("voice") or {}, au.get("music") or {}
    sfx = [e for e in (b.get("audio_plan") or {}).get("sfx_merged") or [] if e.get("confidence") != "low"]
    ss = b.get("sound_sources") or {}
    asp = b.get("aspects") or {}
    sizes = (asp.get("framing") or {}).get("shot_sizes") or {}
    size_main = max(sizes, key=sizes.get) if sizes else None
    support = (asp.get("camera") or {}).get("support_shares") or {}
    readers = ["tools"] + (["model"] if vlm_used else []) + (["agent"] if reviewed else [])
    return {
        "seconds": round(dur, 1) if dur else None,
        "shots": shots,
        "shots_per_10s": round(shots / dur * 10, 2) if dur else None,
        "avg_shot_s": s.get("avg_shot_s"),
        "transitions": trans,
        "jump_cuts": trans.get("jump", 0),
        "effect_transitions": sum(v for k, v in trans.items() if k not in HARD_TRANSITIONS),
        "made_mix": mix,
        "made_main": max(mix, key=mix.get) if mix else None,
        "made_confidence": conf,
        "made_reliable": bool(vlm_used or reviewed or (conf is not None and conf >= MADE_MIN_CONF)),
        "readers": readers,
        "overlays": sorted(s.get("overlay_kinds") or []),
        "text_cues": len(cues),
        "text_first_1s": any(float(c.get("t0", 99)) < 1.0 for c in cues),
        "captions": int(text_kinds.get("subtitle", 0)),
        "callouts": int(text_kinds.get("huazi", 0)) + int(text_kinds.get("label", 0)),
        "stickers": int(counts.get("stickers") or 0),
        "sfx": len(sfx),
        "sfx_on_cue": sum(1 for e in sfx if (e.get("on") or {}).get("type")),
        "voice": bool(voice.get("present")),
        "voice_share": voice.get("ratio"),
        "voice_source": _source(ss.get("voice")) if voice.get("present") else None,
        "music": bool(music.get("present")),
        "music_share": music.get("ratio") if music.get("present") else 0.0,
        "bpm": music.get("tempo_bpm") if music.get("present") else None,
        "music_source": _source(ss.get("music")) if music.get("present") else None,
        "beat_synced": bool(au.get("beat_synced_edit")),
        "camera_moving_share": round(float(support.get("moving", 0)), 3) if support else None,
        "shot_size_main": SHOT_SIZES.get(size_main, size_main),
        "lighting": ((asp.get("lighting") or {}).get("result") or {}).get("setup"),
        "remake": s.get("production") if isinstance(s.get("production"), str) else None,
        "rea_video": (b.get("tool") or {}).get("version") if isinstance(b.get("tool"), dict) else None,
    }


def ensure_video_av(st: Store, post: dict) -> Path:
    """A copy with sound, up to 1280 px tall, for rea-video (the visual stage's copy has no audio)."""
    st.video_av.mkdir(parents=True, exist_ok=True)
    mp4 = st.video_av / f"{post['shortcode']}.mp4"
    if not mp4.exists():
        time.sleep(random.uniform(0.6, 1.8))
        cmd = ["yt-dlp", "-q", "--no-warnings", "--no-playlist", "-f",
               "b[height<=1280][ext=mp4]/bv*[height<=1280]+ba/b[height<=1280]/b",
               "--merge-output-format", "mp4", "-o", str(mp4), post["url"]]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0 or not mp4.exists():
            raise ProductionError((r.stderr or r.stdout or "yt-dlp failed").strip()[-200:])
    return mp4


def production_one(st: Store, post: dict, vlm: bool = False, force: bool = False,
                   decompose: Callable[[Path, Path, bool], dict] | None = None,
                   fetch: Callable[[Store, dict], Path] = ensure_video_av) -> dict:
    sc = post["shortcode"]
    cache = st.production / f"{sc}.json"
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    mp4 = fetch(st, post)
    out = st.production / sc
    b = (decompose or run_decompose)(mp4, out, vlm)
    rec = {"shortcode": sc, **summarize(b), "package": str(out / "VIDEO.md")}
    st.production.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(rec))
    return rec


def findings_markdown(sections: list[tuple[str, bool, list[dict], list[dict], int]], errs: int) -> str:
    lines = ["# Production decode: how winners are made vs losers", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M}. Measured by rea-video (shots, transitions, captions, sound "
             "effects, voice, music, camera). Production method (filmed / AI / code / screen) is counted only where "
             f"a vision model or agent reviewed it or the tools were at least {MADE_MIN_CONF:.0%} sure. "
             "Gap = winners' share minus losers' share, in percentage points.", ""]
    for handle, ours, rows, table, n in sections:
        win = [r for r in rows if r.get("tier") == "winner" and r.get("prod")]
        los = [r for r in rows if r.get("tier") == "loser" and r.get("prod")]
        lines += [f"## @{handle} ({'yours' if ours else 'reference'}; {n} decoded, "
                  f"{len(win)} winners vs {len(los)} losers)", ""]
        if not table:
            lines += ["Too few judged videos to compare.", ""]
            continue
        lines += ["| trait | gap | winners | losers |", "|---|---:|---:|---:|"]
        for x in table:
            lines.append(f"| {x['value']} | {x['gap'] * 100:+.0f} | {x['win_n']} of {x['win_of']} | "
                         f"{x['lose_n']} of {x['lose_of']} |")
        lines.append("")
    lines += [f"{errs} videos could not be fetched or decoded and are left out."]
    return "\n".join(lines) + "\n"


def cmd_production(st: Store, per_account: int, min_age_days: int, yours: set[str], workers: int = 2,
                   vlm: bool = False, force: bool = False) -> int:
    rea_video_bin()   # fail before any download when the tool is missing
    errs, sections = 0, []
    for path in st.files():
        payload = store.load(path)
        handle = store.handle_of(payload, path)
        rows = store.selected(payload, per_account)
        if not rows:
            continue
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(production_one, st, r, vlm, force): r for r in rows if r.get("url")}
            for fut in as_completed(futs):
                r = futs[fut]
                try:
                    r["prod"] = fut.result()
                    r.pop("prod_error", None)
                except Exception as exc:  # noqa: BLE001 - counted and reported; video left out
                    errs += 1
                    r["prod_error"] = str(exc)[:200]
        store.save(path, payload)
        analysis.tercile_flags(rows, min_age_days)
        n = sum(1 for r in rows if r.get("prod"))
        print(f"[production] @{handle}: {n}/{len(rows)} decoded", flush=True)
        sections.append((handle, handle in yours, rows, analysis.production_lift(rows), n))
    st.data.mkdir(parents=True, exist_ok=True)
    out = st.data / "PRODUCTION-FINDINGS.md"
    out.write_text(findings_markdown(sections, errs))
    print(f"[production] wrote {out} ({errs} errors); full breakdowns under {st.production}/<id>/VIDEO.md")
    return 0


def describe(p: dict) -> str:
    """One readable line for a prod record (idea cards, the CLI)."""
    bits = [f"{p['shots']} shots" + (f", {p['avg_shot_s']} s each on average" if p.get("avg_shot_s") else "")]
    if p.get("made_reliable") and p.get("made_mix"):
        bits.append("made: " + ", ".join(f"{k.replace('_', ' ')} {v:.0%}" for k, v in
                                         sorted(p["made_mix"].items(), key=lambda kv: -kv[1])))
    if p.get("voice"):
        bits.append(f"voice: {(p.get('voice_source') or 'unknown').replace('_', ' ')}")
    if p.get("music"):
        bits.append("music" + (f" {p['bpm']:.0f} BPM" if p.get("bpm") else "") + (", cut to the beat" if p.get("beat_synced") else ""))
    text = [f"{p['captions']} caption lines" if p.get("captions") else None,
            f"{p['callouts']} text callouts" if p.get("callouts") else None,
            f"{p['stickers']} stickers" if p.get("stickers") else None]
    if any(text):
        bits.append(", ".join(t for t in text if t))
    if p.get("sfx"):
        bits.append(f"{p['sfx']} sound effects ({p.get('sfx_on_cue', 0)} on a cut or text)")
    return "; ".join(bits)


def cmd_production_one(target: str, out: Path, vlm: bool = False) -> int:
    """Decode one video (a local file or any URL yt-dlp can fetch) and print the compact record."""
    rea_video_bin()
    out.mkdir(parents=True, exist_ok=True)
    src = Path(target)
    if not src.exists():
        mp4 = out / "source.mp4"
        if not mp4.exists():
            r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "--no-playlist", "-f",
                                "b[height<=1280][ext=mp4]/bv*[height<=1280]+ba/b[height<=1280]/b",
                                "--merge-output-format", "mp4", "-o", str(mp4), target],
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0 or not mp4.exists():
                print(f"[production] download failed: {(r.stderr or r.stdout).strip()[-200:]}")
                return 1
        src = mp4
    try:
        b = run_decompose(src, out / "breakdown", vlm)
    except ProductionError as exc:
        print(f"[production] {exc}")
        return 1
    rec = summarize(b)
    (out / "production.json").write_text(json.dumps(rec, indent=1))
    print(describe(rec))
    if not rec["made_reliable"]:
        print(f"  production method not counted: tools-only confidence {rec['made_confidence']} "
              f"(< {MADE_MIN_CONF}); rerun with --vlm or review the shots (rea-video review)")
    print(f"  breakdown: {out / 'breakdown' / 'VIDEO.md'} · report: {out / 'breakdown' / 'report.html'}")
    return 0
