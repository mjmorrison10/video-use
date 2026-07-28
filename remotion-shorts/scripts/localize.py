#!/usr/bin/env python3
"""Give a job its own SMALL source window so Remotion seeks a tiny file (fast).
Extracts [minIn-pad, maxOut+pad] from the full source, re-encodes (frame-accurate,
faststart), and rewrites the job's range inSec/outSec relative to that window.
Caption/offset (output-time) values are untouched.

Usage: localize.py JOB.json FULL_SRC.mp4 --pubdir public/ [--pad 0.25]
"""
import argparse, json, subprocess, sys
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument("job"); ap.add_argument("src")
ap.add_argument("--pubdir", default="public")
ap.add_argument("--pad", type=float, default=0.25)
ap.add_argument("--vf", default=None,
                help="optional ffmpeg -vf filter chain applied to the window "
                     "(e.g. 'crop=308:548:1226:266,scale=1080:1920')")
a=ap.parse_args()
job=json.loads(Path(a.job).read_text())
ranges=job["ranges"]
lo=min(r["inSec"] for r in ranges); hi=max(r["outSec"] for r in ranges)
start=max(0.0, lo-a.pad); dur=(hi+a.pad)-start
name=Path(a.job).stem + "_src.mp4"
out=Path(a.pubdir)/name
cmd=["ffmpeg","-y","-v","error","-ss",f"{start:.3f}","-i",a.src,"-t",f"{dur:.3f}",
     "-vf","scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
     "-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",
     "-c:a","aac","-b:a","160k","-movflags","+faststart",str(out)]
# NOTE: we do NOT pre-crop here (framing handled in React). Keep full 16:9 frame.
cmd=["ffmpeg","-y","-v","error","-ss",f"{start:.3f}","-i",a.src,"-t",f"{dur:.3f}"]
# Optional pre-crop/scale (e.g. isolating one panel of a side-by-side remote call
# and delivering it already 9:16, so the React layer just covers a vertical source).
if a.vf:
    cmd+=["-vf",a.vf]
cmd+=["-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",
      "-c:a","aac","-b:a","160k","-movflags","+faststart",str(out)]
subprocess.run(cmd, check=True)
for r in ranges:
    r["inSec"]=round(r["inSec"]-start,3); r["outSec"]=round(r["outSec"]-start,3)
job["videoSrc"]=name
Path(a.job).write_text(json.dumps(job,ensure_ascii=False,indent=1))
mb=out.stat().st_size/1e6
print(f"[localize] {a.job}: window [{start:.2f}+{dur:.2f}s] -> {name} ({mb:.1f}MB), {len(ranges)} ranges remapped")
