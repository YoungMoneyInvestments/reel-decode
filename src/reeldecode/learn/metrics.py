"""Optional: pull your own posts' numbers at the 24 h, 72 h and 7 day marks and log them on briefs.

  YouTube Shorts   YouTube Data + Analytics API with your own OAuth token
                   (``[metrics] youtube_token``; pip install 'reel-decode[youtube]'): views, likes,
                   comments, average watch seconds and percent, shares, subscribers gained, the
                   retention curve, the share still watching at 3 s, and the curve's shape.
  Instagram Reels  the owner-only "View insights" panel, read from your own signed-in browser
                   profile (``browser_profile`` on the account in reeldecode.toml): views, reach,
                   non-follower share, likes, comments, saves, shares, follows, profile activity.
                   The web panel has no watch time or retention.

It only reads, and it fails loud: a signed-out profile, a wrong account or an empty panel is
printed and the run exits 1. Nothing is guessed or zero-filled.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

from ..config import Config, normalize
from ..gate import brief

IG_LABELS = {"Views": "views", "Viewers": "reach", "Accounts reached": "reach", "Likes": "likes",
             "Comments": "comments", "Saves": "saves", "Shares": "shares", "Follows": "follows",
             "Profile activity": "profile_visits", "Non-followers": "non_follower_pct"}
YT_ID = re.compile(r"(?:shorts/|watch\?v=|youtu\.be/)([\w-]{11})")
IG_CODE = re.compile(r"instagram\.com/(?:[\w.]+/)?(?:reel|p)/([\w-]+)")
IG_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
IG_EPOCH_MS = 1314220021721  # Instagram media ids carry their creation time: (id >> 23) ms after this


class Skip(Exception):
    """A post that cannot be read right now; the message says why and what fixes it."""


# ---------------------------------------------------------------- which posts, which mark
def parse_when(v) -> dt.datetime | None:
    if not v:
        return None
    if isinstance(v, dt.datetime):
        d = v
    elif isinstance(v, dt.date):
        d = dt.datetime(v.year, v.month, v.day, 12)
    else:
        try:
            d = dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:  # a hand-written note: take its first date and, if present, first clock time
            m = re.search(r"(\d{4}-\d{2}-\d{2})(?:\D{1,12}(\d{1,2}:\d{2}))?", str(v))
            if not m:
                return None
            d = dt.datetime.fromisoformat(f"{m.group(1)}T{(m.group(2) or '12:00').zfill(5)}")
    return d if d.tzinfo else d.astimezone()


def ig_posted_at(url: str) -> dt.datetime | None:
    """The exact post time of an Instagram reel, decoded from its shortcode (no network)."""
    m = IG_CODE.search(url or "")
    if not m or len(m.group(1)) > 12:  # longer codes are private-share links, not media ids
        return None
    n = 0
    for ch in m.group(1):
        if ch not in IG_ALPHABET:
            return None
        n = n * 64 + IG_ALPHABET.index(ch)
    when = dt.datetime.fromtimestamp(((n >> 23) + IG_EPOCH_MS) / 1000, dt.timezone.utc)
    return when if dt.datetime(2015, 1, 1, tzinfo=dt.timezone.utc) < when else None


def code_of(url: str) -> str:
    m = YT_ID.search(url) or IG_CODE.search(url)
    return m.group(1) if m else url


def platform_of(url: str) -> str | None:
    return "youtube" if YT_ID.search(url) else "instagram" if IG_CODE.search(url) else None


def posts_of(d: dict) -> list[dict]:
    """Every live post on a brief: trial versions first, then the top-level url(s)."""
    out, seen = [], set()
    for name, v in ((d.get("trial") or {}).get("posted") or {}).items():
        if isinstance(v, dict) and v.get("url"):
            out.append({"variant": str(name), "url": v["url"],
                        "posted_at": ig_posted_at(v["url"]) or parse_when(v.get("at"))})
            seen.add(code_of(v["url"]))
    links = re.findall(r"(?:\b(\w{1,3})\s+)?(https?://\S+)", str(d.get("url") or ""))
    for label, url in links:  # one link, or several written as "a URL | b URL"
        if code_of(url) not in seen:
            seen.add(code_of(url))
            out.append({"variant": label.upper() if label and len(links) > 1 else None, "url": url,
                        "posted_at": ig_posted_at(url) or parse_when(d.get("posted_at"))})
    return out


def due_mark(age_h: float, snaps: list[dict], variant, url: str, marks=(24, 72, 168)) -> int | None:
    """The latest mark this post has passed that has no snapshot yet."""
    passed = [m for m in marks if age_h >= m]
    if not passed:
        return None
    have = {s.get("mark") for s in snaps
            if s.get("variant") == variant and code_of(s.get("url") or url) == code_of(url)}
    return passed[-1] if passed[-1] not in have else None


# ---------------------------------------------------------------- YouTube
def curve_shape(curve: list[float], duration_s: float | None) -> str | None:
    """Name a retention curve (see the table in docs/test-and-learn.md)."""
    if len(curve) < 20:
        return None
    n = len(curve)
    hook_i = max(1, min(n - 1, round(n * 3 / duration_s))) if duration_s else max(1, n // 10)
    hook_drop = curve[0] - curve[hook_i]
    steps = [curve[i] - curve[i + 1] for i in range(hook_i, n - 1)]
    late = curve[int(n * 0.8)] - curve[-1]
    mid = curve[hook_i] - curve[int(n * 0.8)]
    if curve[0] and hook_drop / curve[0] > 0.45:
        return "hook failed: cliff in the first 3 s"
    if steps and max(steps) > 0.12 and max(steps) > 4 * (sum(steps) / len(steps) + 1e-9):
        at = hook_i + steps.index(max(steps))
        return f"one bad moment near {round(100 * at / n)}% of the video"
    if late > mid and late > 0.15:
        return "holds, then drops near the end: too long or the ask came early"
    if curve[hook_i] and mid / curve[hook_i] > 0.5:
        return "steady slide through the middle: the value failed"
    return "good: moderate early drop, long shallow slope"


def iso_seconds(iso: str) -> float | None:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else None


def youtube_clients(token_path: str):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(os.path.expanduser(token_path))
    return build("youtube", "v3", credentials=creds), build("youtubeAnalytics", "v2", credentials=creds)


def youtube_read(cfg: Config, urls: list[str]) -> dict[str, dict]:
    """url -> {"posted_at", "duration_s", "metrics"} or {"skip": reason}."""
    if not cfg.youtube_token:
        return {u: {"skip": "set [metrics] youtube_token in reeldecode.toml to read YouTube"} for u in urls}
    try:
        yt, yta = youtube_clients(cfg.youtube_token)
    except Exception as e:  # noqa: BLE001 - missing token or client library
        return {u: {"skip": f"YouTube client unavailable: {e}"} for u in urls}
    ids = {YT_ID.search(u).group(1): u for u in urls}
    idl = list(ids)
    items = []
    for i in range(0, len(idl), 50):
        items += yt.videos().list(part="snippet,statistics,contentDetails,status",
                                  id=",".join(idl[i:i + 50])).execute().get("items", [])
    found = {v["id"]: v for v in items}
    today = dt.date.today()
    out: dict[str, dict] = {}
    for vid, url in ids.items():
        v = found.get(vid)
        if not v:
            out[url] = {"skip": "video not found on the channel this token owns"}
            continue
        if v["status"]["privacyStatus"] != "public":
            out[url] = {"skip": f"video is {v['status']['privacyStatus']}: nothing to measure"}
            continue
        pub = parse_when(v["snippet"]["publishedAt"])
        dur = iso_seconds(v["contentDetails"].get("duration"))
        st = v["statistics"]
        m: dict = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                   "comments": int(st.get("commentCount", 0))}
        q = yta.reports().query(
            ids="channel==MINE", startDate=str(pub.date()), endDate=str(today), filters=f"video=={vid}",
            metrics="views,averageViewDuration,averageViewPercentage,shares,subscribersGained").execute()
        row = (q.get("rows") or [None])[0]
        if row and row[0]:  # Analytics lags about two days; until then only the public counts exist
            m.update({"avg_watch_s": row[1], "avg_watch_pct": round(row[2], 1), "shares": row[3], "follows": row[4]})
            r = yta.reports().query(
                ids="channel==MINE", startDate=str(pub.date()), endDate=str(today), filters=f"video=={vid}",
                metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio").execute().get("rows", [])
            curve = [round(x[1], 3) for x in r]
            if curve:
                if dur:
                    m["hold_3s"] = round(100 * curve[min(len(curve) - 1, round(len(curve) * 3 / dur))], 1)
                m["retention"] = curve[::5]
                shape = curve_shape(curve, dur)
                if shape:
                    m["curve"] = shape
        out[url] = {"posted_at": pub, "duration_s": dur, "metrics": m}
    return out


# ---------------------------------------------------------------- Instagram
def parse_ig_panel(body: str) -> dict:
    """The text of Instagram's insights panel -> {metric: number}. Labels with no number are skipped."""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    out: dict = {}
    for i, ln in enumerate(lines):
        key = IG_LABELS.get(ln)
        if not key or key in out:
            continue
        for cand in lines[i + 1:i + 4]:
            c = cand.replace(",", "")
            if re.fullmatch(r"\d+(\.\d+)?%?", c):
                out[key] = float(c.rstrip("%")) if "." in c or c.endswith("%") else int(c)
                break
            if c in IG_LABELS:  # the next label arrived first: this one has no number ("--")
                break
    return out


