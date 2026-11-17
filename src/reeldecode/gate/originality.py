"""Originality: a brief inspired by someone else's video must not be a rewrite of it.

A brief lists the reference videos it learned from under ``inspired_by`` (their shortcodes). The gate
compares the brief's spoken script with each reference transcript: it fails when too many of the brief's
five-word runs also appear in the reference, or when any run of eight or more words is shared. It
fails closed: a listed reference with no transcript cannot be checked, so the brief does not pass.
"""
from __future__ import annotations

import re

from ..config import Config
from ..store import Store
from . import formula

MAX_SHARED_SHARE = 0.15    # share of the brief's 5-word runs found in a reference
MAX_RUN = 8                # longest word run allowed to match a reference verbatim
GRAM = 5


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _grams(ws: list[str], n: int) -> set[tuple]:
    return {tuple(ws[i:i + n]) for i in range(len(ws) - n + 1)}


def longest_shared_run(a: list[str], b: list[str]) -> int:
    best, prev = 0, [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def compare(script: str, reference: str) -> dict:
    s, r = words(script), words(reference)
    g = _grams(s, GRAM)
    share = len(g & _grams(r, GRAM)) / len(g) if g else 0.0
    return {"shared_share": round(share, 3), "longest_run": longest_shared_run(s, r)}


def checks(d: dict, cfg: Config, store: Store | None = None) -> list[str]:
    refs = d.get("inspired_by") or []
    if not refs:
        return []
    script, _src = formula.spoken_text(d)
    if not script:
        return ["inspired_by is set but the brief has no spoken script to check"]
    st = store or Store(cfg)
    fails = []
    for sc in refs:
        doc = st.transcript(str(sc))
        if not doc or not doc.get("text"):
            fails.append(f"cannot verify originality against {sc}: no transcript (run fetch and transcribe)")
            continue
        c = compare(script, doc["text"])
        if c["shared_share"] > MAX_SHARED_SHARE:
            fails.append(f"too close to {sc}: {round(c['shared_share'] * 100)}% of its word runs are in your script "
                         f"(limit {round(MAX_SHARED_SHARE * 100)}%)")
        if c["longest_run"] >= MAX_RUN:
            fails.append(f"copied wording from {sc}: {c['longest_run']} words in a row (limit {MAX_RUN - 1})")
    return fails
