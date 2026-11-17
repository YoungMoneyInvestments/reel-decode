# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
