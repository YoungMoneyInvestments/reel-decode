# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
