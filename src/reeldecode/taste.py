"""taste: turn 3-5 videos you want to edit like into a taste book (tastebook.md).

For each reference video: download it (yt-dlp), find every cut (ffmpeg scene detection), save a
frame just before and just after each cut, and (if Whisper is installed) transcribe with word
timestamps. Pacing is computed in code. The taste book states each rule with the video and the
timestamps it came from, so an editor or an agent driving an editing tool can follow it and a human
can check it.

Measured here: shot length, cuts in the opening, longest hold, where the cuts fall against the
spoken words. NOT measured (frames are saved so you or a vision model can judge them): zooms,
captions, b-roll, sound effects. The taste book says so instead of inventing rules for them.
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

SCENE = 0.3          # ffmpeg scene-change score above which a frame counts as a cut
MIN_SHOT = 0.25      # two cuts closer than this are one cut (flash frames, dissolves)
MAX_FRAMES = 40      # before/after frame pairs saved per video
PTS = re.compile(r"pts_time:([0-9.]+)")


# ----------------------------------------------------------------- pure functions
def parse_cuts(showinfo_stderr: str, min_shot: float = MIN_SHOT) -> list[float]:
    cuts: list[float] = []
    for t in (float(m) for m in PTS.findall(showinfo_stderr)):
        if t > 0 and (not cuts or t - cuts[-1] >= min_shot):
            cuts.append(round(t, 2))
    return cuts


def shots(cuts: list[float], duration: float) -> list[tuple[float, float]]:
    edges = [0.0] + [c for c in cuts if 0 < c < duration] + [duration]
    return [(a, round(b - a, 2)) for a, b in zip(edges, edges[1:]) if b - a > 0]


def pacing(cuts: list[float], duration: float) -> dict:
    sh = shots(cuts, duration)
    lens = [length for _, length in sh]
    return {
        "duration": round(duration, 2), "cuts": len(cuts), "shots": len(sh),
        "avg_shot": round(duration / max(len(sh), 1), 2),
        "median_shot": round(statistics.median(lens), 2) if lens else 0.0,
        "cuts_first_10s": sum(1 for c in cuts if c <= 10),
        "opening_hold": sh[0][1] if sh else duration,
        "longest": max(sh, key=lambda s: s[1]) if sh else (0.0, duration),
        "shortest": min(sh, key=lambda s: s[1]) if sh else (0.0, duration),
        "cut_times": cuts,
    }


def cuts_on_speech(cuts: list[float], sentences: list[dict], slack: float = 0.35) -> dict:
    """How many cuts land within `slack` seconds of a sentence start (a cut on the new thought)."""
    starts = [s["t"] for s in sentences]
    on = [c for c in cuts if any(abs(c - t) <= slack for t in starts)]
    return {"cuts": len(cuts), "on_sentence_start": len(on), "times": on[:6]}


def _ts(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def _med(vals: list[float]) -> float:
    return round(statistics.median(vals), 2) if vals else 0.0


def build_tastebook(stats: list[dict]) -> str:
    """tastebook.md from per-video stats: {"name","url","pacing","speech"?}. Pure and deterministic."""
    if not stats:
        raise ValueError("no videos")
    p = [s["pacing"] for s in stats]
    asl = _med([x["avg_shot"] for x in p])
    first10 = _med([float(x["cuts_first_10s"]) for x in p])
    hold = _med([x["opening_hold"] for x in p])
    lines = ["# Taste book", "",
             f"Built from {len(stats)} reference video(s). Every number below was measured in code from the "
             "videos listed at the end; each rule cites a video and timestamps you can check.", "",
             "## Pacing rules", ""]
    ex = min(stats, key=lambda s: abs(s["pacing"]["avg_shot"] - asl))
    cuts = ex["pacing"]["cut_times"][:5]
    lines += [f"1. **Cut about every {asl} s** (median average shot length across the references; "
              f"range {min(x['avg_shot'] for x in p)}-{max(x['avg_shot'] for x in p)} s). "
              f"Example, {ex['name']}: cuts at " + ", ".join(_ts(c) for c in cuts) + ".",
              f"2. **{int(first10) if first10 == int(first10) else first10} cuts in the first 10 seconds** (median).",
              f"3. **Hold the opening shot about {hold} s** before the first cut (median)."]
    long_ex = max(stats, key=lambda s: s["pacing"]["longest"][1])
    lt, ll = long_ex["pacing"]["longest"]
    lines.append(f"4. **No shot longer than {ll} s.** The longest in the references is {ll} s at "
                 f"{_ts(lt)} in {long_ex['name']}.")
    sp = [(s["name"], s["speech"]) for s in stats if s.get("speech") and s["speech"]["cuts"]]
    if sp:
        on = sum(x["on_sentence_start"] for _, x in sp)
        tot = sum(x["cuts"] for _, x in sp)
        best_name, best = max(sp, key=lambda t: t[1]["on_sentence_start"])
        lines.append(f"5. **Put cuts on the new thought.** {on} of {tot} cuts ({round(100 * on / tot)}%) land within "
                     f"0.35 s of a sentence start. Example, {best_name}: " +
                     ", ".join(_ts(t) for t in best["times"]) + ".")
    lines += ["", "## Not measured (judge from the saved frames)", "",
              "Zooms, on-screen captions, b-roll and sound effects are not detected automatically. The frames "
              "before and after every cut are saved under `frames/<video>/`. Add rules for them here after "
              "looking, with a timestamp from the video for each one, for example "
              "`zoom on the punchline: <video> 0:23.4`. An unverified rule is worse than none.", "",
              "## Per-video log", ""]
    for s in stats:
        x = s["pacing"]
        lines += [f"### {s['name']}", s.get("url", ""), "",
                  f"- {x['duration']} s, {x['shots']} shots, average {x['avg_shot']} s, median {x['median_shot']} s",
                  f"- cuts in first 10 s: {x['cuts_first_10s']}; opening hold {x['opening_hold']} s",
                  f"- longest shot {x['longest'][1]} s at {_ts(x['longest'][0])}; "
                  f"shortest {x['shortest'][1]} s at {_ts(x['shortest'][0])}",
                  "- cuts at: " + (", ".join(_ts(c) for c in x["cut_times"]) or "none"), ""]
    return "\n".join(lines).rstrip() + "\n"


# ----------------------------------------------------------------- tools (ffmpeg, yt-dlp, whisper)
def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def duration_of(path: Path) -> float:
    r = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe could not read {path}: {r.stderr[:160]}") from exc


def detect_cuts(path: Path, scene: float = SCENE) -> list[float]:
    r = _run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", f"select='gt(scene,{scene})',showinfo",
              "-an", "-f", "null", "-"])
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg scene detection failed: {r.stderr[-200:]}")
    return parse_cuts(r.stderr)


def save_frames(path: Path, cuts: list[float], out: Path, pad: float = 0.15) -> int:
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for c in cuts[:MAX_FRAMES]:
        for tag, t in (("before", max(c - pad, 0)), ("after", c + pad)):
            r = _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(path),
                      "-frames:v", "1", "-vf", "scale=360:-2", str(out / f"{c:07.2f}_{tag}.jpg")])
            n += r.returncode == 0
    return n


def download(url: str, folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    r = _run(["yt-dlp", "-q", "--no-warnings", "-f", "best[ext=mp4]/best", "-o", str(folder / f"{name}.%(ext)s"), url])
    got = [f for f in folder.glob(f"{name}.*") if f.suffix not in (".part", ".ytdl")]
    if r.returncode != 0 or not got:
        raise RuntimeError(f"yt-dlp could not download {url}: {r.stderr[-200:]}")
    return got[0]


def transcribe_sentences(path: Path, model_name: str = "small.en") -> list[dict] | None:
    try:
        import whisper
    except ImportError:
        print("[taste] openai-whisper not installed: skipping cuts-vs-speech (pip install 'reel-decode[transcribe]')",
              file=sys.stderr)
        return None
    from .decode import sentences_from_words
    res = whisper.load_model(model_name).transcribe(str(path), language="en", word_timestamps=True, fp16=False)
    words = [w for s in res.get("segments") or [] for w in s.get("words") or []]
    return sentences_from_words(words)


def cmd_taste(urls: list[str], out: Path, work: Path, model_name: str = "small.en") -> int:
    if not 1 <= len(urls) <= 8:
        print("[taste] give 3 to 5 reference videos (1 to 8 accepted)", file=sys.stderr)
        return 2
    stats = []
    for i, src in enumerate(urls, 1):
        name = f"ref{i}"
        path = Path(src) if Path(src).exists() else download(src, work / "video", name)
        dur = duration_of(path)
        cuts = detect_cuts(path)
        n = save_frames(path, cuts, work / "frames" / name)
        sents = transcribe_sentences(path, model_name)
        st = {"name": name, "url": src if "://" in src else "", "pacing": pacing(cuts, dur)}
        if sents:
            st["speech"] = cuts_on_speech(cuts, sents)
        stats.append(st)
        print(f"[taste] {name}: {dur:.1f}s, {len(cuts)} cuts, {n} frames", flush=True)
    out.write_text(build_tastebook(stats), encoding="utf-8")
    (work / "taste-stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    print(f"[taste] wrote {out}")
    return 0
