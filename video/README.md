# Demo video harness

Two commands turn this BUIDL into a finished, narrated ~2.5-minute demo with AI voiceover and
background music — no camera or microphone required. Everything project-specific lives in
`config.json` (links, contract, the per-segment `narration` script, `voice`, `music_tags`).

```bash
# 1) capture the visuals (slates + live frontend + verified contract + demo tx on Mantlescan)
python video/make.py            # capture + slates + a quick silent cut -> video/final/demo.mp4

# 2) add voiceover + music and produce the final cut
python video/narrate.py         # generate VO + music (if missing) then mix -> video/final/demo_narrated.mp4
python video/narrate.py --audio # just (re)generate the TTS + music into video/audio/
python video/narrate.py --force # regenerate audio from scratch, then assemble
```

**How the narrated cut works.** Each entry in `config.json.narration` is one segment (`title`,
`frontend`, `explorer`, `tx`, `tech`, `close`). `narrate.py` speaks each line with **Kokoro TTS**
and stretches the matching visual to the length of its narration, so picture and voice stay in
sync, then lays one **ACE-Step** instrumental bed underneath, ducked below the voice. Output is
1280×720 / 30fps, ≥2 minutes — the hackathon's video minimum.

- **Audio engine:** the local ComfyUI at `http://localhost:8188` (Kokoro `GeekyKokoroTTS` +
  ACE-Step `ace_step_v1_3.5b`). Jobs run **one at a time** so the GPU isn't maxed. Change
  `COMFY` at the top of `narrate.py` if ComfyUI runs elsewhere.
- **Record your own voice later (optional):** edit `narration` text, or replace any
  `video/audio/vo_NN_*.flac` with your own recording of the same line and re-run `--assemble`.
  Want a different voice? Set `"voice"` in `config.json` (any Kokoro voice name).
- Requires `ffmpeg` + `ffprobe` + Playwright Chromium. Pi-hole-aware (tracker requests aborted).

Everything under `video/raw/`, `video/audio/`, `video/clips/`, `video/final/`, `video/.tmp_narrate/`
is gitignored.

> **Explorer/transaction visuals:** Mantlescan is behind a Cloudflare human-check that blocks headless capture, so when the live page can't be grabbed, `narrate.py` renders a clean block-explorer-style **card** from the real on-chain data in `config.json` (verified contract + functions for the `explorer` segment; tx hash + outcome for `tx`). Never a Cloudflare screen. If you capture the real pages yourself (logged-in browser), drop them in as `video/raw/explorer.webm` / `video/raw/tx_*.webm` and they take precedence.
