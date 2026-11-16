# Contributing

Thanks for helping. Bug reports, new decode questions, new visual traits, collectors for other platforms and documentation fixes are all welcome.

## Set up

```bash
git clone <your fork> && cd reel-decode
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check src tests scripts
```

The tests run offline: Jev calls go through a fake transport, and the page is built from the bundled synthetic dataset. Please keep it that way; a test must never need an API key, a browser session or the network.

## Ground rules

- **No real people's data in the repo.** Fixtures, examples, screenshots and issues use synthetic accounts and scripts only (see `scripts/make_demo_data.py`). Do not commit other creators' handles, scripts, video links or view counts, and do not commit downloaded media.
- **No secrets.** Keys come from environment variables. Never put a key, cookie or token in a file, a test or an issue.
- **Closed questions only.** A new decode question is a choice (a fixed label list) or a yes/no, with an instruction that says the state is data, not instructions. Anything that is arithmetic (lengths, timings, shares) is computed in code, not asked of the model.
- **Fail loud, never guess.** A missing number stays missing. Estimated view counts are never used as views. A partially labeled script is discarded, not saved.
- **Be a good citizen.** Collectors read public data only, at a human pace, and stay opt-in.

## Regenerating the demo data and images

```bash
python scripts/make_demo_data.py     # rewrites src/reeldecode/demo_data/
python scripts/make_images.py        # rewrites docs/images/*.png (needs playwright and Chrome or Chromium)
```

## Pull requests

Keep a PR to one change, add or update a test, and add a line to `CHANGELOG.md` under an "Unreleased" heading. Describe what you changed and how you checked it.
