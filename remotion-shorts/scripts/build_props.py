#!/usr/bin/env python3
"""Turn an editorial cut-spec + word transcript into a Remotion job JSON.

The cut-spec lists the chosen source spans (word-boundary in/out seconds). To cut
a filler word mid-span, the editor simply splits that span into two spans that
skip the filler word. This script:
  - computes each span's OUTPUT offset by running sum (like video-use render.py),
  - collects the transcript words inside each span and re-times them to the
    OUTPUT timeline (word-level captions),
  - emits props matching src/Short/schema.ts (shortSchema).

Usage:
  python build_props.py CUTSPEC.json TRANSCRIPT.json -o JOB.json
"""
import argparse
import json
import sys
from pathlib import Path


def load(p):
    return json.loads(Path(p).read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cutspec")
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out", default="job.json")
    args = ap.parse_args()

    spec = load(args.cutspec)
    tr = load(args.transcript)
    words = [w for w in tr.get("words", []) if w.get("type", "word") == "word"
             and w.get("start") is not None and w.get("end") is not None]

    fps = spec.get("fps", 30)
    ranges = []
    captions = []
    offset = 0.0
    for seg in spec["segments"]:
        a = float(seg["inSec"])
        b = float(seg["outSec"])
        dur = b - a
        if dur <= 0:
            print(f"[warn] skipping non-positive span {seg}", file=sys.stderr)
            continue
        ranges.append({
            "inSec": round(a, 3),
            "outSec": round(b, 3),
            "offsetSec": round(offset, 3),
            "framing": seg.get("framing", "cover"),
            "beat": seg.get("beat"),
        })
        for w in words:
            ws, we = float(w["start"]), float(w["end"])
            if ws < a or ws >= b:  # word begins inside this span
                continue
            out_start = (ws - a) + offset
            out_end = (min(we, b) - a) + offset
            if out_end <= out_start:
                out_end = out_start + 0.12
            captions.append({
                "text": w["text"],
                "startMs": round(out_start * 1000),
                "endMs": round(out_end * 1000),
                "timestampMs": round(((out_start + out_end) / 2) * 1000),
            })
        offset += dur

    job = {
        "videoSrc": spec.get("videoSrc", "proxy.mp4"),
        "fps": fps,
        "ranges": ranges,
        "captions": captions,
        "music": spec.get("music"),
        "style": spec.get("style", {}),
        "hook": spec.get("hook"),
    }
    Path(args.out).write_text(json.dumps(job, ensure_ascii=False, indent=1))
    total = offset
    print(f"[props] {len(ranges)} spans, {len(captions)} caption words, "
          f"total output = {total:.2f}s -> {args.out}")
    if not (15 <= total <= 45):
        print(f"[warn] duration {total:.1f}s is outside the 15-45s target",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
