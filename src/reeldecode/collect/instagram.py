"""Optional Instagram collector: the public Reels grid of one account, read through YOUR OWN
signed-in browser profile. Opt-in (``[collect.instagram] enabled = true``).

Responsible use: this reads public data only (what any signed-in visitor sees on an account's
Reels tab), never logs in for you, never stores passwords, scrolls at a human pace and stops when
the grid stops growing. Instagram's terms of use, rate limits and the consequences of automated
access to your account are your responsibility. If you can export your data another way (a CSV
from a tool you already use), ``reeldecode collect --from-csv`` skips the browser entirely.

How it works: Playwright opens the profile's Reels tab, listens to the JSON responses the page
itself requests while scrolling, and keeps each media item's shortcode, play count, likes,
comments, caption and post time. Play counts that are missing are flagged, never estimated.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import store
from ..config import Config, normalize

log = logging.getLogger("reeldecode.collect")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
RESPONSIBLE_USE = (
    "Instagram collection is opt-in. It reads public Reels data through your own signed-in browser\n"
    "profile at a slow pace. Instagram's terms and rate limits are your responsibility. Enable it with\n"
    "[collect.instagram] enabled = true in reeldecode.toml, or use --from-csv instead.")


class NotEnabled(RuntimeError):
    pass


# ---------------------------------------------------------------- parsing (pure, tested)
def make_post(media: dict) -> dict | None:
    """One media node from Instagram's JSON -> a dataset row. None if it is not a post."""
    pk = media.get("pk") or media.get("id")
    if not pk or media.get("like_count") is None:
        return None
    play = media.get("play_count") or media.get("view_count") or media.get("video_view_count")
    code = media.get("code") or media.get("shortcode") or str(pk)
    cap = media.get("caption") or ""
    cap = cap.get("text", "") if isinstance(cap, dict) else str(cap)
    ts = int(media.get("taken_at") or media.get("timestamp") or 0)
    return {
        "id": str(pk), "shortcode": code, "url": f"https://www.instagram.com/reel/{code}/",
        "posted_at": datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else "",
        "media_type": "VIDEO" if media.get("media_type") in (2, "VIDEO") or media.get("product_type") == "clips" else str(media.get("media_type") or ""),
        "views": int(play) if play else None,
        "views_source": "grid_play_count" if play else "missing",
        "likes": int(media["like_count"]), "comments": int(media.get("comment_count") or 0),
        "duration": float(media.get("video_duration") or 0) or None,
        "caption": cap[:600],
    }


def extract_posts(data: Any) -> list[tuple[dict, str]]:
    """Walk any Instagram JSON response; return (row, uploader) for every media node in it."""
    out: list[tuple[dict, str]] = []
    seen: set[str] = set()

    def walk(obj, depth=0):
        if not obj or depth > 12:
            return
        if isinstance(obj, list):
            for x in obj:
                walk(x, depth + 1)
        elif isinstance(obj, dict):
            if obj.get("pk") and obj.get("like_count") is not None:
                post = make_post(obj)
                if post and post["id"] not in seen:
                    seen.add(post["id"])
                    user = obj.get("user") or obj.get("owner") or {}
                    out.append((post, user.get("username", "") if isinstance(user, dict) else ""))
                    return
            for v in obj.values():
                walk(v, depth + 1)

    walk(data)
    return out


