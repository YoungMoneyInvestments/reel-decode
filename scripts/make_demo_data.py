#!/usr/bin/env python3
"""Generate the bundled SYNTHETIC demo dataset (src/reeldecode/demo_data/).

Every account, script, caption and number here is made up. The accounts do not exist; the
links point at example.com. Effects are planted on purpose so the demo page has something to
show (e.g. on @demo_creator a question or number opener and an early proof sentence win), and a
different account rewards a different shape, as real accounts do.

    python scripts/make_demo_data.py
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "src" / "reeldecode" / "demo_data"

ACCOUNTS = {
    "demo_creator": {
        "topic": "cooking", "n": 48, "base": 2400,
        # planted effects (multipliers on views)
        "fx": {"opener": {"question": 1.9, "specific_number": 2.2, "callout": 0.6, "statement": 0.8},
               "proof_early": 1.8, "neutral": 0.55, "method_heavy": 0.4, "playful": 1.5},
    },
    "demo_fitcoach": {
        "topic": "fitness", "n": 44, "base": 18000,
        "fx": {"opener": {"question": 1.6, "specific_number": 1.3, "callout": 0.55, "statement": 0.9},
               "proof_early": 1.3, "neutral": 1.0, "method_heavy": 1.6, "playful": 1.0},
    },
    "demo_studyhacks": {
        "topic": "study", "n": 40, "base": 41000,
        "fx": {"opener": {"question": 1.5, "specific_number": 1.4, "callout": 0.8, "statement": 0.85},
               "proof_early": 1.2, "neutral": 1.25, "method_heavy": 1.7, "playful": 0.9},
    },
}

BANK = {
    "cooking": {
        "question": ["Why does restaurant rice never stick?", "Ever wonder why your garlic turns bitter?",
                     "What if your pan is the problem?", "Why do chefs salt pasta water so much?",
                     "Is your onion really caramelized?", "Why is homemade pizza always soggy?"],
        "specific_number": ["3 minutes is all a perfect egg needs.", "Two ingredients fixed my weeknight sauce.",
                            "I cooked 40 steaks to find this.", "1 tablespoon of cornstarch changes stir fry.",
                            "$4 of beans fed us for three days."],
        "callout": ["If you burn garlic every time, listen.", "Most home cooks skip this step.",
                    "Stop rinsing your pasta right now."],
        "statement": ["This is how I make dinner on a Tuesday.", "Today we are making a simple soup.",
                      "Here is my favorite way to cook chicken thighs at home."],
        "proof": ["I tested it on 12 batches and every one came out crisp.", "My neighbor, a line cook for ten years, does the same.",
                  "The thermometer read 74 degrees, right on target.", "It cut my prep time from 30 minutes to 11."],
        "setup": ["Most recipes skip this part.", "Here is the situation in my kitchen.", "It all started with a sticky pan.",
                  "The problem is heat, not the recipe."],
        "method": ["Heat the pan before the oil goes in.", "Salt the water until it tastes like the sea.",
                   "Let the meat rest for five minutes.", "Add the garlic in the last minute only.",
                   "Toss the rice with a little oil first.", "Keep the lid off so steam can escape."],
        "payoff": ["That is the whole secret.", "Your dinner tastes like a restaurant now.", "And it is ready in ten minutes."],
        "cta": ["Save this for your next grocery run.", "Send this to the friend who burns everything.",
                "Comment PAN and I will send the full recipe.", "Follow for one fix a day."],
        "filler": ["Okay, let's go.", "So yeah."],
    },
    "fitness": {
        "question": ["Why are your legs still sore after three days?", "Is cardio killing your gains?",
                     "What do strong people do on rest days?", "Why does your back hurt after deadlifts?"],
        "specific_number": ["10 minutes a day built my pull up.", "I walked 8,000 steps for 30 days.",
                            "Three sets is enough for most people.", "Two changes fixed my squat depth."],
        "callout": ["If you skip warm ups, watch this.", "Most people breathe wrong when they lift.",
                    "Stop doing crunches for abs."],
        "statement": ["Here is my full upper body day.", "Today I want to talk about recovery."],
        "proof": ["My squat went from 60 to 100 kilos in a year.", "A sports physio showed me this.",
                  "I tracked it for 12 weeks and the numbers moved."],
        "setup": ["Here is what usually happens.", "A lot of people start strong and stall.", "This used to happen to me."],
        "method": ["Brace your core before you lift.", "Push your knees out over your toes.", "Rest two minutes between sets.",
                   "Add one rep each week.", "Keep the bar close to your shins.", "Slow down the lowering phase."],
        "payoff": ["That is how you keep progressing.", "Your joints will thank you.", "Simple, and it works."],
        "cta": ["Save this for leg day.", "Send it to your gym partner.", "Follow for the next part."],
        "filler": ["Alright.", "Let's get into it."],
    },
    "study": {
        "question": ["Why do you forget everything you read?", "What if highlighting is wasting your time?",
                     "How do top students revise in half the time?", "Why does cramming feel like it works?"],
        "specific_number": ["25 minutes changed how I study.", "I read 52 books with this one rule.",
                            "Three questions after every chapter.", "One page of notes per lecture."],
        "callout": ["If you reread your notes, stop.", "Most students revise the wrong way."],
        "statement": ["This is my study routine.", "Let me explain spaced repetition."],
        "proof": ["My grades went from a C to an A in one term.", "A memory researcher calls it the testing effect.",
                  "I tracked my recall for 6 weeks."],
        "setup": ["Here is the usual pattern.", "We all do this before exams.", "It feels productive, but it is not."],
        "method": ["Close the book and write what you remember.", "Quiz yourself before you reread.",
                   "Space each review a few days apart.", "Teach the idea to an empty chair.",
                   "Turn every heading into a question.", "Mix topics instead of blocking them."],
        "payoff": ["That is how memory actually sticks.", "You will remember it on exam day.", "Less time, better grades."],
        "cta": ["Save this before your next exam.", "Send it to your study group.", "Follow for one method a week."],
        "filler": ["So.", "Okay."],
    },
}

FORMATS = ["how_to_steps", "concept_explainer", "myth_buster", "personal_story", "result_reveal", "tool_demo"]
REGISTERS = ["neutral_info", "playful", "hype", "calm", "provocative"]
PAYOFFS = ["practical_tip", "information", "mindset_shift", "entertainment"]
CTA_OF = {"Save": "save", "Send": "send_to_friend", "Comment": "comment_keyword", "Follow": "follow"}


def make_reel(rng: random.Random, handle: str, spec: dict, i: int, when: datetime) -> dict:
    bank = BANK[spec["topic"]]
    fx = spec["fx"]
    sc = f"demo-{handle.split('_')[1][:4]}-{i:03d}"
    post = {"shortcode": sc, "url": f"https://example.com/demo/{handle}/{sc}",
            "posted_at": when.isoformat(), "media_type": "VIDEO", "views_source": "synthetic"}
    mult = math.exp(rng.gauss(0, 0.45))
    if rng.random() < 0.12:     # music-only / text-only video: nothing to decode
        post.update({"script_status": "no_speech", "caption": "No talking, just the process. #demo",
                     "views": int(spec["base"] * mult), "likes": int(spec["base"] * mult * 0.05),
                     "comments": rng.randint(2, 40)})
        return post
    opener = rng.choice(["question", "specific_number", "callout", "statement", "question", "statement"])
    proof_early = rng.random() < 0.45
    register = rng.choice(REGISTERS)
    method_n = rng.choice([1, 2, 3, 4])
    has_cta = rng.random() < 0.7
    sents: list[tuple[str, str]] = [("hook", rng.choice(bank[opener]))]
    if proof_early:
        sents.append(("proof", rng.choice(bank["proof"])))
    sents.append(("setup", rng.choice(bank["setup"])))
    if rng.random() < 0.3:
        sents.append(("filler", rng.choice(bank["filler"])))
    sents += [("method", m) for m in rng.sample(bank["method"], method_n)]
    if not proof_early and rng.random() < 0.4:
        sents.append(("proof", rng.choice(bank["proof"])))
    sents.append(("payoff", rng.choice(bank["payoff"])))
    cta_line = rng.choice(bank["cta"]) if has_cta else None
    if cta_line:
        sents.append(("cta", cta_line))
    method_heavy = method_n / len(sents) > 0.34
    mult *= fx["opener"].get(opener, 1.0)
    mult *= fx["proof_early"] if proof_early else 1.0
    mult *= fx["neutral"] if register == "neutral_info" else 1.0
    mult *= fx["playful"] if register == "playful" else 1.0
    mult *= fx["method_heavy"] if method_heavy else 1.0
    t, script = 0.0, []
    for role, text in sents:
        script.append({"t": round(t, 2), "text": text, "role": role})
        t += 0.38 * len(text.split()) + rng.uniform(0.1, 0.5)
    views = int(spec["base"] * mult)
    fmt = "how_to_steps" if method_n >= 3 else rng.choice(FORMATS)
    post.update({
        "views": views, "likes": int(views * rng.uniform(0.02, 0.08)), "comments": int(views * rng.uniform(0.001, 0.01)),
        "caption": f"{sents[0][1]} #demo #{spec['topic']}", "duration": round(t + 1.5, 1),
        "script_status": "decoded", "script": script, "spoken_seconds": round(t, 1),
        "spoken_words": sum(len(s.split()) for _, s in sents),
        "d_talking": 0.98, "d_format": fmt, "d_hook_formula": opener, "d_register": register,
        "d_viewer_payoff": "practical_tip" if method_n >= 2 else rng.choice(PAYOFFS),
        "d_cta_type": next((v for k, v in CTA_OF.items() if cta_line and cta_line.startswith(k)), "none"),
        "d_open_loop": round(0.8 if opener in ("question", "curiosity_gap") else rng.uniform(0.05, 0.5), 2),
        "d_viewer_addressed": round(0.85 if opener in ("callout", "question") else rng.uniform(0.05, 0.6), 2),
        "d_concrete_detail": round(0.9 if proof_early or opener == "specific_number" else rng.uniform(0.1, 0.6), 2),
        "d_proof_shown": round(0.9 if any(r == "proof" for r, _ in sents) else 0.1, 2),
        "d_single_idea": round(rng.uniform(0.5, 0.95), 2),
        "d_self_promo": round(rng.uniform(0.02, 0.2), 2),
    })
    return post


def main() -> None:
    rng = random.Random(20261116)
    OUT.mkdir(parents=True, exist_ok=True)
    start = datetime(2025, 1, 6, 17, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 20, 17, 0, tzinfo=timezone.utc)
    total = 0
    for handle, spec in ACCOUNTS.items():
        step = (end - start) / spec["n"]
        posts = [make_reel(rng, handle, spec, i, start + step * i + timedelta(hours=rng.randint(0, 30)))
                 for i in range(spec["n"])]
        posts.sort(key=lambda p: p["posted_at"], reverse=True)
        payload = {"handle": handle, "synthetic": True,
                   "note": "Synthetic demo data generated by scripts/make_demo_data.py. Not a real account.",
                   "posts": posts}
        (OUT / f"reference_{handle}.json").write_text(json.dumps(payload, indent=1))
        total += sum(len(p.get("script") or []) + 1 for p in posts if p.get("script"))
    # what decoding this many sentences would cost at ~800 input tokens per call (an estimate)
    tokens = total * 800
    (OUT / "decode_runs.jsonl").write_text(json.dumps({
        "finished_at": "2026-11-01T00:00:00+00:00", "model": "jev-1.13.0", "synthetic": True,
        "input_tokens": tokens, "cost_usd": round(tokens / 1e6 * 0.042, 4), "errors": 0}) + "\n")
    print(f"wrote {OUT}: {total} calls' worth of synthetic labels")


if __name__ == "__main__":
    main()
