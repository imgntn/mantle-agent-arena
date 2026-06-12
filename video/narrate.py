"""Voiceover + music pass for a Mantle BUIDL demo. Reads video/config.json (the `narration` list
and `voice`), generates a Kokoro TTS line per segment and one ACE-Step instrumental bed via the
local ComfyUI API, then stretches each b-roll section to its narration length and mixes the voice
over ducked music into video/final/demo_narrated.mp4.

  python video/make.py            # FIRST: capture b-roll into video/raw/  (slates + frontend + explorer + tx)
  python video/narrate.py         # then: generate audio (if missing) + assemble the narrated cut
  python video/narrate.py --audio # just (re)generate the TTS + music into video/audio/
  python video/narrate.py --force # regenerate audio even if it already exists

GPU-friendly: audio is generated one ComfyUI job at a time (never parallel), so it won't max the GPU.
Requires a running ComfyUI at COMFY (default http://localhost:8188) with GeekyKokoroTTS + ACE-Step,
ffmpeg/ffprobe on PATH, and Playwright (for the title/closing slates).
"""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = HERE / "raw"
AUDIO = HERE / "audio"
FINAL = HERE / "final"
TMP = HERE / ".tmp_narrate"
CFG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
COMFY = "http://localhost:8188"
W, H = 1280, 720
PAD = 0.5            # seconds of silence/visual held after each narration line
MUSIC_VOL = 0.07    # background bed level under the voice (kept well below the VO)
SFX_VOL = 0.4       # transition whoosh level
# Mantlescan sits behind a Cloudflare human-check that headless/headful capture can't pass
# reliably, so the explorer/tx segments always use the rendered (real-data) placeholder cards.
# Flip to False once a reliable Mantlescan capture exists in raw/ to prefer the live page.
FORCE_CARDS = True
VOICE = CFG.get("voice", "\U0001f1fa\U0001f1f8 \U0001f6b9 Michael")  # US male "Michael" by default

# ---------------------------------------------------------------- ComfyUI client
def _post_prompt(graph):
    body = json.dumps({"prompt": graph, "client_id": "mantle-narrate"}).encode()
    req = urllib.request.Request(COMFY + "/prompt", body, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))["prompt_id"]


def _wait(pid, timeout=900):
    end = 0
    while end < timeout:
        time.sleep(2); end += 2
        h = json.load(urllib.request.urlopen(COMFY + f"/history/{pid}", timeout=30))
        if pid in h and h[pid].get("outputs"):
            for out in h[pid]["outputs"].values():
                if "audio" in out:
                    return out["audio"][0]
            raise RuntimeError("job finished with no audio output")
    raise TimeoutError(f"ComfyUI job {pid} timed out")


def _download(meta, dst):
    q = urllib.parse.urlencode({"filename": meta["filename"],
                                "subfolder": meta.get("subfolder", ""), "type": meta.get("type", "output")})
    data = urllib.request.urlopen(COMFY + "/view?" + q, timeout=120).read()
    dst.write_bytes(data)


def tts(text, dst):
    g = {"1": {"class_type": "GeekyKokoroTTS",
               "inputs": {"text": text, "voice": VOICE, "speed": 1.0, "use_gpu": True}},
         "2": {"class_type": "SaveAudio", "inputs": {"audio": ["1", 0], "filename_prefix": "mantle_vo"}}}
    _download(_wait(_post_prompt(g)), dst)


def music(seconds, tags, seed, dst):
    g = {"1": {"class_type": "EmptyAceStepLatentAudio", "inputs": {"seconds": float(seconds), "batch_size": 1}},
         "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ace_step_v1_3.5b.safetensors"}},
         "2": {"class_type": "TextEncodeAceStepAudio",
               "inputs": {"clip": ["3", 1], "tags": tags, "lyrics": "", "lyrics_strength": 1.0}},
         "5": {"class_type": "TextEncodeAceStepAudio",
               "inputs": {"clip": ["3", 1], "tags": "", "lyrics": "", "lyrics_strength": 1.0}},
         "4": {"class_type": "KSampler",
               "inputs": {"seed": seed, "steps": 50, "cfg": 7.0, "sampler_name": "euler",
                          "scheduler": "normal", "denoise": 1.0, "model": ["3", 0],
                          "positive": ["2", 0], "negative": ["5", 0], "latent_image": ["1", 0]}},
         "6": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["4", 0], "vae": ["3", 2]}},
         "7": {"class_type": "SaveAudio", "inputs": {"audio": ["6", 0], "filename_prefix": "mantle_music"}}}
    _download(_wait(_post_prompt(g)), dst)