def instagram_read(cfg: Config, account: str, urls: list[str]) -> dict[str, dict]:
    from playwright.sync_api import sync_playwright

    from ..collect.instagram import browser_path

    handle = normalize(account)
    prof = cfg.account(handle).browser_profile
    if not prof:
        raise Skip(f"no browser_profile set for @{handle} in reeldecode.toml")
    profile = Path(os.path.expanduser(prof))
    out: dict[str, dict] = {}
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile), executable_path=browser_path(cfg), headless=True,
            viewport={"width": 1280, "height": 1400}, locale="en-US")
        try:
            if not any(c["name"] == "sessionid" and c["value"] for c in ctx.cookies("https://www.instagram.com")):
                raise Skip(f"the browser profile for @{handle} is signed out")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.instagram.com/accounts/edit/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            who = re.search(r'"username":"([^"]+)"', page.content())
            if not who or who.group(1).lower() != handle:
                raise Skip(f"the profile is signed in as @{who.group(1) if who else '?'}, expected @{handle}")
            for url in urls:
                try:
                    # /p/ rather than /reel/: a Trial Reel opened at /reel/ has no insights button
                    page.goto(f"https://www.instagram.com/p/{code_of(url)}/", wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)
                    btn = page.get_by_text("View insights", exact=True).first
                    if not btn.count() or not btn.is_visible():
                        out[url] = {"skip": f"no 'View insights' for @{handle}: not this account's post, or removed"}
                        continue
                    btn.click(timeout=5000)
                    page.wait_for_function(
                        "() => { const t = document.body.innerText; return t.includes('Interactions') && t.includes('Likes'); }",
                        timeout=12000)
                    time.sleep(1)
                    m = parse_ig_panel(page.locator("body").inner_text(timeout=5000))
                    out[url] = {"metrics": m} if "views" in m else {"skip": "insights panel showed no Views number"}
                except Exception as e:  # noqa: BLE001 - per post, reported
                    out[url] = {"skip": f"{type(e).__name__}: {str(e)[:160]}"}
        finally:
            ctx.close()
    return out


