"""The spoken-script stages: fetch -> transcribe -> anatomy.

fetch       audio and public metadata for each video with yt-dlp (no login), cached per id.
transcribe  local Whisper with word timestamps -> sentences with start times, cached per id.
anatomy     Jev labels every sentence (hook, setup, proof, method...) and every script
            (format, opener, payoff, ask, register, yes/no checks). Typed answers, no parsing.
"""
from __future__ import annotations

import json
import random
import re
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from . import jev, store
from .questions import REEL_Q, ROLE_Q
from .store import Store

MIN_SPOKEN_WORDS = 12     # fewer = music or visual-only video, no script to decode
SENT_END = re.compile(r"[.!?…][\"')\]]*$")


# --------------------------------------------------------------------------- fetch
def fetch_one(st: Store, post: dict) -> dict:
    """Audio + trimmed public metadata for one video. Returns the meta dict (cached)."""
    sc = post["shortcode"]
    meta_path = st.meta / f"{sc}.json"
    if meta_path.exists() and st.audio_file(sc):
        return json.loads(meta_path.read_text(encoding="utf-8"))
    time.sleep(random.uniform(0.6, 1.8))          # be gentle: one small pause per request
    tmpl = str(st.audio / f"{sc}.%(ext)s")
    cmd = ["yt-dlp", "-q", "--no-warnings", "--no-playlist", "-f", "bestaudio/worst/best",
           "--write-info-json", "-o", tmpl, post["url"]]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    info_path = st.audio / f"{sc}.info.json"
    if r.returncode != 0 or not info_path.exists():
        raise RuntimeError((r.stderr or r.stdout or "yt-dlp failed").strip()[-220:])
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info_path.unlink()
    meta = {"shortcode": sc, "caption": info.get("description") or "", "likes": info.get("like_count"),
            "comments": info.get("comment_count"), "timestamp": info.get("timestamp"),
            "duration": info.get("duration")}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def cmd_fetch(st: Store, per_account: int, workers: int = 3) -> int:
    for d in (st.audio, st.trans, st.meta):
        d.mkdir(parents=True, exist_ok=True)
    for path in st.files():
        payload = store.load(path)
        rows = store.selected(payload, per_account)
        ok = fail = streak = 0
        errors: list[str] = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(fetch_one, st, p): p for p in rows if p.get("url")}
            for fut in as_completed(futs):
                post = futs[fut]
                try:
                    meta = fut.result()
                except Exception as exc:  # noqa: BLE001 - recorded per video, run continues
                    fail += 1
                    streak += 1
                    post["fetch_error"] = str(exc)[:200]
                    errors.append(f"{post['shortcode']}: {str(exc)[:120]}")
                    if streak >= 15:
                        print(f"[fetch] {path.name}: 15 failures in a row, stopping this account "
                              "(the site is refusing; rerun later, finished videos are cached)", file=sys.stderr)
                        for f in futs:
                            f.cancel()
                        break
                    continue
                streak = 0
                ok += 1
                post.pop("fetch_error", None)
                post["caption"] = meta.get("caption") or post.get("caption") or ""
                for k in ("likes", "comments", "duration"):
                    if meta.get(k) is not None:
                        post[k] = meta[k]
                if meta.get("timestamp"):
                    post["posted_at"] = datetime.fromtimestamp(meta["timestamp"], timezone.utc).isoformat()
        store.save(path, payload)
        print(f"[fetch] {path.name}: {ok} ok, {fail} failed of {len(rows)} selected")
        for e in errors[:3]:
            print(f"    {e}")
    return 0


# --------------------------------------------------------------------------- transcribe
def sentences_from_words(words: list[dict]) -> list[dict]:
    out, cur = [], []
    for w in words:
        tok = (w.get("word") or "").strip()
        if not tok:
            continue
        cur.append(w)
        if SENT_END.search(tok) or len(cur) >= 60:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"t": round(float(g[0].get("start") or 0), 2), "end": round(float(g[-1].get("end") or 0), 2),
             "text": " ".join((w["word"] or "").strip() for w in g).strip(), "words": len(g)} for g in out]


