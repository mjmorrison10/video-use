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
import argparse, json, math, subprocess, tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("job"); ap.add_argument("src")
ap.add_argument("--pubdir", default="public")
ap.add_argument("--vf", default=None)
ap.add_argument("--fps", type=int, default=30)
ap.add_argument("--handles", type=float, default=0.0,
                help="seconds of extra media kept on each side of every beat, so "
                     "an editor can extend a cut in an NLE (default 0 = exact trim)")
ap.add_argument("--out", default=None, help="output filename (default <job>_src.mp4)")
ap.add_argument("--map", default=None,
                help="write a JSON table of where each beat sits inside the assembled "
                     "file; implies the job's ranges are NOT rewritten")
a = ap.parse_args()

job = json.loads(Path(a.job).read_text())
ranges = sorted(job["ranges"], key=lambda r: r["offsetSec"])
name = a.out or (Path(a.job).stem + "_src.mp4")
out = Path(a.pubdir) / name

src_dur = float(subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.src],
    capture_output=True, text=True, check=True).stdout.strip())

table = []
with tempfile.TemporaryDirectory() as tmp:
    parts = []
    cum_f = 0          # running VIDEO frame count of the assembled file
    for i, r in enumerate(ranges):
        dur = r["outSec"] - r["inSec"]
        # handles are clamped at the media bounds, so the head handle we actually
        # get can be shorter than requested — the map records the real value.
        head = min(a.handles, r["inSec"])
        tail = min(a.handles, max(0.0, src_dur - r["outSec"]))
        start, seglen = r["inSec"] - head, head + dur + tail
        p = Path(tmp) / f"s{i:03d}.mp4"
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}",
               "-i", a.src, "-t", f"{seglen:.3f}"]
        if a.vf:
            cmd += ["-vf", a.vf]
        cmd += ["-r", str(a.fps), "-vsync", "cfr",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                "-ar", "48000", "-ac", "2", str(p)]
        subprocess.run(cmd, check=True)
        parts.append(p)
        # Count VIDEO frames, not format duration: AAC padding runs past the last
        # video frame, so format=duration reads long and that over-estimate
        # compounds into every later clip. Concat with -c copy preserves frame
        # counts, so an integer frame total is exact.
        nframes = int(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
             "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(p)],
            capture_output=True, text=True, check=True).stdout.strip())
        # `-ss` emits the first frame at or AFTER the requested time, so the beat
        # does not land exactly `head` seconds into the part — it lands wherever
        # the master's frame grid put it. Derive the head in master frames so the
        # map points at the real frame instead of a rounded seconds value.
        first_f = math.ceil(start * a.fps - 1e-6)          # first master frame in this part
        head_f = max(0, int(round(r["inSec"] * a.fps)) - first_f)
        table.append({
            "beat": r.get("beat"),
            "masterIn": round(r["inSec"], 3), "masterOut": round(r["outSec"], 3),
            "durSec": round(dur, 3),
            "headHandle": round(head, 3), "tailHandle": round(tail, 3),
            "clipStartFrames": cum_f, "framesInClip": nframes,
            "clipStart": round(cum_f / a.fps, 3),        # start of this clip in the assembled file
            "beatIn": round((cum_f + head_f) / a.fps, 3),  # where the cut actually begins
            "beatOut": round((cum_f + head_f) / a.fps + dur, 3),
            "offsetSec": round(r["offsetSec"], 3),       # position on the output timeline
        })
        cum_f += nframes
    lst = Path(tmp) / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", "-movflags", "+faststart",
                    str(out)], check=True)

mb = out.stat().st_size / 1e6
if a.map:
    # NLE-export mode: leave the job untouched (it may already be rendered) and
    # publish where each beat sits inside the assembled file instead.
    Path(a.map).write_text(json.dumps(
        {"file": name, "handlesSec": a.handles, "fps": a.fps, "segments": table},
        ensure_ascii=False, indent=1))
    print(f"[assemble] {len(ranges)} segments (+{a.handles}s handles) -> {name} "
          f"({mb:.1f}MB), map -> {a.map}")
else:
    # pipeline mode: ranges become sequential in the assembled file
    for r in ranges:
        dur = r["outSec"] - r["inSec"]
        r["inSec"] = round(r["offsetSec"], 3)
        r["outSec"] = round(r["offsetSec"] + dur, 3)
    job["ranges"] = ranges
    job["videoSrc"] = name
    Path(a.job).write_text(json.dumps(job, ensure_ascii=False, indent=1))
    print(f"[assemble] {a.job}: {len(ranges)} segments -> {name} ({mb:.1f}MB)")
