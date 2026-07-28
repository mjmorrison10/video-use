#!/usr/bin/env python3
"""Build a Remotion job from a FINISHED cut + a hand-edited SRT.

This is the "human already cut it" path: the video is the edit (one full-length
range, no snapping, no face-tracking, no assembly) and the SRT is the caption
truth. All the pipeline still supplies is the house style — serif/cyan captions,
hook overlay, CTA card.

Usage: build_final_job.py --video NAME.mp4 --srt FIXED.srt -o jobs/x.json
                          [--cta-text T] [--cta-sub S] [--cta-dur 1.8]
                          [--hook TEXT] [--hook-until 1.4] [--music SRC]
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from srt_to_pages import parse, to_pages  # noqa: E402

clean = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())

# Lit in cyan with a neon glow. Money and the deprivation/payoff spikes only —
# lighting every noun destroys the scarcity that makes a glow mean something.
POWER = ["bankrupt", "160000", "10000", "education", "bush", "recurring",
         "client", "daughters", "anybody", "ai"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="filename inside public/")
    ap.add_argument("--srt", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--cta-text"); ap.add_argument("--cta-sub")
    ap.add_argument("--cta-dur", type=float, default=1.8)
    ap.add_argument("--cta-line", action="append", default=[],
                    help="extra CTA line under --cta-sub; repeatable, last one is the ask")
    ap.add_argument("--hook"); ap.add_argument("--hook-until", type=float, default=1.4)
    ap.add_argument("--music", default=None, help="omit when the cut already has a mix")
    ap.add_argument("--music-start", type=float, default=0.0)
    ap.add_argument("--vol-low", type=float, default=0.09)
    ap.add_argument("--vol-high", type=float, default=0.14)
    ap.add_argument("--climax", type=float, default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--power", default=None, help="comma list to override power words")
    a = ap.parse_args()

    src = Path("public") / a.video
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
        capture_output=True, text=True, check=True).stdout.strip())

    pages = to_pages(parse(Path(a.srt).read_text(encoding="utf-8-sig")))
    if not pages:
        sys.exit("no caption pages parsed")
    last = pages[-1]["endMs"] / 1000
    if last > dur + 0.05:
        sys.exit(f"captions run {last:.2f}s past the {dur:.2f}s video")

    power = [p.strip() for p in a.power.split(",")] if a.power else POWER
    vocab = {clean(t["text"]) for p in pages for t in p["tokens"]}
    missing = [w for w in power if w not in vocab]
    if missing:
        print(f"[warn] power words never appear in the captions: {missing}", file=sys.stderr)

    job = {
        "videoSrc": a.video,
        "fps": a.fps,
        # the human's cut IS the edit — one range, straight through
        "ranges": [{"inSec": 0.0, "outSec": round(dur, 3), "offsetSec": 0.0,
                    "framing": "cover", "cropX": 0.5, "cropXEnd": None,
                    "cropPanSec": None, "mute": False, "beat": "FINAL CUT"}],
        "captionPages": pages,
        "music": ({"src": a.music, "startSec": a.music_start,
                   "volLow": a.vol_low, "volHigh": a.vol_high,
                   "climaxSec": a.climax} if a.music else None),
        "style": {
            "highlightColor": "#00E5FF", "accentColor": "#00E5FF",
            "textColor": "white", "strokeColor": "black", "fontSize": 58,
            "captionPosition": "bottom", "captionBottom": 420,
            "uppercase": True, "powerWords": power,
        },
        "hook": ({"text": a.hook, "untilSec": a.hook_until} if a.hook else None),
        "broll": [], "zooms": [], "zoomSteps": [],
        "cta": ({"text": a.cta_text, "sub": a.cta_sub, "durSec": a.cta_dur,
                 "lines": a.cta_line}
                if a.cta_text else None),
    }
    Path(a.out).write_text(json.dumps(job, ensure_ascii=False, indent=1))
    lit = sum(1 for p in pages for t in p["tokens"] if clean(t["text"]) in set(power))
    print(f"[final] {len(pages)} pages, {lit} power words lit, video {dur:.2f}s"
          f"{' + ' + str(a.cta_dur) + 's CTA' if a.cta_text else ''} -> {a.out}")


if __name__ == "__main__":
    main()