def cmd_transcribe(st: Store, per_account: int, model_name: str, device: str = "",
                   shard: str = "", reverse: bool = False) -> int:
    try:
        import whisper  # openai-whisper
    except ImportError:
        print("[transcribe] openai-whisper is not installed: pip install 'reel-decode[transcribe]'", file=sys.stderr)
        return 2
    st.trans.mkdir(parents=True, exist_ok=True)
    codes: list[str] = []
    for path in st.files():
        codes += [p["shortcode"] for p in store.selected(store.load(path), per_account)]
    codes = sorted(set(codes))
    if shard:
        i, n = (int(x) for x in shard.split("/"))
        codes = [c for k, c in enumerate(codes) if k % n == i]
    todo = [c for c in codes if not (st.trans / f"{c}.json").exists() and st.audio_file(c)]
    print(f"[transcribe] {len(todo)} to do of {len(codes)} (shard {shard or 'all'})", flush=True)
    if not todo:
        return 0
    gpu = device == "mps"      # Apple GPU is ~9x real time but cannot do word timestamps (float64)
    model = whisper.load_model(model_name, device=device or None)
    if reverse:
        todo.reverse()
    for k, sc in enumerate(todo, 1):
        if (st.trans / f"{sc}.json").exists():      # another worker got there first
            continue
        audio = st.audio_file(sc)
        try:
            res = model.transcribe(str(audio), language="en", word_timestamps=not gpu, fp16=False,
                                   condition_on_previous_text=False, verbose=None,
                                   temperature=0.0)  # no fallback ladder: it re-decodes music six times
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                                    "stream=codec_name", "-of", "csv=p=0", str(audio)],
                                   capture_output=True, text=True)
            if probe.returncode == 0 and not probe.stdout.strip():
                doc = {"shortcode": sc, "model": model_name, "text": "", "sentences": [], "word_count": 0,
                       "no_speech_prob": 1.0, "audio_end": 0.0, "silent": True}
            else:
                doc = {"shortcode": sc, "error": str(exc)[:200]}
            (st.trans / f"{sc}.json").write_text(json.dumps(doc), encoding="utf-8")
            continue
        segs = res.get("segments") or []
        words = [w for s in segs for w in (s.get("words") or [])]
        if not words:   # no word timestamps: spread each segment's time over its words
            for s in segs:
                toks = (s.get("text") or "").split()
                span = (s["end"] - s["start"]) / max(len(toks), 1)
                words += [{"word": tok, "start": s["start"] + i * span, "end": s["start"] + (i + 1) * span}
                          for i, tok in enumerate(toks)]
        nsp = [s.get("no_speech_prob") or 0 for s in segs]
        doc = {"shortcode": sc, "model": model_name, "text": (res.get("text") or "").strip(),
               "sentences": sentences_from_words(words), "word_count": len(words),
               "no_speech_prob": round(statistics.mean(nsp), 3) if nsp else 1.0,
               "audio_end": round(float(segs[-1]["end"]), 2) if segs else 0.0}
        (st.trans / f"{sc}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        if k % 10 == 0:
            print(f"  {k}/{len(todo)}", flush=True)
    print("[transcribe] done", flush=True)
    return 0


def spoken(doc: dict | None) -> bool:
    """A real spoken script, not music or a Whisper hallucination over silence."""
    if not doc or doc.get("word_count", 0) < MIN_SPOKEN_WORDS:
        return False
    if doc.get("no_speech_prob", 0) > 0.6:
        return False
    sents = [s["text"].lower() for s in doc.get("sentences") or []]
    if len(sents) >= 4 and len(set(sents)) <= len(sents) / 2:   # looping lyric or repeated hallucination
        return False
    return True


# --------------------------------------------------------------------------- anatomy
def decode_post(post: dict, handle: str, doc: dict, key: str, transport=None) -> int:
    """Label one video's script in place. Fails closed: no partial script is ever kept.
    Returns input tokens used."""
    sents = (doc["sentences"] or [])[: jev.MAX_SENTENCES]
    try:
        res = jev.read_script(handle, [s["text"] for s in sents], key, post.get("caption") or "", transport)
    except Exception as exc:  # noqa: BLE001 - recorded on the row
        post["script_status"] = "error"
        post["script_error"] = str(exc)[:160]
        for qk in REEL_Q:
            post.pop(f"d_{qk}", None)
        return 0
    reel = res["reel"]
    if (reel.get("talking") or 0) < 0.5:           # lyrics or noise, not a script
        post["script_status"] = "no_speech"
        post["d_talking"] = reel.get("talking")
        post.pop("script", None)
        return res["tokens"]
    for k, v in reel.items():
        post[f"d_{k}"] = v
    post["script"] = [{"t": s["t"], "text": s["text"], "role": r} for s, r in zip(sents, res["roles"])]
    post["script_status"] = "decoded"
    post["spoken_seconds"] = doc.get("audio_end")
    post["spoken_words"] = doc.get("word_count")
    post.pop("script_error", None)
    return res["tokens"]


def cmd_anatomy(st: Store, per_account: int, force: bool = False, workers: int = 4, transport=None) -> int:
    key = jev.api_key()
    if not key and transport is None:
        print("[anatomy] set TYPESAFE_API_KEY (your TypeSafe key) first", file=sys.stderr)
        return 2
    tokens = errs = done = 0
    for path in st.files():
        payload = store.load(path)
        handle = store.handle_of(payload, path)
        jobs = []
        for post in store.selected(payload, per_account):
            doc = st.transcript(post["shortcode"])
            if doc is None:
                post["script_status"] = "no_transcript"
                continue
            if not spoken(doc):
                post["script_status"] = "no_speech"
                post.pop("script", None)
                continue
            if not force and post.get("script_status") in ("decoded", "no_speech"):
                continue
            jobs.append((post, doc))
        print(f"[anatomy] @{handle}: {len(jobs)} scripts to decode", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for post, used in zip([j[0] for j in jobs],
                                  ex.map(lambda j, h=handle: decode_post(j[0], h, j[1], key, transport), jobs)):
                tokens += used
                done += 1
                errs += post.get("script_status") == "error"
        store.save(path, payload)
    cost = jev.cost_usd(tokens)
    run = {"finished_at": datetime.now(timezone.utc).isoformat(), "model": jev.MODEL, "scripts": done,
           "input_tokens": tokens, "cost_usd": cost, "errors": errs}
    st.data.mkdir(parents=True, exist_ok=True)
    with (st.data / "decode_runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(run) + "\n")
    print(f"[anatomy] {done} scripts, {tokens:,} input tokens = ${cost:.4f}, {errs} errors")
    return 0


def run_costs(data_dir: Path) -> tuple[float, int]:
    cost, tokens = 0.0, 0
    rp = data_dir / "decode_runs.jsonl"
    if rp.exists():
        for line in rp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                j = json.loads(line)
                cost += j.get("cost_usd") or 0
                tokens += j.get("input_tokens") or 0
    return cost, tokens


__all__ = ["ROLE_Q", "cmd_anatomy", "cmd_fetch", "cmd_transcribe", "sentences_from_words", "spoken"]
