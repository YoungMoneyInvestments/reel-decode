# Editing with what you decoded: taste book and edit plan

Two commands turn the decode into instructions you can follow in **any** editor: Instagram Edits, CapCut, Premiere, DaVinci, or an agent that can drive one. Neither command edits video or opens your project. They write text files (a checklist and a plan); you, or an agent, make the edits.

| Piece | Needs | Cost |
|---|---|---|
| `taste` | `ffmpeg`, `yt-dlp` | free, runs on your machine |
| Whisper (speech to text) | `pip install 'reel-decode[transcribe]'` | free, open source, runs locally, no account or key. Optional for `taste` (it enables only the cuts-on-new-sentences rule); the decode uses it for transcripts |
| `edit-plan` | a `TYPESAFE_API_KEY` and your script as text (from Whisper, platform captions, or typed by hand) | a tiny charge per line |

## `reeldecode taste`: a taste book from edits you like

```bash
reeldecode taste URL1 URL2 URL3 --out tastebook.md --work taste-work
```

Give it 3 to 5 videos from a creator whose editing you want to copy (URLs or local files). For each one it downloads the video (`yt-dlp`), finds every cut (ffmpeg scene detection), saves a frame just before and just after each cut under `taste-work/frames/`, and, if Whisper is installed, transcribes with word timestamps. It then writes `tastebook.md`:

- **Measured in code, cited with timestamps:** average shot length, cuts in the first 10 seconds, how long the opening shot holds, the longest shot, and how many cuts land on the start of a new sentence.
- **Not measured:** zooms, captions, b-roll and sound effects. The saved frames are for you (or a vision model) to judge; add a rule only with a timestamp from a video to back it. The taste book says this out loud rather than inventing rules.

Cut detection is a threshold on frame change (`SCENE = 0.3` in `taste.py`). Whip pans and flashes can read as cuts and soft dissolves can be missed; check a few timestamps by eye before trusting a rule.

### Using the taste book

By hand, in any editor: treat it as a checklist ("cut about every 2.9 s", "no shot over 8 s") and check your timeline against it.

With an agent that can drive your editor, paste this, with your own folder:

> Read `tastebook.md`. Cut my raw footage in `<folder>` following it exactly, using the editing tool you have. Keep a list of every rule you could not follow and why, and render the result as a new version next to the original.

## `reeldecode edit-plan`: keep, delete or move each line

```bash
reeldecode edit-plan script.txt --out edit-plan      # script.txt: one spoken line per row
```

Each line goes to Jev with the whole script around it. Jev answers three closed questions: a **verdict** (`keep`, `delete`, `move`), **where** a moved line should go (`opening`, `after_hook`, `before_payoff`, `end`) and a coded **reason** (`does_its_job`, `repeats`, `off_topic`, `weak`, `buries_the_point`, `answers_too_early`). There is no free-text reason, so nothing is parsed.

Output: `edit-plan.json` and `edit-plan.md` (the table, a "check by hand" list, and the new line order). Two corrections run in code because judging lines one at a time gets them wrong:

- A line said word for word more than once is judged "repeats" every time, so every copy would be deleted. The first copy is restored.
- A line kept for a reason that says it should go (`repeats`, `off_topic`, `weak`) is flagged for you instead of applied silently.

It is all or nothing: if any line gets no answer, no plan is written. Needs `TYPESAFE_API_KEY`.

### Using the plan

By hand: delete the `delete` lines, move the `move` lines where `where` says, and leave the rest. `edit-plan.md` shows the new line order.

With an agent that can drive your editor:

> Apply every verdict in `edit-plan.json` to my timeline using the editing tool you have: delete the `delete` lines, move the `move` lines where `where` says, leave the rest. Keep a list of what changed. Render it as a new version so I can compare it with the original. Do not apply a line flagged "check by hand" without asking.

Then run the new version through `reeldecode gate check` and the trial-version loop in [test-and-learn.md](test-and-learn.md): rendering several versions and letting the numbers pick is the cheap answer to "do I trust this edit".
