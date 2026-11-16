#!/usr/bin/env python3
"""Render the README images from the SYNTHETIC demo data. Needs playwright and Google Chrome
(or `playwright install chromium`).

    python scripts/make_images.py            # writes docs/images/*.png
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT / "src"))

from reeldecode import config, page
from reeldecode.store import Store

ROLE_COLORS = {"hook": "#ff6b9d", "setup": "#a48bff", "story": "#3cc4dc", "proof": "#3ecf98",
               "method": "#6ea0ff", "payoff": "#f0a93a", "cta": "#ff7b66", "filler": "#6b7485"}

BANNER = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@600&display=swap">
<style>
*{box-sizing:border-box;margin:0}
body{width:__W__px;height:__H__px;background:radial-gradient(1200px 600px at 85% 20%,#1c2a4a 0,#0f1319 60%);color:#e8ecf2;
 font-family:"IBM Plex Sans",system-ui,sans-serif;display:flex;align-items:center;gap:56px;padding:0 __PAD__px;overflow:hidden}
.l{flex:1.05;display:flex;flex-direction:column;gap:22px}
.k{font:500 15px "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:#6ea0ff}
h1{font:600 __T__px/1 "IBM Plex Sans Condensed",sans-serif;letter-spacing:-.01em}
p{font-size:__P__px;line-height:1.38;color:#b9c2d0;max-width:30ch}
.cmd{font:500 17px "IBM Plex Mono",monospace;background:#171c24;border:1px solid #2a313d;border-radius:8px;padding:12px 16px;color:#e8ecf2;width:max-content}
.cmd b{color:#3ecf98;font-weight:500}
.r{flex:1;display:flex;flex-direction:column;gap:14px}
.card{background:#171c24;border:1px solid #2a313d;border-radius:14px;padding:18px 20px;box-shadow:0 20px 60px rgba(0,0,0,.35)}
.strip{display:flex;height:14px;border-radius:4px;overflow:hidden;margin:4px 0 12px}
.line{display:grid;grid-template-columns:62px 1fr;gap:10px;font-size:15px;padding:5px 0;border-bottom:1px solid #232a35}
.line i{font:500 11px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.05em;font-style:normal;padding-top:3px}
.hd{display:flex;justify-content:space-between;font:400 13px "IBM Plex Mono",monospace;color:#98a2b3}
.hd b{color:#e8ecf2;font-weight:500}
table{width:100%;border-collapse:collapse;font-size:14.5px}
td{padding:6px 4px;border-bottom:1px solid #232a35}
td.g{text-align:right;font:500 14px "IBM Plex Mono",monospace}
.pos{color:#3ecf98}.neg{color:#ff7b66}
</style></head><body>
<div class="l">
  <div class="k">open source · short-form video</div>
  <h1>reel-decode</h1>
  <p>Find out what your winning Reels, Shorts and TikToks <em>say and show</em> that your losing ones don't.</p>
  <div class="cmd"><b>$</b> reeldecode page --demo --open</div>
</div>
<div class="r">
  <div class="card">
    <div class="hd"><span><b>@demo_creator</b> · 3.1× its year median</span><span>top third</span></div>
    <div class="strip">__STRIP__</div>
    __LINES__
  </div>
  <div class="card">
    <div class="hd" style="margin-bottom:6px"><span><b>winners vs losers</b>, same account</span><span>gap, pts</span></div>
    <table>__ROWS__</table>
  </div>
</div>
</body></html>"""


def banner_html(data: dict, w: int, h: int, compact: bool = False) -> str:
    acct = next(a for a in data["accounts"] if a["handle"] == "demo_creator")
    reels = [r for r in data["reels"] if r["a"] == "demo_creator" and r["script"] and r["tier"] == "winner"]
    best = sorted(reels, key=lambda r: (-(len(r["script"]) >= 5), -(r["xm"] or 0)))[0]
    strip = "".join(f'<span style="flex:{max(1, len(s[2].split()))};background:{ROLE_COLORS[s[1]]}"></span>'
                    for s in best["script"])
    lines = "".join(f'<div class="line"><i style="color:{ROLE_COLORS[s[1]]}">{s[1]}</i><span>{s[2]}</span></div>'
                    for s in best["script"][: 3 if compact else 4])
    rows = ""
    for x in acct["lift"][: 3 if compact else 4]:
        g = round(x["gap"] * 100)
        name = f'{x["dim"].replace("_", " ")}: {x["value"].replace("_", " ")}'
        rows += f'<tr><td>{name}</td><td class="g {"pos" if g > 0 else "neg"}">{g:+d}</td></tr>'
    html = BANNER.replace("__STRIP__", strip).replace("__LINES__", lines).replace("__ROWS__", rows)
    html = html.replace("__W__", str(w)).replace("__H__", str(h))
    html = html.replace("__PAD__", "64" if compact else "84").replace("__T__", "72" if compact else "92")
    html = html.replace("__P__", "22" if compact else "25")
    return html.replace("3.1×", f'{best["xm"]:.1f}×')


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="reeldecode-img-"))
    data = page.build(Store(config.Config(), page.demo_dir()), 0, 7, {"demo_creator"})
    html = page.render(data, tmp)
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(channel="chrome")
        except Exception:  # noqa: BLE001 - fall back to Playwright's own Chromium
            b = pw.chromium.launch()
        for name, w, h, compact in (("hero.png", 1600, 640, False), ("social-preview.png", 1280, 640, True)):
            pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            pg.set_content(banner_html(data, w, h, compact), wait_until="networkidle")
            pg.screenshot(path=str(IMG / name))
            pg.close()
            print("wrote", IMG / name)
        for scheme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2, color_scheme=scheme)
            pg = ctx.new_page()
            pg.goto(html.as_uri(), wait_until="networkidle")
            pg.wait_for_timeout(400)
            secs = pg.locator("section")
            shots = {"plot": 0, "lift": 1, "script": 3} if scheme == "light" else {"plot": 0}
            for key, idx in shots.items():
                out = IMG / f"page-{key}-{scheme}.png"
                box = secs.nth(idx).bounding_box()
                pad = 20
                pg.set_viewport_size({"width": 1280, "height": int(box["y"] + box["height"] + 2 * pad + 40)})
                box = secs.nth(idx).bounding_box()
                pg.screenshot(path=str(out), clip={"x": box["x"] - pad, "y": box["y"] - pad,
                                                   "width": box["width"] + 2 * pad, "height": box["height"] + 2 * pad})
                print("wrote", out)
            ctx.close()
        b.close()
    print(json.dumps({"tmp_page": str(html)}))


if __name__ == "__main__":
    main()