# ---------------------------------------------------------------- command
def cmd_pull(cfg: Config, ids: list[str], all_now: bool = False, dry_run: bool = False) -> int:
    now = dt.datetime.now().astimezone()
    marks = cfg.marks_hours
    todo: list[dict] = []
    for p, d in brief.all_exps(cfg.path(cfg.experiments)):
        if ids and d.get("id") not in ids:
            continue
        for post in posts_of(d):
            plat = platform_of(post["url"])
            if plat:
                todo.append({"path": p, "id": d.get("id"), "account": d.get("account") or "", "platform": plat, **post})
    problems: list[str] = []
    results: dict[str, dict] = {}
    yt_urls = [t["url"] for t in todo if t["platform"] == "youtube"]
    if yt_urls:
        try:
            results.update(youtube_read(cfg, yt_urls))
        except Exception as e:  # noqa: BLE001
            problems.append(f"YouTube: {type(e).__name__}: {str(e)[:200]}")
    by_acct: dict[str, list[dict]] = {}
    for t in todo:
        if t["platform"] == "instagram":
            by_acct.setdefault(t["account"], []).append(t)
    for acct, ts in by_acct.items():
        want = []
        for t in ts:
            snaps = brief.load(t["path"]).get("metrics") or []
            age = (now - t["posted_at"]).total_seconds() / 3600 if t["posted_at"] else None
            if all_now or (age is not None and due_mark(age, snaps, t["variant"], t["url"], marks)):
                want.append(t["url"])
            elif age is None:
                problems.append(f"{t['id']}: no posted_at on the brief, cannot place {t['url']} on a mark")
        if not want:
            continue
        try:
            results.update(instagram_read(cfg, acct, want))
        except Skip as e:
            problems.append(f"Instagram @{acct}: {e} ({len(want)} post(s) waiting)")
        except Exception as e:  # noqa: BLE001
            problems.append(f"Instagram @{acct}: {type(e).__name__}: {str(e)[:200]}")
    logged = 0
    for t in todo:
        r = results.get(t["url"])
        if r is None:
            continue
        tag = f"{t['id']}{'/' + t['variant'] if t['variant'] else ''}"
        if "skip" in r:
            problems.append(f"{tag}: {r['skip']}")
            continue
        d = brief.load(t["path"])
        posted = t["posted_at"] or r.get("posted_at")
        if not posted:
            problems.append(f"{tag}: no post time known")
            continue
        age = (now - posted).total_seconds() / 3600
        snaps = d.get("metrics") or []
        mark = due_mark(age, snaps, t["variant"], t["url"], marks)
        if mark is None and not all_now:
            continue
        snap = {"at": now.isoformat(timespec="minutes"), "hours_since_post": round(age, 1),
                "mark": mark, "source": "reeldecode/" + t["platform"], "url": t["url"]}
        if t["variant"]:
            snap["variant"] = t["variant"]
        snap.update(r["metrics"])
        print(f"{tag} {round(age)}h mark={mark}: " + json.dumps(r["metrics"]))
        if dry_run:
            continue
        d.setdefault("metrics", []).append(snap)
        if r.get("duration_s") and not d.get("duration_s"):
            d["duration_s"] = r["duration_s"]
        if not d.get("posted_at") and r.get("posted_at") and not t["variant"]:
            d["posted_at"] = r["posted_at"].isoformat(timespec="seconds")
        if d.get("status") in (None, "scheduled", "rendered"):
            d["status"] = "posted"
        brief.save(t["path"], d)
        logged += 1
    print(f"\n{logged} snapshot(s) logged from {len(todo)} live post(s); {len(problems)} problem(s)")
    for pr in sorted(set(problems)):
        print("  PROBLEM " + pr, file=sys.stderr)
    return 1 if problems else 0
