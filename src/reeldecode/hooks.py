"""The triple hook: context, lean, snapback, then a topic-word ask. See docs/hooks.md.

Jev answers the typed questions in questions.HOOK_Q about a video's opening (first four spoken
sentences) and ending (last three), plus VISUAL_CONTEXT_Q on the first still when the frames
stage kept it. Code turns the answers into the parts and a 0-3 score:

  context   the topic is clear in the first half of sentence 1 (context_spot == first_words)
  lean      something pulls the viewer in (lean != none) AND they would want more (leans_in)
  snapback  a later opening sentence turns against the direction the viewer was leaning
  score     context + lean + snapback (0-3); 3 is the full triple hook
  close     a comment-a-word ask whose word matches the topic, after the payoff is delivered

``channels`` counts where the context is set: said (audio), written (on-screen text), shown
(the first frame). The method asks for all three.
"""
from __future__ import annotations

import base64
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from . import jev, store
from .questions import HOOK_Q, VISUAL_CONTEXT_Q
from .store import Store

OPENING_N = 4
ENDING_N = 3
YES = 0.5


def numbered(sents: list[str]) -> str:
    return "\n".join(f"{i}. {s}" for i, s in enumerate(sents, 1))


def text_payload(sents: list[str], on_screen_text: str = "") -> dict:
    qs = dict(HOOK_Q)
    if not on_screen_text.strip():
        qs.pop("text_context")
    state = {"opening": numbered(sents[:OPENING_N]), "ending": numbered(sents[-ENDING_N:]),
             "on_screen_text": on_screen_text[:300]}
    return {"model": jev.MODEL, "state": state, "questions": qs}


def image_payload(jpg: bytes, first_sentence: str) -> dict:
    ref = "frame-" + uuid.uuid4().hex
    return {"model": jev.MODEL, "state": {"frame": ref, "first_sentence": first_sentence},
            "questions": {"visual_context": VISUAL_CONTEXT_Q},
            "assets": {ref: {"type": "image", "format": "jpg", "data_base64": base64.b64encode(jpg).decode("ascii")}}}


def _ans(body: dict, q: str, required: bool = True):
    a = (body.get("answers") or {}).get(q)
    if not isinstance(a, dict):
        if required:
            raise jev.JevError(f"no answer for {q}")
        return None
    return a.get("noul") if "noul" in a else a.get("choice")


def parts(raw: dict, roles: list[str] | None = None) -> dict:
    """Code decides the parts and the score from Jev's answers."""
    context = raw["context_spot"] == "first_words"
    lean = raw["lean"] != "none" and (raw["leans_in"] or 0) >= YES
    snap = (raw["snapback"] or 0) >= YES
    channels = [c for c, ok in (("said", context),
                                ("written", (raw.get("text_context") or 0) >= YES),
                                ("shown", (raw.get("visual_context") or 0) >= YES)) if ok]
    value_first = None
    if roles:
        cta_at = next((i for i, r in enumerate(roles) if r == "cta"), len(roles))
        value_first = any(r in ("payoff", "method", "proof") for r in roles[:cta_at])
    return {**raw, "context": context, "lean_in": lean, "snapback_turn": snap,
            "score": int(context) + int(lean) + int(snap), "channels": channels,
            "close": raw["keyword_ask"] == "topic_keyword" and value_first is not False,
            "value_before_ask": value_first}


def read_hook(sents: list[str], key: str, on_screen_text: str = "", first_jpg: bytes | None = None,
              roles: list[str] | None = None, transport: jev.Transport | None = None) -> dict:
    """All or nothing: raises if any answer is missing."""
    if not sents:
        raise jev.JevError("empty script")
    call = transport or jev.http_call
    with ThreadPoolExecutor(max_workers=2) as ex:
        tf = ex.submit(call, text_payload(sents, on_screen_text), key)
        imf = ex.submit(call, image_payload(first_jpg, sents[0]), key) if first_jpg else None
        tb = tf.result()
        ib = imf.result() if imf else None
    raw = {q: _ans(tb, q) for q in HOOK_Q if q != "text_context"}
    raw["text_context"] = _ans(tb, "text_context", required=bool(on_screen_text.strip()))
    raw["visual_context"] = _ans(ib, "visual_context") if ib is not None else None
    out = parts(raw, roles)
    out["tokens"] = jev.tokens_of(tb) + (jev.tokens_of(ib) if ib else 0)
    return out


def judge(h: dict) -> list[str]:
    """Gate failures for a script's hook (used by `gate read`)."""
    fails = []
    if not h["context"]:
        fails.append(f"triple hook: the topic is not clear in the first words (Jev: {h['context_spot'].replace('_', ' ')}); "
                     "say what the video is about immediately")
    if not h["lean_in"]:
        fails.append("triple hook: no lean; add proof or a stat, a pain point, a benefit, or something unexpected "
                     "that makes the viewer want more")
    if not h["snapback_turn"]:
        fails.append("triple hook: no snapback; after the lean, turn the viewer another way "
                     "(the obvious answer is wrong, the catch, 'but here's the problem')")
    return fails


def first_still(st: Store, sc: str) -> bytes | None:
    hits = sorted((st.frames / "stills").glob(f"{sc}_000.30.jpg")) if (st.frames / "stills").exists() else []
    return hits[0].read_bytes() if hits else None


def hook_one(st: Store, post: dict, key: str, transport=None) -> int:
    script = post.get("script") or []
    sents = [s["text"] for s in script]
    try:
        h = read_hook(sents, key, ((post.get("vis") or {}).get("hook_text") or ""),
                      first_still(st, post["shortcode"]), [s["role"] for s in script], transport)
    except Exception as exc:  # noqa: BLE001 - recorded on the row
        post.pop("hook", None)
        post["hook_error"] = str(exc)[:160]
        return 0
    used = h.pop("tokens")
    post["hook"] = h
    post.pop("hook_error", None)
    return used


def cmd_hooks(st: Store, per_account: int, force: bool = False, workers: int = 6, transport=None) -> int:
    key = jev.api_key()
    if not key and transport is None:
        print("[hooks] set TYPESAFE_API_KEY (your TypeSafe key) first", file=sys.stderr)
        return 2
    tokens = errs = done = 0
    for path in st.files():
        payload = store.load(path)
        handle = store.handle_of(payload, path)
        jobs = [p for p in store.selected(payload, per_account)
                if p.get("script") and (force or not p.get("hook"))]
        print(f"[hooks] @{handle}: {len(jobs)} scripts to score", flush=True)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for post, used in zip(jobs, ex.map(lambda p: hook_one(st, p, key, transport), jobs)):
                tokens += used
                done += 1
                errs += "hook_error" in post
        store.save(path, payload)
    cost = jev.cost_usd(tokens)
    st.data.mkdir(parents=True, exist_ok=True)
    with (st.data / "decode_runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"finished_at": datetime.now(timezone.utc).isoformat(), "stage": "hooks",
                             "model": jev.MODEL, "videos": done, "input_tokens": tokens, "cost_usd": cost,
                             "errors": errs}) + "\n")
    print(f"[hooks] {done} scripts, {tokens:,} input tokens = ${cost:.4f}, {errs} errors")
    return 0


__all__ = ["cmd_hooks", "judge", "parts", "read_hook"]
