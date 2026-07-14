"""Score a clip with a story-arc music bed that runs the FULL length: it climbs to a crest at
the climax moment (--climax), then falls to a softer ending. The track passage is chosen (via
--offset) so its own crescendo also crests at the climax; gentle sidechain ducking keeps the
voice clear while the cinematic bed stays present. Final two-pass loudnorm to -14 LUFS.

Pass the PRE-loudnorm <stem>_captioned.mp4 as CLIP (see music_mix.py).

Usage: music_arc.py CAPTIONED.mp4 TRACK -o OUT --offset OFF --climax T [--lo .14 --hi .26 --end .11]
  --offset : track start (s); pick so the track's own crest lands at --climax
  --climax : output time (s) the swell should crest at (the key line); music then falls to the end
"""
import argparse, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, run, ffprobe_duration, REPO  # noqa
sys.path.insert(0, os.path.join(REPO, "helpers"))
import render as rndr  # noqa

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip"); ap.add_argument("track")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--climax", type=float, required=True)
    ap.add_argument("--lo", type=float, default=0.14)    # bed gain at the start
    ap.add_argument("--hi", type=float, default=0.26)    # bed gain at the crest (climax)
    ap.add_argument("--end", type=float, default=0.11)   # bed gain at the ending
    ap.add_argument("--duck-ratio", type=float, default=3.0)
    ap.add_argument("--duck-thresh", type=float, default=0.11)
    a = ap.parse_args()
    M = load_style()["music"]
    clip_len = ffprobe_duration(a.clip)
    T = min(a.climax, clip_len - 0.5)
    fo = 1.0
    # story arc: climb lo->hi over [0,T], then fall hi->end over [T,clip_len]; fade in/out at edges
    vol = (f"volume='if(lt(t,{T}),{a.lo}+({a.hi}-{a.lo})*t/{T},"
           f"{a.hi}+({a.end}-{a.hi})*(t-{T})/({clip_len}-{T}))':eval=frame")
    music_af = (f"afade=t=in:st=0:d=0.6,{vol},"
                f"afade=t=out:st={max(0.0,clip_len-fo):.3f}:d={fo}")
    fc = (
        f"[0:a]asplit=2[v][key];"
        f"[1:a]{music_af}[m];"
        f"[m][key]sidechaincompress=threshold={a.duck_thresh}:ratio={a.duck_ratio}:"
        f"attack=20:release=320:makeup=1[md];"
        f"[v][md]amix=inputs=2:normalize=0:duration=first,alimiter=limit={M['limiter']}[a]"
    )
    with tempfile.TemporaryDirectory() as td:
        raw = os.path.join(td, "mix.mp4")
        run(["ffmpeg", "-y", "-i", a.clip,
             "-ss", f"{a.offset:.3f}", "-i", a.track,
             "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", raw])
        ok = rndr.apply_loudnorm_two_pass(Path(raw), Path(a.out))
        if not ok:
            import shutil; shutil.copy(raw, a.out)
    print(f"[done] {a.out} ({ffprobe_duration(a.out):.2f}s, full-length, crest@{T:.1f}s offset={a.offset}s loudnorm={ok})")

if __name__ == "__main__":
    main()