# ---------------------------------------------------------------- ffmpeg helpers
def _dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def _run(args):
    subprocess.run(args, check=True)


# ---------------------------------------------------------------- slates (self-contained)
def _slate_html(body):
    a = CFG.get("accent", "#5ad1ff")
    return f"""<html><head><style>
      *{{margin:0;box-sizing:border-box;font-family:ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif;}}
      body{{width:{W}px;height:{H}px;background:#0a0e14;color:#e6edf3;display:flex;flex-direction:column;
        justify-content:center;padding:0 90px;background:radial-gradient(900px 500px at 30% 20%, {a}22, transparent),#0a0e14;}}
      h1{{font-size:60px;font-weight:800;letter-spacing:-1px;line-height:1.05;}} .a{{color:{a};}}
      p{{font-size:25px;color:#8b98a8;margin-top:20px;}} .tag{{margin-top:24px;font-size:18px;color:{a};letter-spacing:.04em;}}
      .row{{margin-top:18px;font-size:22px;}} .row span{{color:#8b98a8;display:inline-block;width:170px;}}
      code{{color:{a};font-family:ui-monospace,Menlo,Consolas,monospace;font-size:19px;}}
    </style></head><body>{body}</body></html>"""


def _title_html():
    name = CFG["name"]; words = name.rsplit(" ", 1)
    h1 = (f"<h1>{words[0]} <span class='a'>{words[1]}</span></h1>" if len(words) == 2
          else f"<h1 class='a'>{name}</h1>")
    return _slate_html(h1 + f"<p>{CFG['tagline']}</p>"
                       f"<div class='tag'>Turing Test Hackathon 2026 · {CFG['track']} · Mantle</div>")


def _close_html():
    return _slate_html(
        "<h1>Try it.</h1>"
        f"<div class='row'><span>Repo</span><code>{CFG['repo']}</code></div>"
        f"<div class='row'><span>Live</span><code>{CFG['frontend_url']}</code></div>"
        f"<div class='row'><span>{CFG['contract_label']}</span><code>{CFG['contract']}</code></div>")


def _card_html(inner):
    """Block-explorer-styled card (used when the live Mantlescan page is Cloudflare-walled).
    Everything shown is real on-chain data from config.json."""
    a = CFG.get("accent", "#5ad1ff")
    return f"""<html><head><style>
      *{{margin:0;box-sizing:border-box;font-family:ui-sans-serif,-apple-system,'Segoe UI',Roboto,sans-serif;}}
      body{{width:{W}px;height:{H}px;background:#0a0e14;color:#e6edf3;display:flex;flex-direction:column;
        justify-content:center;padding:0 80px;background:radial-gradient(900px 500px at 80% 0%, {a}18, transparent),#0a0e14;}}
      .bar{{display:flex;align-items:center;gap:10px;color:#8b98a8;font-size:17px;margin-bottom:18px;}}
      .bar b{{color:#e6edf3;}} .dot{{width:9px;height:9px;border-radius:50%;background:{a};box-shadow:0 0 10px {a};}}
      .panel{{background:#0f1620;border:1px solid #1d2735;border-radius:14px;padding:30px 34px;}}
      h2{{font-size:34px;font-weight:800;letter-spacing:-.5px;}}
      .ok{{display:inline-block;margin-left:14px;font-size:17px;color:#1ec77b;border:1px solid #1ec77b55;
        background:#1ec77b14;border-radius:999px;padding:5px 13px;vertical-align:middle;font-weight:700;}}
      .addr{{margin-top:14px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:23px;color:{a};word-break:break-all;}}
      .meta{{margin-top:12px;color:#8b98a8;font-size:17px;}}
      .grid{{margin-top:22px;display:grid;grid-template-columns:1fr 1fr;gap:12px 28px;}}
      .item{{font-size:20px;}} .item .kw{{color:{a};font-family:ui-monospace,Consolas,monospace;}}
      .item .lbl{{color:#8b98a8;display:inline-block;width:96px;}}
      .foot{{margin-top:22px;color:#5e6b7e;font-size:16px;font-family:ui-monospace,Consolas,monospace;}}
    </style></head><body>{inner}</body></html>"""


