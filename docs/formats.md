# Formats: what wins, from frames and words

Two questions this answers about any creator you study, and about yourself:

1. **Which formats beat this creator's typical video?** Talking head vs screen recording vs interview,
   explainer vs story vs how-to, question hooks vs contrarian hooks.
2. **Which of those hold up across creators,** so it is a pattern and not one account's quirk?

## The run

```bash
reeldecode collect --from-csv creator.csv --handle some_creator   # urls + real view counts
reeldecode fetch && reeldecode transcribe && reeldecode anatomy   # the words (Jev on the script)
reeldecode frames                                                 # the pictures (Jev on stills)
reeldecode formats                                                # -> data/FORMATS.md, data/formats.json
```

`reeldecode formats --demo` runs offline on the bundled synthetic data (script groupings only; the
demo has no frames).

## What Jev is asked about the pictures

`frames` pulls six stills per video with ffmpeg: 0.3 s, 1.5 s and 3 s (the opening a viewer decides
on) and 25%, 50% and 75% of the running time (the body). Each still is sent to Jev as an image with
closed questions. The wording lives in `src/reeldecode/questions.py`:

| question | asked of | answers |
|---|---|---|
| `shot` | every still | talking_head, talking_head_with_graphics, person_over_screen, screen_recording, interview, b_roll, product_shot, text_card, clip_from_elsewhere, split_screen, other |
| `caption` | every still | probability there is on-screen text of three or more words |
| `hook_visual` | the first still | headline_text, face_closeup, proof_on_screen, product_or_tool, action, unexpected_image, scene_or_aesthetic, other |

Code then decides, per video:

- **visual format**: the shot type on at least half the stills, else `mixed`
- **opening shot**: the shot at 0.3 s
- **shot sequence**: the shots in order with repeats collapsed (`talking_head > screen_recording > talking_head`)
- **caption share**: the share of stills carrying a caption

A video is all or nothing: if any still fails, nothing is stored for it and the error is kept on the
row (`frames_error`). Images are a preview feature at TypeSafe (sent with the
`TypeSafe-Danger-Zone-Images: true` header), so spot-check a few stills against their labels before
you trust a big run. The stills are kept in `.reeldecode-cache/frames/stills/` for exactly that.

## What the words add

From `anatomy`: the script **format**, the **spoken hook** (how the first sentence opens), and the
**opening sequence**, the first three sentence jobs with filler dropped and repeats collapsed
(`hook > setup > method`, `hook > story > payoff`). That is the sequencing: what the creator says
first, second and third.

## How "wins" is measured

Each video is scored by **times typical**: its views divided by the same creator's median for the
same year. 1.00x is that creator's normal video; 2.00x is double. Raw views are never compared
across creators, so a 20k-follower account and a 2M one count the same.

- **Per creator:** each value (and each pairing, such as `talking_head + concept_explainer`) with
  at least `--min-n` judged videos (default 3) is listed with its median, how many videos, how
  many were in the creator's top third, and the best example with a link.
- **Across creators:** your own accounts are left out. Each reference creator gets one vote per
  value: its median for that value. **Beats typical** counts the creators where that median is
  above 1.00x. A value that beats typical for 4 of 5 creators is a pattern; one that is 6x for a
  single creator on 3 videos is a lead to test.

## Reading it honestly

- Small groups swing. A 3-video group is a lead to test with a trial, not a rule.
- Times typical says what did well, not why. Topic, timing and luck are not controlled.
- Feed the leads into a brief (`reeldecode gate new ... --format <visual format>`), and let your own
  trials (`learn`) decide.

## Cost

Measured on 80 real Instagram videos from two creators: 897,040 input tokens, **$0.038**, about
two minutes, no errors. That is roughly 1,900 tokens a still and $0.0005 a video, so 1,000 videos
cost about 50 cents. Every run is logged to `decode_runs.jsonl` with `"stage": "frames"`.
