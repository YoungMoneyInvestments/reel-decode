"""TypeSafe Jev client: typed questions in, labels and probabilities out.

Jev is a "System One" model: it answers closed questions (pick one label, or yes/no as a
probability) about a JSON state. One HTTPS call per question set. The key comes from the
TYPESAFE_API_KEY environment variable and is never printed or written anywhere.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .questions import REEL_Q, ROLE_Q

ENDPOINT = os.environ.get("TYPESAFE_ENDPOINT", "https://api.typesafe.ai/v1/systemone")
MODEL = os.environ.get("TYPESAFE_MODEL", "jev-1.13.0")
PRICE_PER_M_INPUT_USD = 0.042   # published input price at the time of writing; check yours
MAX_SENTENCES = 45

Transport = Callable[[dict, str], dict]


class JevError(RuntimeError):
    pass


def api_key() -> str:
    return (os.environ.get("TYPESAFE_API_KEY") or "").strip()


def http_call(payload: dict, key: str, attempts: int = 3) -> dict:
    import requests

    last: Exception | None = None
    for a in range(attempts):
        try:
            headers = {"Authorization": "Bearer " + key}
            if payload.get("assets"):                     # images are opt-in per request
                headers["TypeSafe-Danger-Zone-Images"] = "true"
            r = requests.post(ENDPOINT, headers=headers, json=payload, timeout=(5, 60))
            if r.status_code == 429 or r.status_code >= 500:
                raise JevError(f"HTTP {r.status_code}")
            if r.status_code != 200:
                raise JevError(f"HTTP {r.status_code}: {r.text[:160]}")
            return r.json()
        except Exception as exc:  # noqa: BLE001 - bounded retry, then surfaced to the caller
            last = exc
            time.sleep(1.5 * (a + 1))
    raise JevError(f"jev call failed: {last}")


def position_word(i: int, n: int) -> str:
    if i == 0:
        return "first sentence"
    if i == n - 1:
        return "last sentence"
    f = i / max(n - 1, 1)
    return "early" if f < 0.34 else ("middle" if f < 0.67 else "late")


def reel_payload(account: str, sents: list[str], caption: str = "") -> dict:
    state = {"account": account, "first_sentence": sents[0], "script": " ".join(sents)[:6000],
             "caption": (caption or "")[:600]}
    return {"model": MODEL, "questions": REEL_Q, "state": state}


def sentence_payload(sents: list[str], i: int) -> dict:
    state = {"position": position_word(i, len(sents)),
             "previous_sentence": sents[i - 1] if i else "", "sentence": sents[i],
             "next_sentence": sents[i + 1] if i + 1 < len(sents) else ""}
    return {"model": MODEL, "questions": {"role": ROLE_Q}, "state": state}


def tokens_of(body: dict) -> int:
    return int((body.get("usage") or {}).get("input_tokens") or 0)


def reel_answers(body: dict) -> dict:
    """{question: label or probability} from one reel call; raises if any answer is missing."""
    ans = body.get("answers") or {}
    out = {}
    for qk in REEL_Q:
        a = ans.get(qk)
        if not isinstance(a, dict):
            raise JevError(f"no answer for {qk}")
        out[qk] = a.get("noul") if (a.get("type") == "noul" or "noul" in a) else a.get("choice")
        if "confidence" in a and "noul" not in a:
            out[qk + "_conf"] = a.get("confidence")
    return out


def read_script(account: str, sents: list[str], key: str, caption: str = "",
                transport: Transport | None = None, workers: int = 8) -> dict:
    """Label one script: one reel call plus one call per sentence. All or nothing.

    Returns {"reel": {...}, "roles": [...], "tokens": int}."""
    call = transport or http_call
    sents = sents[:MAX_SENTENCES]
    if not sents:
        raise JevError("empty script")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rf = ex.submit(call, reel_payload(account, sents, caption), key)
        sf = [ex.submit(call, sentence_payload(sents, i), key) for i in range(len(sents))]
        bodies = [rf.result()] + [f.result() for f in sf]   # any failure raises: no partial record
    roles = [((b.get("answers") or {}).get("role") or {}).get("choice") for b in bodies[1:]]
    if any(r is None for r in roles):
        raise JevError("Jev returned no role for a sentence")
    return {"reel": reel_answers(bodies[0]), "roles": [str(r) for r in roles],
            "tokens": sum(tokens_of(b) for b in bodies)}


def cost_usd(tokens: int) -> float:
    return round(tokens / 1_000_000 * PRICE_PER_M_INPUT_USD, 5)
