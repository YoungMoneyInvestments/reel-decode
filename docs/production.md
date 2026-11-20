# Production: how each video was made, shot by shot

The script stages tell you what a video **says**. `visual` and `frames` tell you roughly what is on
screen. `reeldecode production` tells you how the video was **made and edited**: every cut and what kind
it is, every caption line and styled text callout, stickers, every sound effect and what it lands on,
whether the voice is a human recording or TTS, whether there is music and whether the edit is cut to
its beat, framing, camera support and lighting. For each shot it also judges the production method
(filmed, AI video, code or template graphics, screen recording, avatar, 3D) and writes a remake plan.

The measuring is done by [rea-video](https://github.com/JuneYaooo/rea-video) (Apache-2.0), run as a
separate tool. reel-decode runs it on every selected video, keeps its full breakdown, and turns the
measurements into winners-vs-losers traits, `formats` groupings and idea-card lines.

## The run

```bash
pip install -e '.[fetch,production]'    # rea-video, pinned to the commit this was tested against
brew install ffmpeg                      # or apt install ffmpeg
reeldecode production                    # every selected video -> data/PRODUCTION-FINDINGS.md
reeldecode page && reeldecode formats && reeldecode ideas
```

On Python 3.12 and older, rea-video's OCR extra also pulls in `opencv-python`, which shares the `cv2`
folder with the `opencv-python-headless` used here. If `import cv2` breaks afterwards:
`pip uninstall -y opencv-python && pip install --force-reinstall --no-deps "opencv-python-headless>=4.8,<5"`.

One video at a time (a file, or any URL `yt-dlp` can fetch), without a dataset:

```bash
reeldecode production --one path/to/video.mp4 --out breakdown-one
```

That prints a one-line summary and the paths to rea-video's `VIDEO.md` (a layered breakdown an agent
can read cheaply) and `report.html` (the human report with storyboard and remake plan).

`reeldecode page --demo` shows the production table on the bundled **synthetic** data, with effects
planted on purpose.

## What it records per video

The full breakdown lives in `.reeldecode-cache/production/<id>/` (`VIDEO.md`, `report.html`,
`breakdown.json`, sound stems). A compact record goes on the post as `prod`:

| field | what it is |
|---|---|
| `shots`, `shots_per_10s`, `avg_shot_s` | shot count and pacing from rea-video's shot detector |
| `jump_cuts`, `effect_transitions` | jump cuts, and transitions other than a hard cut (dissolves, wipes, whips) |
| `text_first_1s` | on-screen text (not text that is part of the scene) in the first second |
| `captions`, `callouts`, `stickers` | caption lines, styled text callouts and labels, stickers and emoji |
| `sfx`, `sfx_on_cue` | sound effects (low-confidence ones left out), and how many land on a cut or a text entrance |
| `voice`, `voice_source` | voice present; `human_recording`, `tts`, `ai_video_native` or `unknown` |
| `music`, `bpm`, `music_source`, `beat_synced` | music present, its tempo, `existing_library` / `popular_song` / `ai_generated`, and whether the cuts hit the beat |
| `camera_moving_share`, `shot_size_main`, `lighting` | share of time on a moving camera, the main framing, the lighting setup |
| `made_mix`, `made_main`, `made_reliable` | production method shares by duration, and whether the call can be trusted (below) |
| `remake`, `package` | rea-video's one-line remake plan and the path to the full `VIDEO.md` |

A source rea-video is less than 60% sure of (voice or music) is written as `unknown`, not guessed.

## The production-method call is gated

Telling filmed footage from AI video leans on sensor noise and frame cadence, and **platform
recompression erases both**. In testing, a phone-shot TikTok downloaded from the platform came back as
"100% AI video" at 0.60 confidence. reel-decode therefore counts `made_mix` only when:

- a vision model judged the shots (`reeldecode production --vlm`, configured with rea-video's
  `REA_VLM_BASE_URL`, `REA_VLM_API_KEY`, `REA_VLM_MODEL`; any OpenAI-compatible vision model), or
- an agent reviewed the shots (`rea-video review` then `rea-video apply-review` on the breakdown
  folder), or
- the tools alone were at least 80% sure.

Method traits ("has AI-generated shots", "mostly filmed"...) are compared only across the videos that
pass. Everything else in the table is measured, not judged, and counts on every video.

## Winners vs losers

`PRODUCTION-FINDINGS.md`, and the "How winners are made vs losers" table on the page, use the same
method as the script table (top third vs bottom third inside one account, against its same-year
median; gap in points with counts). The traits:

fast cutting (4+ shots per 10 s) · long takes (under 1.5 per 10 s) · jump cuts · transition effects ·
text in the first second · burned-in captions · styled text callouts · stickers · added sound effects ·
sound effects on cuts or text · background music · edit cut to the beat · human voice · TTS or AI
voice · moving camera · close framing · and, when gated in: mostly filmed · AI shots · code or
template graphics · screen recording · AI avatar.

`formats` adds five groupings: **edit pace**, **on-screen text**, **sound design**, **voice source**
and **production method** (reliable calls only), each ranked against the creator's typical video.

Idea cards for outliers gain a "how it was made" line (shots, pace, voice, music, text, sound
effects), the remake route when the method call is reliable, and the path to the shot-by-shot
breakdown. Use it to remake the craft (camera, pacing, caption style, sound cues) with your own
material. Don't reuse the outlier's footage, music, characters or likeness.

## Cost and time

Everything runs locally and costs nothing per video. Only `--vlm` calls a paid model, and that is your
own endpoint. The first run downloads rea-video's sound models (about 220 MB, to
`~/.cache/rea-video/models`). Measured on a laptop CPU: a 21-second video takes about a minute, so
budget roughly 3x the video's running time. `--workers` runs that many videos at once (default 2).
Each video caches, so a rerun only does new work. `--force` redoes them.

## Limits

- Same as every table here: associations, small samples, public views only. See the README.
- rea-video's caption OCR defaults to Chinese + English. Other scripts need its own `--ocr-lang`,
  which this stage does not pass yet.
- A failed video (download or decompose) is recorded on the post as `prod_error` and left out. It is
  never half-recorded.
