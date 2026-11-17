# Content lanes: what each account is for

Decoding tells you what works. Lanes keep you making it, on the right account, every week.

The failure this prevents: one person, several accounts or brands, and every post drifting toward whatever was easiest that day. The product account turns into a founder diary, the personal account turns into ads, and nobody can say what the schedule is. A **lane** fixes that by giving each recurring kind of post a job, a funnel stage, a format, a weekly target and a list of things that do not belong in it.

## Define lanes per account

In `reeldecode.toml`:

```toml
[[accounts]]
handle = "acme_product"
yours = true

[[accounts.lanes]]
name = "founder-explainer"
job = "Founder explains the product on camera, interview style"
stages = ["mofu", "bofu"]        # the funnel stages this lane may serve
format = "interview"
per_week = 2
avoid = ["get rich", "guaranteed"]   # words that do not belong here

[[accounts.lanes]]
name = "customer-quote-carousel"
job = "Real customer quotes as designed carousels, never raw screenshots"
stages = ["mofu"]
format = "carousel"
per_week = 3

[[accounts]]
handle = "acme_founder"
yours = true

[[accounts.lanes]]
name = "building-in-public"
job = "The human side: what I am building, why, what went wrong"
stages = ["tofu", "mofu"]
format = "talking_head"
per_week = 4
```

Decide the split once, on paper, before filming: which account carries which job (reach, trust, proof, the ask), what each account must never become, and what ships every week. The config is where that decision lives so every later post is checked against it.

## The gate enforces the lane

```bash
reeldecode gate new E014 "Three first weeks" --variable format --stage mofu \
    --account acme_product --lane customer-quote-carousel --format carousel
reeldecode gate check E014
```

On an account that has lanes, a brief fails until it names a lane that exists, its funnel stage is one the lane serves, its format matches the lane, and none of the lane's `avoid` words appear in its topic, caption or script. An account with no lanes has no lane rules.

## Posts without a spoken script

`carousel`, `image` and `text_post` briefs skip the spoken-script rubric and the script formula (there is no script). They still need the funnel job, one topic, a viewer takeaway, someone to send it to, and a **recorded source for every quote or claim** (who said it, where, and permission to use it). Quote posts built from community messages should name the source in `proof`, not just screenshot the message.

## See the week

```bash
reeldecode lanes                 # next 7 days
reeldecode lanes --days 14 --strict   # exit 1 if any lane is short; use it in a scheduled check
```

For each lane: target, posted in the window (briefs with `status: posted` and a `posted_at`), queued (scripted, rendered or scheduled), the shortfall, and days since the last post. A lane with a shortfall has an empty slot. Fill it with a brief, not with whatever is lying around.

## What lanes do not do

Reel-decode does not produce the carousel images, source the quotes or schedule the post. It makes sure each of those jobs exists as a brief, on the right account, at the right funnel stage, at the cadence you chose. Keep the real lane definitions for your brands in your own private config, not in a public repository.
