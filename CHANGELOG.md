# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `reeldecode production`: runs [rea-video](https://github.com/JuneYaooo/rea-video) (Apache-2.0, optional extra `[production]`) on every selected video and keeps a compact record per post. It covers shots and pacing, jump cuts and transition effects, captions, text callouts and stickers, sound effects and what they land on, voice source (human or TTS), music, tempo and beat-synced editing, framing, camera and lighting, and filmed / AI / code / screen per shot. The production-method call counts only when a vision model or agent checked it or the tools were at least 80% sure, because recompressed platform downloads fool the pixel tests. Writes `PRODUCTION-FINDINGS.md` (winners vs losers), adds a production table and per-video chips to the page, five `formats` groupings, and a "how it was made" line, remake route and breakdown path to idea cards. `--one <file-or-url>` decodes a single video. Synthetic demo data now carries planted production effects. See [docs/production.md](docs/production.md).
- `frames`: new shot type `talking_head_with_graphics` (a person to camera with panels, charts or cards laid over the live shot). Before this, such a video was labeled `talking_head` and could not be ranked apart from a plain one; one continuous take with building overlays has zero cuts, so cut-based pacing cannot see it either.
- `reeldecode hooks`: the triple hook (context, lean, snapback) scored 0 to 3 per video with typed Jev questions, plus where the context is set (said, written, shown) and whether the ending asks for a topic word after delivering value. `formats` groups by score and parts; `gate read` blocks scripts missing a part (`triple_hook = false` turns it off). See [docs/hooks.md](docs/hooks.md).
- `reeldecode frames`: six stills per video (three from the first 3 seconds, three from the body) go to Jev as images with typed questions: shot type, on-screen caption, and what the first frame does. Per-video visual format, opening shot and shot sequence are computed in code. All or nothing per video; cost logged to `decode_runs.jsonl`.
- `reeldecode formats`: script format, spoken hook, opening sequence of sentence jobs, visual format, opening shot, first frame and their pairings, ranked per creator by median times-typical, then pooled across creators one vote each. See [docs/formats.md](docs/formats.md).
- `reeldecode ideas`: idea cards from videos at least N times their account's same-year median (structure and numbers, no script to reuse). `inspired_by` in a brief adds a copy check to the gate (fails on too many shared five-word runs or an eight-word verbatim run, and fails closed without a transcript). `learn report` lists posts over 100,000 organic views as promotion candidates; it never spends money. See [docs/ideas.md](docs/ideas.md).
- Content lanes: `[[accounts.lanes]]` (job, funnel stages, format, weekly target, off-limits words), `gate new --lane --format`, lane checks in `gate check`, `reeldecode lanes` for posted / queued / short per lane. `carousel`, `image` and `text_post` briefs skip the spoken-script checks and require a source for every quote. See [docs/lanes.md](docs/lanes.md).
- `reeldecode taste`: reference videos in, `tastebook.md` out (shot length, opening cuts, opening hold, cuts on new sentences, each cited with timestamps), plus before/after frames for every cut. Zooms, captions, b-roll and sound effects are reported as not measured.
- `reeldecode edit-plan`: a typed keep / delete / move verdict, destination and coded reason for every script line, with repeat and contradiction handling. See [docs/editing.md](docs/editing.md).

## [0.1.0] - 2026-11-16

### Added
- `reeldecode` CLI: `init`, `collect`, `fetch`, `transcribe`, `anatomy`, `visual`, `page`, `gate`, `learn`.
- Spoken-script decode: yt-dlp fetch, local Whisper transcripts with sentence timings, Jev typed labels per sentence and per script, fail-closed on partial answers, cost log per run.
- Visual decode: cuts, faces, opening motion and on-screen text with OpenCV and tesseract.
- Winners-vs-losers analysis inside each account against its same-year median, with counts on every gap.
- Single-file interactive decode page, plus a bundled synthetic dataset for `page --demo`.
- Brief gate: ten-point script rubric, viewer-first brief checks, the configurable script formula and a hashed Jev script read.
- Learning loop: `learn log`, `learn pull` (Instagram insights from your own signed-in profile, YouTube Analytics with your own token), `learn report` with trial-winner picking and retention-curve naming.
- CSV import and an opt-in Instagram Reels grid collector that runs on your own browser profile.
- Docs for the formula, the decode questions and the test-and-learn loop; cron and launchd examples.
