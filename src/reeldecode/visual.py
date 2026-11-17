"""The visual stage: what is on screen, measured locally. No API calls.

For each video a low-resolution copy is downloaded with yt-dlp and measured:
  cuts         HSV-histogram correlation between frames sampled 5x a second (< 0.55 = a cut)
  faces        OpenCV Haar frontal-face detector, once per second
  motion       mean pixel change between frame 0 and 0.5 s (does it open on movement?)
  screen text  tesseract on three frames in the first 3 s and three mid-video frames
Every video counts here, including music-only ones the script stages have to skip.
Needs: pip install 'reel-decode[visual]' and the tesseract binary on PATH.
"""
from __future__ import annotations

import json
import random
import re
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from . import analysis, store
from .store import Store

SHORT_WORDS = {"to", "of", "in", "on", "is", "it", "my", "be", "do", "go", "if", "no", "so", "up", "we",
               "me", "us", "an", "at", "by", "or"}
_HAAR = None


def _haar():
    global _HAAR
    if _HAAR is None:
        import cv2
        _HAAR = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return _HAAR


def ocr_words(frame) -> list[str]:
    """Words tesseract reads in one frame (letters only). On-screen text, not speech."""
    import cv2
    g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    ok, png = cv2.imencode(".png", g)
    if not ok:
        return []
    r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "11", "-l", "eng"],
                       input=png.tobytes(), capture_output=True, timeout=60)
    words = re.findall(r"[A-Za-z][A-Za-z']+", r.stdout.decode("utf-8", "replace"))
    return [w for w in words if len(w) >= 3 or w.lower() in SHORT_WORDS]


def measure_file(mp4: str) -> dict:
    """Measure one local video file. Pure OpenCV + tesseract; no network."""
    import cv2
    cap = cv2.VideoCapture(mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = n / fps if fps else 0
    step = max(int(round(fps / 5)), 1)
    frames, times = [], []
    i = 0
    while cap.grab():
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                frames.append(cv2.resize(fr, (180, 320)))
                times.append(i / fps)
        i += 1
    cap.release()
    if len(frames) < 5:
        raise RuntimeError("video unreadable")
    dur = dur or times[-1]

    def hist(fr):
        h = cv2.calcHist([cv2.cvtColor(fr, cv2.COLOR_BGR2HSV)], [0, 1], None, [32, 32], [0, 180, 0, 256])
        return cv2.normalize(h, h).flatten()
    hs = [hist(f) for f in frames]
    cuts = [times[k] for k in range(1, len(hs)) if cv2.compareHist(hs[k - 1], hs[k], cv2.HISTCMP_CORREL) < 0.55]

    def face(fr):
        g = cv2.cvtColor(cv2.resize(fr, (360, 640)), cv2.COLOR_BGR2GRAY)
        return len(_haar().detectMultiScale(g, 1.15, 5, minSize=(50, 50))) > 0
    per_sec = [k for k, t in enumerate(times) if abs(t - round(t)) < 0.11]
    face_hits = [face(frames[k]) for k in per_sec]
    g0 = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY).astype("float32")
    k05 = min(range(len(times)), key=lambda k: abs(times[k] - 0.5))
    g1 = cv2.cvtColor(frames[k05], cv2.COLOR_BGR2GRAY).astype("float32")
    motion0 = float(abs(g1 - g0).mean())
    cap = cv2.VideoCapture(mp4)

    def frame_at(t):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        return fr if ok else None
    hook_words: list[str] = []
    for t in (0.4, 1.5, 2.8):
        fr = frame_at(min(t, max(dur - 0.1, 0)))
        if fr is not None:
            ws = ocr_words(fr)
            if len(ws) > len(hook_words):
                hook_words = ws
    mid_text = 0
    for f in (0.3, 0.5, 0.7):
        fr = frame_at(dur * f)
        if fr is not None and len(ocr_words(fr)) >= 3:
            mid_text += 1
    cap.release()
    return {
        "seconds": round(dur, 1),
        "cuts_first5": sum(1 for c in cuts if c <= 5),
        "cuts_per_10s": round(len(cuts) / dur * 10, 2) if dur else None,
        "face_first_frame": bool(face(frames[0])),
        "face_share": round(sum(face_hits) / len(face_hits), 2) if face_hits else 0,
        "motion_start": round(motion0, 1),
        "hook_text_words": len(hook_words), "hook_text": " ".join(hook_words)[:160],
        "text_mid_frames": mid_text,
    }


