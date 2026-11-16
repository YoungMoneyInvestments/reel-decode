# The script formula

The formula is a short list of checks a script must pass before anyone films or renders it. You set it from your own decode page; reel-decode ships defaults that came out of the study this tool was built for, and makes every threshold a setting.

## Where the defaults came from

The tool was built to answer one question on a set of real accounts: what do this account's best videos do that its worst ones don't? About 500 videos from six accounts (four of one creator's own accounts, two larger accounts in the same niche used as references) were transcribed, labeled sentence by sentence, and split into top and bottom thirds inside each account. In summary:

- **A short first sentence won almost everywhere.** First sentence of 12 words or fewer: winners more often on three of four judged accounts (gaps of +12 to +32 points).
- **Questions and specific numbers were the best openers.** On the two reference accounts, videos that opened on a question ran about 1.5x their year median; on the largest of the creator's own accounts, a specific number opener ran about 2x. Call-outs ("If you...", "Most people...") were the worst opener on one reference account (about 0.55x) and flat statements sat below median on both of the creator's main accounts.
- **A proof sentence was the trait that travelled.** A sentence showing a result, a figure or a named source was more common in winners on three of four accounts (up to +38 points).
- **A neutral, informational read lost** on both of the creator's main accounts (−24 and −41 points), while it was neutral or positive on the teaching-led reference accounts.
- **Teaching-heavy scripts split by audience.** Over a third of sentences being "method" was +21 and +22 on the reference accounts and −21 and −22 on the creator's own. The same shape that lifted their reels sank the creator's: an audience built on other content did not want lessons.

Every line above is an association in one sample, not a proven cause. That is why the formula is a starting point you replace with your own decode, and why the gate has an exception field for deliberate tests.

## The checks

Run offline by `reeldecode gate check`:

| Check | Default | Setting |
|---|---|---|
| First spoken sentence length | 12 words or fewer | `[formula] first_max_words` |
| First sentence opens on a number or a question | digits, `$`, `%`, number words, or ends with `?` | (code: `NUMBER` in `gate/formula.py`) |
| Video length (per account) | off | `duration = [min, max]` on the account; `0` = no lower bound |
| A Jev read exists and matches the current script | required | the read stores a hash of the script |

Read by Jev during `reeldecode gate read` and stored on the brief:

| Check | Default | Setting |
|---|---|---|
| Opener label | `specific_number` or `question` | `[formula] good_openers` |
| A proof sentence in the first three | required | |
| Delivery is not `neutral_info` | required | |
| Teaching ("method") share of sentences | off; when on, at most a third | `method_cap = true` on the account, `[formula] method_max_share` |
| A spoken call to action | off | `spoken_ask = true` on the account |

## Which briefs it blocks

The formula blocks briefs at `idea` or `scripted`. A brief that is already `rendered` or `scheduled` gets the findings as advice only, and a `posted` brief is never judged: checks run before a video exists, never after it is live.

## Testing another shape on purpose

To test a shape the formula would reject (a teaching series, a new opener), set:

```yaml
formula_exception: "testing a how-to series against our story baseline, E014 is the control"
```

The checks still run and print, but they do not block. Use it for a real test with a control, never to skip the work.

## Updating the formula

1. Run the decode on your accounts and on two or three accounts you would like to resemble.
2. Look for gaps that are large (20 points or more), built on enough videos, and in the same direction on more than one account.
3. Set the thresholds in `reeldecode.toml`.
4. Post to the formula for ten videos, read `LEARNINGS.md`, and adjust. Your own results beat any default, including these.
