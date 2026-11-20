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
 font-family:"IBM Plex Sans",system-ui,sans-serif;display:flex;align-items:center;gap:48px;padding:0 __PAD__px;overflow:hidden}
.l{flex:1;display:flex;flex-direction:column;gap:20px}
.k{font:500 14px "IBM Plex Mono",monospace;letter-spacing:.14em;text-transform:uppercase;color:#6ea0ff}
h1{font:600 __T__px/1.02 "IBM Plex Sans Condensed",sans-serif;letter-spacing:-.01em;max-width:13ch}
p{font-size:__P__px;line-height:1.4;color:#b9c2d0;max-width:34ch}
.cmd{font:500 16px "IBM Plex Mono",monospace;background:#171c24;border:1px solid #2a313d;border-radius:8px;padding:11px 15px;color:#e8ecf2;width:max-content}
.cmd b{color:#3ecf98;font-weight:500}
.r{flex:1.05;display:flex;flex-direction:column;gap:12px}
.card{background:#171c24;border:1px solid #2a313d;border-radius:14px;padding:14px 18px;box-shadow:0 20px 60px rgba(0,0,0,.35)}
.hd{display:flex;justify-content:space-between;align-items:baseline;font:400 12.5px "IBM Plex Mono",monospace;color:#98a2b3;margin-bottom:6px}
.hd b{color:#e8ecf2;font-weight:500;font-size:13.5px}
.n{display:inline-block;width:20px;height:20px;border-radius:50%;background:#2a3a5c;color:#9fc0ff;font:600 12px/20px "IBM Plex Mono",monospace;text-align:center;margin-right:8px}
table{width:100%;border-collapse:collapse;font-size:14px}
td{padding:4px 2px;border-bottom:1px solid #232a35}
td.g{text-align:right;font:500 13.5px "IBM Plex Mono",monospace;white-space:nowrap}
.pos{color:#3ecf98}.neg{color:#ff7b66}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font:400 12.5px "IBM Plex Mono",monospace;border:1px solid #2a313d;border-radius:6px;padding:3px 7px;color:#b9c2d0}
.chip b{color:#e8ecf2;font-weight:500}
.f{font-size:14px;padding:3px 0;color:#d4dae3}.f i{font-style:normal;color:#ff7b66;margin-right:8px;font-family:"IBM Plex Mono",monospace}
</style></head><body>
<div class="l">
  <div class="k">open source · reels, shorts, tiktok</div>
  <h1>Know why your best videos win.</h1>
  <p>reel-decode compares every video on your account and the accounts you study, so you can see what your winners do that your losers don't: the words, the cuts, the captions, the sound. Then it checks your next script before you film it.</p>
  <div class="cmd"><b>$</b> reeldecode page --demo --open</div>
</div>
<div class="r">
  <div class="card">
    <div class="hd"><span><span class="n">1</span><b>What your winners do (and avoid)</b></span><span>winners vs losers, pts</span></div>
    <table>__ROWS__</table>
  </div>
  <div class="card">
    <div class="hd"><span><span class="n">2</span><b>How your __XM__ outlier was made</b></span><span>shot by shot</span></div>
    <div class="chips">__CHIPS__</div>
  </div>
  <div class="card">
    <div class="hd"><span><span class="n">3</span><b>Your next script, before you film</b></span><span>gate check</span></div>
    __FAILS__
  </div>
</div>
</body></html>"""

# Real `reeldecode gate check` output on a sample brief (scripts/make_images.py does not call Jev).
GATE_FAILS = ["no re-hook between hook and reward", "story backbone incomplete (character, conflict, turn)",
              "cta 'comment_keyword' does not fit tofu (allowed: follow, question, save, send)"]


def banner_html(data: dict, w: int, h: int, compact: bool = False) -> str:
    acct = next(a for a in data["accounts"] if a["handle"] == "demo_creator")
    reels = [r for r in data["reels"] if r["a"] == "demo_creator" and r.get("prod") and r["tier"] == "winner"]
    best = sorted(reels, key=lambda r: -(r["xm"] or 0))[0]
    p = best["prod"]
    lifts = sorted([("script", x) for x in acct["lift"][:6]] + [("production", x) for x in acct["prod_lift"][:6]],
                   key=lambda t: -abs(t[1]["gap"]))
    picked, seen = [], set()
    for kind, x in lifts:          # two from the script, two from the production
        if sum(k == kind for k, _ in picked) < 2 and x["value"] not in seen:
            picked.append((kind, x))
            seen.add(x["value"])
        if len(picked) == (3 if compact else 4):
            break
    rows = ""
    for kind, x in picked:
        g = round(x["gap"] * 100)
        name = x["value"].replace("_", " ") if kind == "production" else f'{x["dim"].replace("_", " ")}: {x["value"].replace("_", " ")}'
        rows += f'<tr><td>{name}</td><td class="g {"pos" if g > 0 else "neg"}">{g:+d}</td></tr>'
    chips = [("shots", p["shots"]), ("pace", f'{p["shots_per_10s"]} / 10 s'),
             ("text in 1st second", "yes" if p["text_first_1s"] else "no"), ("captions", p["captions"]),
             ("sound effects", f'{p["sfx"]} ({p["sfx_on_cue"]} on cue)'),
             ("voice", (p.get("voice_source") or "none").replace("_", " ")),
             ("music", (f'{round(p["bpm"])} BPM' if p.get("bpm") else "none"))]
    chips_html = "".join(f'<span class="chip">{k} <b>{v}</b></span>' for k, v in chips[: 5 if compact else 7])
    fails = "".join(f'<div class="f"><i>FAIL</i>{f}</div>' for f in GATE_FAILS[: 2 if compact else 3])
    html = (BANNER.replace("__ROWS__", rows).replace("__CHIPS__", chips_html).replace("__FAILS__", fails)
            .replace("__XM__", f"{best['xm']:.1f}×"))
    html = html.replace("__W__", str(w)).replace("__H__", str(h))
    html = html.replace("__PAD__", "56" if compact else "72").replace("__T__", "60" if compact else "72")
    return html.replace("__P__", "18" if compact else "20")


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
            def section(has, pg=pg):  # the <section> holding this element, found by id, not position
                return pg.locator("section").filter(has=pg.locator(has)).first
            shots = ({"plot": "#plot", "lift": "#lift", "production": "#prodLift", "script": "#detail"}
                     if scheme == "light" else {"plot": "#plot"})
            for key, sel in shots.items():
                out = IMG / f"page-{key}-{scheme}.png"
                box = section(sel).bounding_box()
                pad = 20
                pg.set_viewport_size({"width": 1280, "height": int(box["y"] + box["height"] + 2 * pad + 40)})
                box = section(sel).bounding_box()
                pg.screenshot(path=str(out), full_page=True, clip={"x": box["x"] - pad, "y": box["y"] - pad,
                                                   "width": box["width"] + 2 * pad, "height": box["height"] + 2 * pad})
                print("wrote", out)
            ctx.close()
        b.close()
    print(json.dumps({"tmp_page": str(html)}))


if __name__ == "__main__":
    main()