def ensure_video(st: Store, post: dict) -> Path:
    """The cached low-resolution copy of a video, downloaded with yt-dlp on first use."""
    st.video.mkdir(parents=True, exist_ok=True)
    mp4 = st.video / f"{post['shortcode']}.mp4"
    if not mp4.exists():
        time.sleep(random.uniform(0.6, 1.8))
        cmd = ["yt-dlp", "-q", "--no-warnings", "--no-playlist", "-f",
               "worstvideo[ext=mp4]/worst[ext=mp4]/worst", "-o", str(mp4), post["url"]]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if r.returncode != 0 or not mp4.exists():
            raise RuntimeError((r.stderr or r.stdout or "yt-dlp failed").strip()[-200:])
    return mp4


def visual_one(st: Store, post: dict) -> dict:
    sc = post["shortcode"]
    out = st.visual / f"{sc}.json"
    if out.exists():
        return json.loads(out.read_text())
    st.visual.mkdir(parents=True, exist_ok=True)
    mp4 = ensure_video(st, post)
    rec = {"shortcode": sc, **measure_file(str(mp4))}
    out.write_text(json.dumps(rec))
    return rec


def cmd_visual(st: Store, per_account: int, min_age_days: int, yours: set[str], workers: int = 3) -> int:
    lines = ["# Visual decode: what is on screen in winners vs losers", "",
             f"Run {datetime.now():%Y-%m-%d %H:%M}. Measured locally (OpenCV cuts and faces, tesseract "
             "for on-screen text). Winner/loser = top/bottom third inside one account against its "
             "same-year median. Gap = winners' share minus losers' share, in percentage points.", ""]
    errs = 0
    for path in st.files():
        payload = store.load(path)
        handle = store.handle_of(payload, path)
        rows = store.selected(payload, per_account)
        if not rows:
            continue
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(visual_one, st, r): r for r in rows if r.get("url")}
            for fut in as_completed(futs):
                r = futs[fut]
                try:
                    r["vis"] = fut.result()
                    r.pop("vis_error", None)
                except Exception as exc:  # noqa: BLE001 - counted and reported; video left out
                    errs += 1
                    r["vis_error"] = str(exc)[:160]
        store.save(path, payload)
        analysis.tercile_flags(rows, min_age_days)
        table = analysis.visual_lift(rows)
        have = sum(1 for r in rows if r.get("vis"))
        win = [r for r in rows if r["tier"] == "winner" and r.get("vis")]
        los = [r for r in rows if r["tier"] == "loser" and r.get("vis")]
        print(f"[visual] @{handle}: {have}/{len(rows)} measured, {len(win)} winners, {len(los)} losers", flush=True)
        lines += [f"## @{handle} ({'yours' if handle in yours else 'reference'}; {have} measured, "
                  f"{len(win)} winners vs {len(los)} losers)", ""]
        if not table:
            lines += ["Too few judged videos to compare.", ""]
            continue
        lines += ["| trait | gap | winners | losers |", "|---|---:|---:|---:|"]
        for x in table:
            lines.append(f"| {x['value']} | {x['gap'] * 100:+.0f} | {x['win_n']} of {x['win_of']} | "
                         f"{x['lose_n']} of {x['lose_of']} |")
        med = lambda xs: round(statistics.median(xs), 1) if xs else None
        lines += ["", f"Median cuts per 10 s: winners {med([r['vis']['cuts_per_10s'] for r in win if r['vis']['cuts_per_10s'] is not None])}, "
                  f"losers {med([r['vis']['cuts_per_10s'] for r in los if r['vis']['cuts_per_10s'] is not None])}.", ""]
    lines += [f"{errs} videos could not be fetched or read and are left out."]
    st.data.mkdir(parents=True, exist_ok=True)
    (st.data / "VISUAL-FINDINGS.md").write_text("\n".join(lines) + "\n")
    print(f"[visual] wrote {st.data / 'VISUAL-FINDINGS.md'} ({errs} errors)")
    return 0
