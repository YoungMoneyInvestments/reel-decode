"""The dataset on disk: one ``reference_<handle>.json`` per account in the data folder.

    {"handle": "demo_creator", "posts": [
        {"shortcode": "abc123", "url": "https://...", "posted_at": "2026-03-01T12:00:00+00:00",
         "views": 1840, "views_source": "grid_play_count", "caption": "...", "likes": 90, ...}]}

Any platform yt-dlp can download works (Instagram Reels, TikTok, YouTube Shorts): ``fetch`` uses
each post's ``url``. ``shortcode`` is just a stable id for the cache. Rows whose ``views`` are an
estimate (``views_source: "estimate"``) are never used.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import Config, normalize

SHORTCODE_RE = re.compile(r"/(?:reel|reels|p|tv|shorts|video)/([A-Za-z0-9_-]+)")


class Store:
    def __init__(self, cfg: Config, data_dir: Path | None = None, only: set[str] | None = None):
        self.cfg = cfg
        self.data = data_dir or cfg.path(cfg.data)
        cache = cfg.path(cfg.cache)
        self.audio, self.trans, self.meta = cache / "audio", cache / "transcripts", cache / "meta"
        self.video, self.visual = cache / "video", cache / "visual"
        self.only = {normalize(h) for h in (only or set())}

    def files(self) -> list[Path]:
        fs = sorted(self.data.glob("reference_*.json"))
        return [f for f in fs if not self.only or handle_of_file(f) in self.only]

    def audio_file(self, sc: str) -> Path | None:
        """The finished download for a reel; a .part file still being written is not one."""
        for f in sorted(self.audio.glob(f"{sc}.*")):
            if f.suffix not in (".part", ".json", ".ytdl"):
                return f
        return None

    def transcript(self, sc: str) -> dict | None:
        p = self.trans / f"{sc}.json"
        if not p.exists():
            return None
        doc = json.loads(p.read_text(encoding="utf-8"))
        return None if doc.get("error") else doc


def handle_of_file(p: Path) -> str:
    return normalize(p.stem.replace("reference_", ""))


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def save(p: Path, payload: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def handle_of(payload: dict, p: Path) -> str:
    return normalize(payload.get("handle") or payload.get("account") or handle_of_file(p))


def selected(payload: dict, per_account: int) -> list[dict]:
    """Newest videos with a real view count (files are kept newest first)."""
    rows = [p for p in payload.get("posts") or []
            if p.get("shortcode") and p.get("views") and p.get("views_source") != "estimate"]
    rows.sort(key=lambda r: r.get("posted_at") or "", reverse=True)
    return rows[:per_account] if per_account else rows


def shortcode_of(url: str) -> str:
    m = SHORTCODE_RE.search(url or "")
    if m:
        return m.group(1)
    return hashlib.sha1((url or "").encode()).hexdigest()[:12]


def import_csv(cfg: Config, csv_path: Path, handle: str) -> Path:
    """Build or extend reference_<handle>.json from a CSV with columns
    url, views[, posted_at, caption, likes, comments]. Existing rows keep their decode work."""
    h = normalize(handle)
    out = cfg.path(cfg.data) / f"reference_{h}.json"
    payload = load(out) if out.exists() else {"handle": h, "posts": []}
    by_code = {p["shortcode"]: p for p in payload["posts"] if p.get("shortcode")}
    added = updated = 0
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            url = (row.get("url") or "").strip()
            if not url:
                continue
            sc = (row.get("shortcode") or "").strip() or shortcode_of(url)
            rec = by_code.get(sc)
            if rec is None:
                rec = {"shortcode": sc, "url": url}
                payload["posts"].append(rec)
                by_code[sc] = rec
                added += 1
            else:
                updated += 1
            if (row.get("views") or "").strip():
                rec["views"] = int(float(row["views"].replace(",", "")))
                rec["views_source"] = "csv"
            for k in ("posted_at", "caption"):
                if (row.get(k) or "").strip():
                    rec[k] = row[k].strip()
            for k in ("likes", "comments"):
                if (row.get(k) or "").strip():
                    rec[k] = int(float(row[k].replace(",", "")))
    payload["posts"].sort(key=lambda r: r.get("posted_at") or "", reverse=True)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    save(out, payload)
    print(f"[import] {out}: {added} added, {updated} updated")
    return out
