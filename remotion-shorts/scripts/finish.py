#!/usr/bin/env python3
"""Final encode: house grade + loudness. Run on every render before delivery.

The Remotion render is deliberately flat and at whatever level the mix landed on.
This applies the two finishing passes the client does by hand otherwise:

  grade  an HDR-style contrast expansion. Values are not taste — they were fit
         to his own finished cut, whose luma sits at p5 26 / p95 207 / std 53.5
         where our ungraded render was p5 65 / p95 186 / std 41.
  audio  loudnorm to -14 LUFS, so it is loud on a phone.

Usage: finish.py RAW.mp4 OUT.mp4 [--no-grade] [--lufs -14]
"""
import argparse, subprocess, sys

# Fit against the reference cut; see CLAUDE.md "Look".
GRADE = "eq=contrast=1.34:saturation=1.06:gamma=0.92,unsharp=5:5:0.4"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--crf", type=int, default=18)
    a = ap.parse_args()

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", a.src]
    if a.no_grade:
        cmd += ["-c:v", "copy"]
    else:
        cmd += ["-vf", GRADE, "-c:v", "libx264", "-crf", str(a.crf),
                "-preset", "slow", "-pix_fmt", "yuv420p"]
    cmd += ["-af", f"loudnorm=I={a.lufs}:TP=-1.0:LRA=11",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)

    def probe(p, key):
        return subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", key, "-of", "csv=p=0", p],
            capture_output=True, text=True, check=True).stdout.strip()

    print(f"[finish] {a.out}  {probe(a.out,'format=duration')}s  "
          f"{probe(a.out,'stream=width,height').splitlines()[0]}"
          f"{'' if a.no_grade else '  graded'}  {a.lufs} LUFS")


if __name__ == "__main__":
    sys.exit(main())
