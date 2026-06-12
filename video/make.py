"""One-command demo b-roll for a Mantle BUIDL. Reads video/config.json, renders title/closing
slates, captures the live frontend + the verified contract on Mantlescan, and stitches a cut.

  python video/make.py            # slates + capture + assemble  -> video/final/demo.mp4
  python video/make.py --capture  # just the screen b-roll
  python video/make.py --assemble # just stitch what's in video/raw + clips/host

Drop your talking-head clips in video/clips/host/ (01_intro.mp4, 02_outro.mp4) and they're
spliced in automatically. Pi-hole aware (aborts tracker requests). ffmpeg + Playwright required.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = HERE / "raw"
FINAL = HERE / "final"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
W, H = 1280, 720
EXPLORER = "https://sepolia.mantlescan.xyz"
TRACKERS = ("cloudflareinsights", "google-analytics", "googletagmanager", "doubleclick",
            "facebook", "hotjar", "sentry", "scorecardresearch", "quantserve")


def _slate_html(title_html, rows_html):
    a = CFG.get("accent", "#5ad1ff")
    return f"""<html><head><style>
      *{{margin:0;box-sizing:border-box;font-family:ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif;}}
      body{{width:{W}px;height:{H}px;background:#0a0e14;color:#e6edf3;display:flex;flex-direction:column;
        justify-content:center;padding:0 90px;background:radial-gradient(900px 500px at 30% 20%, {a}22, transparent),#0a0e14;}}
      h1{{font-size:60px;font-weight:800;letter-spacing:-1px;line-height:1.05;}} .a{{color:{a};}}
      p{{font-size:25px;color:#8b98a8;margin-top:20px;}} .tag{{margin-top:24px;font-size:18px;color:{a};letter-spacing:.04em;}}
      .row{{margin-top:18px;font-size:22px;}} .row span{{color:#8b98a8;display:inline-block;width:150px;}}
      code{{color:{a};font-family:ui-monospace,Menlo,Consolas,monospace;font-size:19px;}}
    </style></head><body>{title_html}{rows_html}</body></html>"""


def _png(html, out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.set_content(html, wait_until="networkidle"); pg.wait_for_timeout(400)
        pg.screenshot(path=str(out)); b.close()


def _clip(png, out, secs):
    if out.exists(): out.unlink()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(secs), "-r", "30",
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)


def slates():
    RAW.mkdir(parents=True, exist_ok=True)
    name = CFG["name"]; words = name.rsplit(" ", 1)
    title_html = (f"<h1>{words[0]} <span class='a'>{words[1]}</span></h1>" if len(words) == 2
                  else f"<h1 class='a'>{name}</h1>")
    title = _slate_html(title_html + f"<p>{CFG['tagline']}</p>",
                        f"<div class='tag'>Turing Test Hackathon 2026 · {CFG['track']} · Mantle</div>")
    close = _slate_html("<h1>Try it.</h1>",
        f"<div class='row'><span>Repo</span><code>{CFG['repo']}</code></div>"
        f"<div class='row'><span>Live</span><code>{CFG['frontend_url']}</code></div>"
        f"<div class='row'><span>{CFG['contract_label']}</span><code>{CFG['contract']}</code></div>")
    for nm, html, secs in [("slate_title", title, 7), ("slate_close", close, 8)]:
        png = RAW / f"{nm}.png"; _png(html, png); _clip(png, RAW / f"{nm}.mp4", secs); png.unlink()
        print(f"  rendered {nm}.mp4")


def _route(route):
    route.abort() if any(t in route.request.url for t in TRACKERS) else route.continue_()


def capture():
    RAW.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    frontend = (ROOT / "docs" / "index.html").as_uri()
    shots = [("frontend", frontend, 4, 3), ("explorer", f"{EXPLORER}/address/{CFG['contract']}#code", 4, 3)]
    for tx in CFG.get("txs", [])[:2]:
        shots.append((f"tx_{tx[:8]}", f"{EXPLORER}/tx/{tx}", 3, 2))
    with sync_playwright() as p:
        for name, url, wait, scrolls in shots:
            ctx = p.chromium.launch(headless=True).new_context(
                viewport={"width": W, "height": H},
                record_video_dir=str(RAW), record_video_size={"width": W, "height": H})
            ctx.route("**/*", _route)
            pg = ctx.new_page()
            try:
                pg.goto(url, wait_until="domcontentloaded", timeout=45000)
                pg.wait_for_timeout(wait * 1000)
                for _ in range(scrolls):
                    pg.evaluate("window.scrollBy(0, 360)"); pg.wait_for_timeout(1100)
            except Exception as e:
                print(f"  ({name} slow: {e})")
            vp = Path(pg.video.path()); pg.close(); ctx.close()
            dst = RAW / f"{name}.webm"
            if dst.exists(): dst.unlink()
            vp.rename(dst); print(f"  captured {name}.webm")


def assemble():
    FINAL.mkdir(parents=True, exist_ok=True)
    host = HERE / "clips" / "host"
    order = [RAW / "slate_title.mp4", host / "01_intro.mp4", RAW / "frontend.webm",
             RAW / "explorer.webm"]
    order += sorted(RAW.glob("tx_*.webm"))
    order += [host / "02_outro.mp4", RAW / "slate_close.mp4"]
    tmp = HERE / ".tmp"; tmp.mkdir(exist_ok=True)
    listf = tmp / "concat.txt"; lines = []; i = 0
    for clip in order:
        if not clip.exists():
            if "host" in str(clip): print(f"  (skip missing host clip {clip.name})")
            continue
        norm = tmp / f"{i:02d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip),
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", str(norm)], check=True)
        lines.append(f"file '{norm.name}'"); i += 1
    if not i:
        print("  nothing to assemble — run --capture first"); return
    listf.write_text("\n".join(lines))
    out = FINAL / "demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(listf), "-c", "copy", str(out)], check=True)
    print(f"  assembled {i} clips -> {out}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg in ("--capture", "all"): capture()
    if arg in ("all",): slates()
    if arg in ("--slates",): slates()
    if arg in ("--assemble", "all"): assemble()
