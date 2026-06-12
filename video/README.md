# Demo video harness

One command turns this BUIDL into ~1-minute b-roll; record two short talking-head clips and
you have a full demo. Config-driven — everything specific to this project is in `config.json`.

```bash
python video/make.py            # slates + capture frontend & explorer + assemble -> video/final/demo.mp4
python video/make.py --capture  # just the screen b-roll
python video/make.py --slates   # just title/closing cards
python video/make.py --assemble # just stitch what's in raw/ + clips/host/
```

- **Auto-captured (no wallet):** the live frontend reading on-chain state, the verified contract on
  Mantlescan, and the demo transaction(s) from `config.json`. Pi-hole-aware (tracker requests aborted).
- **Your part:** drop `video/clips/host/01_intro.mp4` and `02_outro.mp4` (record yourself, 16:9) and
  they splice in automatically. Re-run `--assemble`.
- Requires `ffmpeg` + Playwright Chromium. Outputs to `video/final/demo.mp4` (1280×720, 30fps).

Everything under `video/raw/`, `video/clips/`, `video/final/`, `video/.tmp/` is gitignored.