# ---------------------------------------------------------------- browser
def browser_path(cfg: Config) -> str | None:
    for c in (cfg.ig_browser, os.environ.get("REELDECODE_CHROME", ""),
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome") or "", shutil.which("chromium") or ""):
        if c and Path(c).exists():
            return c
    return None   # Playwright's bundled Chromium


def _context(pw, cfg: Config, headless: bool):
    profile = Path(os.path.expanduser(cfg.ig_profile_dir))
    profile.mkdir(parents=True, exist_ok=True)
    return pw.chromium.launch_persistent_context(
        user_data_dir=str(profile), headless=headless, executable_path=browser_path(cfg),
        viewport={"width": 1280, "height": 800}, locale="en-US", user_agent=UA)


def grid_scrape(cfg: Config, handle: str, max_items: int = 600, idle_scrolls: int = 4) -> list[dict]:
    """Scroll one account's Reels tab until it stops growing (or max_items)."""
    if not cfg.ig_enabled:
        raise NotEnabled(RESPONSIBLE_USE)
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    handle = normalize(handle)
    rows: dict[str, dict] = {}

    def on_response(resp):
        u = resp.url
        if not ("graphql/query" in u or "/api/graphql" in u or "/api/v1/clips/" in u or "api/v1/feed/user/" in u):
            return
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 - not JSON, not ours
            return
        for post, uploader in extract_posts(body):
            if uploader and uploader.lower() != handle:
                continue   # explore / suggested posts bleeding into the page
            rows.setdefault(post["shortcode"], post)

    with sync_playwright() as pw:
        ctx = _context(pw, cfg, headless=True)
        try:
            if not any(c["name"] == "sessionid" for c in ctx.cookies("https://www.instagram.com")):
                raise RuntimeError("the browser profile is not signed in: run `reeldecode collect --login` first")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("response", on_response)
            try:
                page.goto(f"https://www.instagram.com/{handle}/reels/", wait_until="domcontentloaded", timeout=30_000)
            except PWTimeout:
                log.warning("page load timed out for @%s", handle)
            page.wait_for_timeout(4000)
            idle = scrolls = 0
            while len(rows) < max_items and idle < idle_scrolls:
                before = len(rows)
                page.mouse.wheel(0, 2600)
                page.wait_for_timeout(2500)        # human pace on purpose
                scrolls += 1
                idle = idle + 1 if len(rows) == before else 0
                print(f"  scroll {scrolls}: {len(rows)} videos", flush=True)
        finally:
            ctx.close()
    out = sorted(rows.values(), key=lambda r: r.get("posted_at") or "", reverse=True)
    return out[:max_items]


def collect(cfg: Config, handle: str, max_items: int = 600) -> Path:
    """Scrape and merge into reference_<handle>.json; decode work on existing rows is kept."""
    h = normalize(handle)
    scraped = grid_scrape(cfg, h, max_items)
    path = cfg.path(cfg.data) / f"reference_{h}.json"
    payload = store.load(path) if path.exists() else {"handle": h, "posts": []}
    old = {p["shortcode"]: p for p in payload["posts"] if p.get("shortcode")}
    for row in scraped:
        prior = old.get(row["shortcode"])
        if prior is None:
            payload["posts"].append(row)
            continue
        for k, v in row.items():   # fresh public numbers win; decode labels stay untouched
            if v not in (None, "") and (k in ("views", "views_source", "likes", "comments") or not prior.get(k)):
                prior[k] = v
    payload["posts"].sort(key=lambda r: r.get("posted_at") or "", reverse=True)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    store.save(path, payload)
    real = sum(1 for r in scraped if r["views_source"] == "grid_play_count")
    print(f"[collect] {path}: {len(scraped)} videos scraped, {real} with a real play count")
    return path


def login(cfg: Config, timeout_s: int = 1800) -> int:
    """Open a visible window on the configured profile; you sign in yourself; it closes once a
    session cookie exists. Nothing typed here is seen or stored by reel-decode."""
    from playwright.sync_api import sync_playwright

    print("Sign in to Instagram in the window that opened. It closes itself when you are signed in.", flush=True)
    with sync_playwright() as pw:
        ctx = _context(pw, cfg, headless=False)
        try:
            pg = ctx.pages[0] if ctx.pages else ctx.new_page()
            pg.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if any(c["name"] == "sessionid" and c["value"] for c in ctx.cookies("https://www.instagram.com")):
                    print("Signed in. The profile is ready for `reeldecode collect HANDLE`.")
                    return 0
                time.sleep(3)
            print("Timed out; no session saved.")
            return 1
        finally:
            ctx.close()
