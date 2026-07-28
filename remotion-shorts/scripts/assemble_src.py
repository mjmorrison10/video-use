#!/usr/bin/env python3
"""Assemble a TINY source containing ONLY the footage a job uses, in output order.

localize.py extracts one contiguous [min..max] window, which is useless when a
job samples beats from across a whole interview (e.g. 360s..4443s would extract
68 minutes). This instead cuts each range out, concatenates them in output order,
and rewrites the ranges to be sequential — so range inSec == its offsetSec and
Remotion seeks a ~40s file.

Optional --vf is applied to every segment (e.g. isolating one panel of a
side-by-side call and delivering it already 9:16).

Usage: assemble_src.py JOB.json SRC.mp4 [--pubdir public] [--vf FILTER] [--fps 30]
"""
import argparse, json, subprocess, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("job"); ap.add_argument("src")
ap.add_argument("--pubdir", default="public")
ap.add_argument("--vf", default=None)
ap.add_argument("--fps", type=int, default=30)
a = ap.parse_args()

job = json.loads(Path(a.job).read_text())
ranges = sorted(job["ranges"], key=lambda r: r["offsetSec"])
name = Path(a.job).stem + "_src.mp4"
out = Path(a.pubdir) / name

with tempfile.TemporaryDirectory() as tmp:
    parts = []
    for i, r in enumerate(ranges):
        dur = r["outSec"] - r["inSec"]
        p = Path(tmp) / f"s{i:03d}.mp4"
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{r['inSec']:.3f}",
               "-i", a.src, "-t", f"{dur:.3f}"]
        if a.vf:
            cmd += ["-vf", a.vf]
        cmd += ["-r", str(a.fps), "-vsync", "cfr",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                "-ar", "48000", "-ac", "2", str(p)]
        subprocess.run(cmd, check=True)
        parts.append(p)
    lst = Path(tmp) / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", "-movflags", "+faststart",
                    str(out)], check=True)

# ranges become sequential in the assembled file
for r in ranges:
    dur = r["outSec"] - r["inSec"]
    r["inSec"] = round(r["offsetSec"], 3)
    r["outSec"] = round(r["offsetSec"] + dur, 3)
job["ranges"] = ranges
job["videoSrc"] = name
Path(a.job).write_text(json.dumps(job, ensure_ascii=False, indent=1))
mb = out.stat().st_size / 1e6
print(f"[assemble] {a.job}: {len(ranges)} segments -> {name} ({mb:.1f}MB)")
