"""The frames stage: Jev looks at stills from each video. See docs/formats.md.

For each video, ffmpeg pulls six stills: three from the opening (0.3 s, 1.5 s, 3 s) and three from
the body (25%, 50%, 75% of the running time). Each still goes to Jev as an image with typed
questions (questions.SHOT_Q, CAPTION_Q, and HOOK_FRAME_Q for the first still). Answers are labels
and probabilities, never free text. The per-video summary (visual format, opening shot, what
stops the scroll, shot sequence) is computed here in code.

One video is all or nothing: if any still fails, nothing is stored for it and the error is kept on
the row. Cost: about 1,100 input tokens per still, so six stills is roughly $0.0003 a video at
Jev's published input price.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import uuid
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import jev, store
from .questions import CAPTION_Q, HOOK_FRAME_Q, SHOT_Q
from .store import Store

OPENING = (0.3, 1.5, 3.0)        # seconds
BODY = (0.25, 0.5, 0.75)         # fractions of the running time
MAJORITY = 0.5                   # a shot type on at least half the stills names the visual format
FRAME_WIDTH = 480

Grab = Callable[[Path, float, Path], Path]


def frame_times(duration: float) -> list[float]:
    """Sorted, de-duplicated still times inside the video."""
    end = max(duration - 0.1, 0.0)
    ts = [min(t, end) for t in OPENING] + [round(duration * f, 2) for f in BODY]
    out: list[float] = []
    for t in sorted(ts):
        if not out or t - out[-1] >= 0.25:
            out.append(round(t, 2))
    return out


def grab_frame(mp4: Path, t: float, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(mp4),
                        "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH}:-2", "-q:v", "4", str(out)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg could not read a still at {t:.2f}s: {r.stderr[-160:]}")
    return out


def duration_of(mp4: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "default=nw=1:nk=1", str(mp4)], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe could not read the duration of {mp4.name}") from exc


def frame_payload(jpg: bytes, first: bool) -> dict:
    ref = "frame-" + uuid.uuid4().hex             # unique, so it can never match other text
    questions = {"shot": SHOT_Q, "caption": CAPTION_Q}
    if first:
        questions["hook_visual"] = HOOK_FRAME_Q
    return {"model": jev.MODEL, "state": {"frame": ref}, "questions": questions,
            "assets": {ref: {"type": "image", "format": "jpg",
                             "data_base64": base64.b64encode(jpg).decode("ascii")}}}


def frame_answers(body: dict, first: bool) -> dict:
    ans = body.get("answers") or {}
    shot = (ans.get("shot") or {}).get("choice")
    cap = (ans.get("caption") or {}).get("noul")
    if shot is None or cap is None:
        raise jev.JevError("Jev returned no shot or caption answer for a still")
    out = {"shot": str(shot), "shot_conf": (ans.get("shot") or {}).get("confidence"), "caption": float(cap)}
    if first:
        hv = (ans.get("hook_visual") or {}).get("choice")
        if hv is None:
            raise jev.JevError("Jev returned no hook_visual answer for the first still")
        out["hook_visual"] = str(hv)
    return out


def summarize(times: list[float], answers: list[dict]) -> dict:
    """Per-video facts from the per-still labels. Decisions in code, not in the model."""
    shots = [a["shot"] for a in answers]
    top, n = Counter(shots).most_common(1)[0]
    seq: list[str] = []
    for s in shots:
        if not seq or seq[-1] != s:
            seq.append(s)
    return {
        "times": times, "shots": shots, "captions": [round(a["caption"], 2) for a in answers],
        "visual_format": top if n / len(shots) >= MAJORITY else "mixed",
        "open_shot": shots[0], "hook_visual": answers[0].get("hook_visual"),
        "shot_seq": " > ".join(seq), "shot_changes": len(seq) - 1,
        "caption_share": round(sum(a["caption"] >= 0.5 for a in answers) / len(answers), 2),
    }


def read_frames(mp4: Path, key: str, work: Path, transport: jev.Transport | None = None,
                grab: Grab = grab_frame, duration: float | None = None) -> dict:
    """Stills from one video -> Jev -> summary. Raises on any failure (nothing partial)."""
    call = transport or jev.http_call
    dur = duration if duration is not None else duration_of(mp4)
    times = frame_times(dur)
    jpgs = [grab(mp4, t, work / f"{mp4.stem}_{t:06.2f}.jpg").read_bytes() for t in times]
    with ThreadPoolExecutor(max_workers=len(jpgs)) as ex:
        bodies = list(ex.map(lambda ij: call(frame_payload(ij[1], ij[0] == 0), key), enumerate(jpgs)))
    answers = [frame_answers(b, i == 0) for i, b in enumerate(bodies)]
    rec = summarize(times, answers)
    rec["tokens"] = sum(jev.tokens_of(b) for b in bodies)
    return rec


def frames_one(st: Store, post: dict, key: str, transport=None, grab: Grab = grab_frame,
               fetch: Callable[[Store, dict], Path] | None = None) -> int:
    """Label one video in place. Returns input tokens used."""
    from .visual import ensure_video
    sc = post["shortcode"]
    cache = st.frames / f"{sc}.json"
    try:
        if cache.exists():
            rec = json.loads(cache.read_text())
            used = 0
        else:
            mp4 = (fetch or ensure_video)(st, post)
            rec = read_frames(mp4, key, st.frames / "stills", transport, grab)
            st.frames.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(rec))
            used = rec.get("tokens", 0)
    except Exception as exc:  # noqa: BLE001 - recorded on the row, video left out
        post.pop("frames", None)
        post["frames_error"] = str(exc)[:160]
        return 0
    post["frames"] = {k: v for k, v in rec.items() if k != "tokens"}
    post.pop("frames_error", None)
    return used


def cmd_frames(st: Store, per_account: int, force: bool = False, workers: int = 4,
               transport=None, grab: Grab = grab_frame, fetch=None) -> int:
    key = jev.api_key()
    if not key and transport is None:
        print("[frames] set TYPESAFE_API_KEY (your TypeSafe key) first", file=sys.stderr)
        return 2
    tokens = errs = done = 0
    for path in st.files():
        payload = store.load(path)
        handle = store.handle_of(payload, path)
        jobs = [p for p in store.selected(payload, per_account)
                if p.get("url") and (force or not p.get("frames"))]
        if force:
            for p in jobs:
                (st.frames / f"{p['shortcode']}.json").unlink(missing_ok=True)
        print(f"[frames] @{handle}: {len(jobs)} videos to look at", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for post, used in zip(jobs, ex.map(lambda p: frames_one(st, p, key, transport, grab, fetch), jobs)):
                tokens += used
                done += 1
                errs += "frames_error" in post
        store.save(path, payload)
    cost = jev.cost_usd(tokens)
    run = {"finished_at": datetime.now(timezone.utc).isoformat(), "stage": "frames", "model": jev.MODEL,
           "videos": done, "input_tokens": tokens, "cost_usd": cost, "errors": errs}
    st.data.mkdir(parents=True, exist_ok=True)
    with (st.data / "decode_runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run) + "\n")
    print(f"[frames] {done} videos, {tokens:,} input tokens = ${cost:.4f}, {errs} errors")
    return 0