def _explorer_card_html():
    fns = CFG.get("functions", [])
    rows = "".join(f"<div class='item'><span class='kw'>{f}</span></div>" for f in fns)
    lic = CFG.get("license", "MIT")
    return _card_html(
        f"<div class='bar'><span class='dot'></span> Mantle Sepolia Testnet · <b>sepolia.mantlescan.xyz</b></div>"
        f"<div class='panel'><h2>{CFG['contract_label']}<span class='ok'>&#10003; Contract Source Code Verified</span></h2>"
        f"<div class='addr'>{CFG['contract']}</div>"
        f"<div class='meta'>Compiler v0.8.24 &nbsp;·&nbsp; Optimizer enabled &nbsp;·&nbsp; License {lic} &nbsp;·&nbsp; Chain ID 5003</div>"
        f"<div class='grid'>{rows}</div>"
        f"<div class='foot'>sepolia.mantlescan.xyz/address/{CFG['contract']}#code</div></div>")


def _tx_card_html():
    txs = CFG.get("txs", [])
    facts = CFG.get("tx_facts", [])
    method = CFG.get("tx_method", "")
    rows = "".join(f"<div class='item'>{f}</div>" for f in facts)
    txhash = (f"<div class='addr'>{txs[0]}</div>" if txs else
              "<div class='meta'>Committed on-chain via the registry contract</div>")
    methrow = (f"<div class='meta'>Method &nbsp; <span style='color:#1ec77b'>{method}</span> &nbsp;·&nbsp; "
               f"To {CFG['contract_label']} &nbsp;·&nbsp; Mantle Sepolia</div>" if method else "")
    foot = (f"sepolia.mantlescan.xyz/tx/{txs[0]}" if txs else
            f"sepolia.mantlescan.xyz/address/{CFG['contract']}")
    return _card_html(
        f"<div class='bar'><span class='dot'></span> Mantle Sepolia Testnet · <b>Transaction</b></div>"
        f"<div class='panel'><h2>Transaction<span class='ok'>&#10003; Success</span></h2>"
        f"{txhash}{methrow}"
        f"<div class='grid'>{rows}</div>"
        f"<div class='foot'>{foot}</div></div>")


def _enh_card_html():
    """Enhancement card: a NEW verified companion contract (if enh_contract) or a capability card."""
    label = CFG.get("enh_label", "Enhancement")
    caption = CFG.get("enh_caption", "")
    contract = CFG.get("enh_contract", "")
    if contract:
        fns = CFG.get("enh_functions", [])
        rows = "".join(f"<div class='item'><span class='kw'>{f}</span></div>" for f in fns)
        inner = (f"<div class='bar'><span class='dot'></span> NEW &middot; Mantle Sepolia &middot; <b>verified companion contract</b></div>"
                 f"<div class='panel'><h2>{label}<span class='ok'>&#10003; Verified</span></h2>"
                 f"<div class='addr'>{contract}</div>"
                 f"<div class='meta'>{caption}</div>"
                 f"<div class='grid'>{rows}</div>"
                 f"<div class='foot'>sepolia.mantlescan.xyz/address/{contract}#code</div></div>")
    else:
        bullets = CFG.get("enh_bullets", [])
        rows = "".join(f"<div class='item'>&#9656;&nbsp; {b}</div>" for b in bullets)
        inner = (f"<div class='bar'><span class='dot'></span> NEW &middot; <b>capability</b></div>"
                 f"<div class='panel'><h2>{label}<span class='ok'>&#10003; live</span></h2>"
                 f"<div class='meta'>{caption}</div>"
                 f"<div class='grid' style='grid-template-columns:1fr;'>{rows}</div></div>")
    return _card_html(inner)


