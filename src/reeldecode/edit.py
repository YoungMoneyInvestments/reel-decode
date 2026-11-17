"""edit-plan: one typed verdict per script line (keep / delete / move), for an editing tool to apply.

Each line goes to Jev with the whole script around it. Jev answers three closed questions, so there
is nothing to parse: a verdict, where a moved line should go, and a coded reason. reeldecode writes
the plan and a change list. It never touches your project: apply the plan with your editing tool
(for example an agent driving Premiere Pro through an MCP server), then render the result as a new
version next to the original.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import jev
from .questions import UNTRUSTED

VERDICT_Q = {
    "type": "choice",
    "instructions": ("`line` is ONE line from the spoken script of a short vertical video; `script` is the whole "
                     "script. Decide what the editor should do with THIS line. " + UNTRUSTED),
    "criteria": {
        "keep": "Does its job where it is: the video is worse without it or with it elsewhere.",
        "delete": "Repeats another line, rambles, hedges, or adds nothing the viewer needs.",
        "move": "Worth keeping but in the wrong place: it buries the point or answers a question not yet asked.",
    },
}
WHERE_Q = {
    "type": "choice",
    "instructions": "If this line were moved, where should it go in the script? " + UNTRUSTED,
    "criteria": {
        "stay": "Where it is.",
        "opening": "Becomes the first line.",
        "after_hook": "Right after the opening line.",
        "before_payoff": "Just before the takeaway.",
        "end": "The last line.",
    },
}
REASON_Q = {
    "type": "choice",
    "instructions": "Why does this line get the verdict it gets? " + UNTRUSTED,
    "criteria": {
        "does_its_job": "It is doing its job where it is.",
        "repeats": "Another line already says it.",
        "off_topic": "It is not about the one idea of the video.",
        "weak": "Hedging, filler or throat-clearing.",
        "buries_the_point": "The strongest thing is later than it should be.",
        "answers_too_early": "It answers something the script has not yet raised.",
    },
}
QUESTIONS = {"verdict": VERDICT_Q, "where": WHERE_Q, "reason": REASON_Q}


def payload(lines: list[str], i: int) -> dict:
    return {"model": jev.MODEL, "questions": QUESTIONS,
            "state": {"line": lines[i], "position": jev.position_word(i, len(lines)), "script": " ".join(lines)[:6000]}}


def plan_line(body: dict) -> dict:
    a = body.get("answers") or {}
    out = {}
    for k in QUESTIONS:
        if not isinstance(a.get(k), dict) or a[k].get("choice") is None:
            raise jev.JevError(f"no answer for {k}")
        out[k] = str(a[k]["choice"])
    if out["verdict"] != "move":
        out["where"] = "stay"
    elif out["where"] == "stay":
        out["verdict"] = "keep"       # a move that goes nowhere is a keep; do not ask the editor to act on it
    return out


def make_plan(lines: list[str], key: str, transport=None, workers: int = 8) -> list[dict]:
    """All or nothing: one failed line raises and no plan is written."""
    call = transport or jev.http_call
    lines = lines[: jev.MAX_SENTENCES]
    if not lines:
        raise jev.JevError("empty script")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        bodies = [f.result() for f in [ex.submit(call, payload(lines, i), key) for i in range(len(lines))]]
    plan = [{"n": i + 1, "line": ln, **plan_line(b)} for i, (ln, b) in enumerate(zip(lines, bodies))]
    return reconcile(plan)


BAD_REASONS = {"repeats", "off_topic", "weak"}


def _norm(t: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in t).split())


def reconcile(plan: list[dict]) -> list[dict]:
    """Fix what judging lines one at a time gets wrong.

    A line repeated word for word is judged "repeats" every time it appears, so every copy would be
    deleted and the idea lost: the first copy is restored. A line kept for a reason that says it
    should go (repeats, off topic, weak) is flagged for a human instead of silently applied."""
    first: dict[str, dict] = {}
    for p in plan:
        k = _norm(p["line"])
        first.setdefault(k, p)
    for k, p0 in first.items():
        group = [p for p in plan if _norm(p["line"]) == k]
        if len(group) > 1 and all(p["verdict"] == "delete" for p in group):
            p0["verdict"], p0["where"], p0["reason"] = "keep", "stay", "does_its_job"
    for p in plan:
        if p["verdict"] == "keep" and p["reason"] in BAD_REASONS:
            p["flag"] = f"kept, but the reason is '{p['reason']}': check by hand"
    return plan


def apply_order(plan: list[dict]) -> list[dict]:
    """The new line order: deletes dropped, moved lines placed where they asked to go."""
    kept = [p for p in plan if p["verdict"] != "delete"]
    stay = [p for p in kept if p["verdict"] == "keep"]
    out = list(stay)
    for p in (q for q in kept if q["verdict"] == "move"):
        w = p["where"]
        if w == "opening":
            out.insert(0, p)
        elif w == "after_hook":
            out.insert(min(1, len(out)), p)
        elif w == "end":
            out.append(p)
        else:  # before_payoff: before the last line, which is the takeaway or the ask
            out.insert(max(len(out) - 1, 0), p)
    return out


def change_list(plan: list[dict]) -> str:
    rows = ["# Edit plan", "", "| # | Verdict | Where | Reason | Line |", "|---|---|---|---|---|"]
    rows += [f"| {p['n']} | {p['verdict']} | {p['where']} | {p['reason']} | {p['line']} |" for p in plan]
    flags = [f"- line {p['n']}: {p['flag']}" for p in plan if p.get("flag")]
    if flags:
        rows += ["", "## Check by hand", ""] + flags
    new = apply_order(plan)
    rows += ["", f"Kept {sum(p['verdict'] == 'keep' for p in plan)}, moved {sum(p['verdict'] == 'move' for p in plan)}, "
             f"deleted {sum(p['verdict'] == 'delete' for p in plan)} of {len(plan)} lines.", "",
             "## New order", ""] + [f"{k}. (was {p['n']}) {p['line']}" for k, p in enumerate(new, 1)]
    return "\n".join(rows) + "\n"


def cmd_edit_plan(script: Path, out: Path, key: str, transport=None) -> int:
    if not key and transport is None:
        print("[edit-plan] TYPESAFE_API_KEY is not set", flush=True)
        return 2
    lines = [ln.strip() for ln in script.read_text(encoding="utf-8").splitlines() if ln.strip()]
    plan = make_plan(lines, key, transport)
    out.mkdir(parents=True, exist_ok=True)
    (out / "edit-plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "edit-plan.md").write_text(change_list(plan), encoding="utf-8")
    print(f"[edit-plan] wrote {out}/edit-plan.json and edit-plan.md")
    return 0
