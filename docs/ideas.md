# From outliers to your next video

The loop: find what is working in your space, learn the structure, make something that is yours, test it, keep what wins. Where reel-decode sits in it:

| Step | Command | Status |
|---|---|---|
| List the videos of the creators you study, with real view counts | `collect`, `fetch` | you name the accounts (no automatic "find creators in my niche") |
| Find the ones that crushed their own normal numbers | `ideas` (uses the same-account, same-year median) | built |
| Break down why they worked | `transcribe`, `anatomy`, `visual`, `page` | built |
| Turn each into an idea of yours, not a copy | `ideas` cards, `gate new --lane`, you or an agent write the script | built; the writing is yours or your agent's |
| Check it is not a copy | `gate check` with `inspired_by` | built |
| Check it fits the account and funnel | `gate check`, `lanes` | built |
| Make the video | your editor ([editing.md](editing.md)) | not reel-decode's job |
| Test as trial reels and read the numbers | `learn pull`, `learn report` | built (posting is yours) |
| See where viewers left, study your winners, sharpen the next batch | `learn report` retention curves, `ideas --include-yours` | built |
| Decide what to promote | `learn report` lists posts over 100,000 organic views | flag only; reel-decode never spends money |

## `reeldecode ideas`

```bash
reeldecode ideas --min-x 3 --limit 20          # writes ideas.md and ideas.json next to your data
reeldecode ideas --include-yours               # your own best videos too: "study your winners"
```

An idea card is a video at least `--min-x` times its own account's median for the same year, with its **structure**: how it opens, its format and payoff, the order of jobs its sentences do (`HSMMMMY` = hook, setup, method x4, payoff), length, and whether proof comes early. The opener is shown as a reference, with a note not to reuse it.

## The copy check

List the reference shortcodes in the brief:

```yaml
inspired_by: [demo-fitc-036]
```

`gate check` compares your spoken script with each reference transcript and fails if more than 15% of your five-word runs appear in it, or if any run of eight or more words matches verbatim. If a listed reference has no transcript, the brief does not pass: it cannot be verified. Structure is borrowed freely; wording is not.

## Promotion candidates

`reeldecode learn report` adds a section listing posts past 100,000 organic views. That is a prompt to decide, not an action. Spend on promotion is your call, per post.

## Posting volume

Many versions a day is a posting-cadence question, not a decode question, and it has a trap: platforms flag near-duplicate versions of one video ("won't get much reach because it looks like something you shared before"). Make versions that are genuinely different videos (order, length, layout, voice, footage), not one body with different openers. `lanes` shows whether each account is hitting its weekly target.