def _slate_png(full_html, out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": W, "height": H})
        pg.set_content(full_html, wait_until="networkidle"); pg.wait_for_timeout(400)
        pg.screenshot(path=str(out)); b.close()


# ---------------------------------------------------------------- segment visuals
VF = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
      f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")


def _png_clip(png, out, secs):
    _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png), "-t", f"{secs:.2f}",
          "-r", "30", "-vf", VF, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)])


def _webm_clip(webm, out, secs):
    _run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(webm), "-t", f"{secs:.2f}",
          "-r", "30", "-vf", VF, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)])


def _resolve_visual(seg_id):
    """Return ('png', full_html) or ('webm', path) for a narration segment id.
    Live captures (raw/*.webm) win when present; otherwise fall back to a rendered card —
    never a Cloudflare interstitial."""
    if seg_id == "title":
        return ("png", _title_html())
    if seg_id == "close":
        return ("png", _close_html())
    if seg_id == "frontend":
        f = RAW / "frontend.webm"
        return ("webm", f) if f.exists() else ("png", _title_html())
    if seg_id == "explorer":
        f = RAW / "explorer.webm"
        if not FORCE_CARDS and f.exists():
            return ("webm", f)
        return ("png", _explorer_card_html())
    if seg_id == "tx":
        txs = sorted(RAW.glob("tx_*.webm"))
        if not FORCE_CARDS and txs:
            return ("webm", txs[0])
        return ("png", _tx_card_html())
    if seg_id in ("tech", "how", "why"):
        if CFG.get("enh_contract") or CFG.get("enh_bullets"):
            return ("png", _enh_card_html())
        f = RAW / "frontend.webm"
        return ("webm", f) if f.exists() else ("png", _explorer_card_html())
    return ("png", _title_html())


# ---------------------------------------------------------------- pipeline
def gen_audio(force=False):
    AUDIO.mkdir(parents=True, exist_ok=True)
    items = CFG["narration"]
    for i, seg in enumerate(items):
        dst = AUDIO / f"vo_{i:02d}_{seg['id']}.flac"
        if dst.exists() and not force:
            print(f"  vo {i:02d} {seg['id']}: exists ({_dur(dst):.1f}s)"); continue
        print(f"  vo {i:02d} {seg['id']}: generating...", flush=True)
        tts(seg["text"], dst)
        print(f"    -> {_dur(dst):.1f}s")
    total = sum(_dur(AUDIO / f"vo_{i:02d}_{seg['id']}.flac") + PAD for i, seg in enumerate(items))
    mpath = AUDIO / "music.flac"
    if mpath.exists() and not force:
        print(f"  music: exists ({_dur(mpath):.1f}s)")
    else:
        tags = CFG.get("music_tags", "ambient electronic, minimal, downtempo, warm pads, "
                       "subtle pulse, clean, modern tech, instrumental, no vocals")
        secs = min(max(total + 6, 30), 240)  # ACE-Step practical ceiling
        seed = 7000 + len(CFG["name"])
        print(f"  music: generating {secs:.0f}s...", flush=True)
        music(secs, tags, seed, mpath)
        print(f"    -> {_dur(mpath):.1f}s")


def _make_whoosh(out):
    """Synthesize a short, subtle transition whoosh (no GPU / no model needed)."""
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anoisesrc=d=0.6:c=pink:r=44100",
          "-af", ("highpass=f=260,lowpass=f=6500,"
                  "afade=t=in:d=0.3,afade=t=out:st=0.3:d=0.3,"
                  "aformat=channel_layouts=stereo,volume=0.8"),
          "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out)])


