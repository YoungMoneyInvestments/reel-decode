# The test-and-learn loop

The decode tells you what your past winners had in common. The loop turns that into the next video and checks whether it worked:

**brief → script check → render versions → trial posts a week apart → read at 72 h → winner to the feed → log → repeat.**

## 1. Brief first

Every video starts as a brief: `reeldecode gate new E014 "title" --variable hook --stage tofu --account your_handle`. The brief answers, before any production:

| Field | Question |
|---|---|
| `funnel.stage` | Which one job does this video do? (below) |
| `funnel.audience` | Which one viewer is it for? A situation, not a demographic. |
| `funnel.goal` | The one thing they should feel or do afterwards |
| `topic` | The one idea, in one sentence of 20 words or fewer. Two ideas are two videos. |
| `viewer_takeaway` | What a stranger can use today. It must still make sense with your name removed. |
| `send_to` | Who a viewer would forward it to |
| `hook_variants` | Three different first lines to test |
| `proof` | The source of every number or claim on screen |
| `spoken_script` | Every spoken word, in order (what the formula reads) |

If a field cannot be filled honestly, the idea is not ready. Change the idea; do not pad the field.

### Funnel stage decides the video

| | Top (`tofu`) | Middle (`mofu`) | Bottom (`bofu`) |
|---|---|---|---|
| Viewer | A stranger | Someone who has seen you before | Someone deciding whether to act |
| Job | Earn the watch and the send | Earn trust: show how it works | Make the ask easy |
| Your name | Not in the hook | Present, after the value | Leads |
| Ends on | A question, follow, send or save | The same, or a comment keyword | Comment keyword, link in bio or DM |
| Judged by | Reach to non-followers, watch time, sends | Saves, comments, follows | Keyword comments, clicks, sign-ups |

A starting mix of six top, three middle and one bottom per ten videos works for most accounts; `reeldecode gate mix` shows yours. A stranger is never sent to a link.

### Not selfish

Delete your name and the call to action from the script. Is a stranger still better off? Can you name the person they would send it to? If either answer is no, the video is about you, not the viewer. The gate catches the obvious cases (brand names or sales asks in a top-of-funnel hook or in the takeaway; add your names under `[formula] brand_terms`).

## 2. Script check

Write ten hooks and keep the three that pass all five:

1. **Mirror the viewer**, inside a question or a number, not as a call-out statement.
2. **Half-guessable.** Curiosity peaks when the viewer is about half sure where it goes.
3. **One surprise.** One unexpected detail; everything else plain.
4. **Exact numbers.** 11 reads as counted, 10 as a guess. Never invent a figure.
5. **One breath.** Say it aloud at normal speed without running out of air.

Then `reeldecode gate read E014` (Jev labels the script; about a hundredth of a cent) and `reeldecode gate check E014`, which exits 1 until the rubric, the brief and the formula all pass. Change the script and the stored read no longer matches its hash, so the gate asks for a new read.

## 3. Render versions

For anything that is not time-sensitive, make **two to four versions that are different videos**, not one body with three hooks pasted on: change sentence order, length, layout, voice or footage, so no two share much more than a third of their timeline. Platforms detect near-duplicates and limit their reach. Type the hook with the platform's own text tool at posting time, new wording per version.

## 4. Trial posts, a week apart

Post the versions as trial posts shown to non-followers (Instagram's Trial Reels, or the equivalent where you post), about a week apart. Never post several versions of one video on the same day. Time-sensitive videos set `time_sensitive: true` and post once.

Record each version's link on the brief: `url: "a https://... | b https://... | c https://..."`.

## 5. Read at 72 hours

`reeldecode learn pull` reads your own posts at 24 h, 72 h and 7 days (or type numbers in with `reeldecode learn log`). `reeldecode learn report` picks the winner once every version is at least 72 hours old:

1. best **hold through the first 3 seconds**, if the leader beats the runner-up by 20% or more;
2. otherwise best **average watch percentage**;
3. otherwise most **sends plus saves per 1,000 views**.

The 72-hour window and the order of measures are reasonable defaults, not platform facts. Change them if your data says otherwise.

## 6. Winner to the feed

Only the winner goes to your main feed, as its own new post (not by making the trial public), and to the other platforms. The losing versions stay unshared.

## 7. Read the curve, then repeat

Where retention curves are available (`learn pull` names YouTube curves automatically):

| Curve | Meaning | Next video |
|---|---|---|
| Cliff in the first 3 seconds, then flat | The hook failed | New hook; the body may be fine |
| Steady slide through the middle | The value failed | Sharper topic, a usable step, a story |
| One sudden step down, then normal | One bad moment | Cut or fix that moment |
| Holds, then drops near the end | Too long, or the ask came early | Shorter; move the ask last |
| Moderate early drop, long shallow slope | Good video | Reuse its pacing |

Compare a video only with its control at the same hour mark, and judge a format over ten posts, not one. Read `LEARNINGS.md` before writing the next batch of briefs, and update your formula when your own results disagree with it.

## Running the loop on a schedule

`reeldecode learn pull` only reads, and it fails loud (exit 1) when a profile is signed out or a panel is empty, so it is safe to run unattended. See [`examples/schedule/`](../examples/schedule/) for a cron line, a macOS launchd job and a wrapper script that pulls, rewrites `LEARNINGS.md` and optionally commits the changed briefs.
