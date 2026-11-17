# The triple hook

A hook has three jobs, in order, and an ending has one:

1. **Context.** The first words tell the viewer what the video is about. Viewers only stay for a
   topic they care about, and putting the topic even at the back half of the first sentence costs
   viewers. Set it in as many places as possible: **said** (audio), **written** (on-screen text),
   **shown** (the first frame).
2. **Lean.** Something makes the viewer curious in that topic's direction: proof or a stat that
   backs up what is coming, a specific pain point, a benefit they want, or something unexpected.
   Read the first one or two sentences on their own: is the topic clear, and do you want more?
3. **Snapback.** A later sentence in the opening yanks the viewer another way: the obvious answer
   is wrong, the catch, "but here's the problem". Hook in one direction, pull the line in another.
4. **Topic-word ask.** At the end, ask for a comment word tied to the topic ("comment HOOK"), after
   the video has delivered its value.

## Score your videos and the creators you study

```bash
reeldecode anatomy     # the script, sentence by sentence (needed first)
reeldecode frames      # optional: lets the hook check the first frame ("shown")
reeldecode hooks       # Jev scores every opening
reeldecode formats     # does a higher score actually beat the creator's typical video?
```

`hooks` sends Jev one text request per video (the first four sentences as `opening`, the last three
as `ending`, and the on-screen text from `visual` when present) and, when `frames` kept the first
still, one image request asking whether the frame alone shows the topic. Questions:
`src/reeldecode/questions.py` (`HOOK_Q`, `VISUAL_CONTEXT_Q`). About 1,100 tokens a video without
the image, 3,000 with it: well under a tenth of a cent.

Code, not the model, decides the parts:

| part | passes when |
|---|---|
| context | Jev places the topic in the first half of sentence 1 (`context_spot: first_words`) |
| lean | `lean` is not `none` and `leans_in` is at least 0.5 |
| snapback | `snapback` is at least 0.5 |
| score | context + lean + snapback, 0 to 3 |
| channels | said / written / shown, each where the context is set |
| close | the ask is a topic word (`keyword_ask: topic_keyword`) and payoff, method or proof comes before it |

Checked live: a "hey guys, welcome back" opening scored 0; a written-to-spec opening ("Most traders
think a 70% win rate means they're profitable. We pulled 4,000 trades... But the traders with the
highest win rates lost the most money.") scored 3; the opening of the video this method comes
from scored 2, because its snapback arrives later than its first four sentences.

## Does it work? Let your data say

`formats` groups every creator's videos by triple hook score, lean type, snapback, context channels
and ask, and gives each group's median **times typical** (views over that creator's same-year
median). If 3-of-3 videos beat typical across most creators, the method holds for your niche; if
not, it is a claim to test with trials, not a rule.

## The gate

`reeldecode gate read` also scores the brief's script on the triple hook, and `gate check` blocks a
script missing context, lean or snapback. Put on-screen text in the brief as `on_screen_text:` so
the written channel is counted. Turn it off per project with `triple_hook = false` under
`[formula]`, or use `formula_exception:` on one brief that tests another shape.

The topic-word ask is reported, not enforced: the funnel stage decides which asks a post may use
(see the brief template).