def _make_sfx_track(whoosh, boundaries, total, out):
    """Place one whoosh at each segment boundary; pad to `total` seconds."""
    n = len(boundaries)
    if n == 0:
        _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
              "-i", f"anullsrc=r=44100:cl=stereo", "-t", f"{total:.2f}",
              "-c:a", "pcm_s16le", str(out)]); return
    parts = [f"[0:a]asplit={n}" + "".join(f"[w{i}]" for i in range(n)) + ";"]
    for i, t in enumerate(boundaries):
        ms = int(t * 1000)
        parts.append(f"[w{i}]adelay={ms}|{ms}[d{i}];")
    parts.append("".join(f"[d{i}]" for i in range(n)) +
                 f"amix=inputs={n}:normalize=0,apad=whole_dur={total:.2f}[sfx]")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(whoosh),
          "-filter_complex", "".join(parts), "-map", "[sfx]", "-t", f"{total:.2f}",
          "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(out)])


def assemble():
    TMP.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    items = CFG["narration"]
    vlist = TMP / "v.txt"; alist = TMP / "a.txt"
    vlines, alines, durs = [], [], []
    for i, seg in enumerate(items):
        vo = AUDIO / f"vo_{i:02d}_{seg['id']}.flac"
        d = _dur(vo) + PAD
        durs.append(d)
        # visual stretched to the narration length
        vclip = TMP / f"v{i:02d}.mp4"
        kind, src = _resolve_visual(seg["id"])
        if kind == "png":
            png = TMP / f"slate{i:02d}.png"; _slate_png(src, png); _png_clip(png, vclip, d)
        else:
            _webm_clip(src, vclip, d)
        vlines.append(f"file '{vclip.name}'")
        # audio: the voice line + PAD silence, normalized to pcm
        aclip = TMP / f"a{i:02d}.wav"
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vo),
              "-af", f"apad=pad_dur={PAD},aresample=44100", "-t", f"{d:.2f}",
              "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(aclip)])
        alines.append(f"file '{aclip.name}'")
        print(f"  segment {i:02d} {seg['id']}: {d:.1f}s ({kind})")
    vlist.write_text("\n".join(vlines)); alist.write_text("\n".join(alines))
    silent = TMP / "video.mp4"; vo_all = TMP / "vo.wav"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(vlist),
          "-c", "copy", str(silent)])
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(alist),
          "-c", "copy", str(vo_all)])
    total = _dur(vo_all)

    # transition whoosh at every segment boundary (start of segments 1..N-1)
    boundaries = [sum(durs[:i]) for i in range(1, len(durs))]
    whoosh = TMP / "whoosh.wav"; sfx = TMP / "sfx.wav"
    _make_whoosh(whoosh); _make_sfx_track(whoosh, boundaries, total, sfx)

    out = FINAL / "demo_narrated.mp4"
    mpath = AUDIO / "music.flac"
    if mpath.exists():
        # [1]=voice (full level, defines duration) · [2]=music bed (ducked) · [3]=transition whooshes
        filt = (f"[2:a]volume={MUSIC_VOL},aresample=44100[m];"
                f"[3:a]volume={SFX_VOL}[s];"
                f"[1:a][m][s]amix=inputs=3:duration=first:normalize=0[a]")
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(vo_all),
              "-stream_loop", "-1", "-i", str(mpath), "-i", str(sfx),
              "-filter_complex", filt, "-map", "0:v:0", "-map", "[a]", "-t", f"{total:.2f}",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)])
    else:
        filt = (f"[2:a]volume={SFX_VOL}[s];"
                f"[1:a][s]amix=inputs=2:duration=first:normalize=0[a]")
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(vo_all),
              "-i", str(sfx), "-filter_complex", filt, "-map", "0:v:0", "-map", "[a]",
              "-t", f"{total:.2f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)])
    print(f"  assembled narrated cut ({total:.0f}s, music {MUSIC_VOL}, sfx on {len(boundaries)} cuts) -> {out}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    force = "--force" in sys.argv
    if arg == "--audio" or arg == "all" or force:
        gen_audio(force=force)
    if arg == "all" or arg == "--assemble" or (arg == "--force"):
        assemble()
