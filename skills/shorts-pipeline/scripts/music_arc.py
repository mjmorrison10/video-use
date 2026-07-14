"""Score a clip so the music BUILDS and then CUTS right before a climax moment, per the
'end the music right before the climax' brief. The track passage is chosen (via --offset) so
its own crescendo crests at the climax; a rising volume envelope adds the climb; sidechain
ducking keeps the voice clear; the music covers only [0, END] of the clip, leaving the climax
line to land dry. Final two-pass loudnorm to -14 LUFS.

Pass the PRE-loudnorm <stem>_captioned.mp4 as CLIP (see music_mix.py).

Usage: music_arc.py CAPTIONED.mp4 TRACK -o OUT --offset OFF --end T [--lo 0.09 --hi 0.20]
  --offset : track start (s); pick so the track's crest lands at --end
  --end    : output time (s) the music should finish/crest at (right before the climax word)
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
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--lo", type=float, default=0.20)
    ap.add_argument("--hi", type=float, default=0.42)
    ap.add_argument("--fade-out", type=float, default=0.9)
    ap.add_argument("--duck-ratio", type=float, default=3.0)
    ap.add_argument("--duck-thresh", type=float, default=0.11)
    a = ap.parse_args()
    M = load_style()["music"]
    T = a.end
    fo = a.fade_out
    # rising swell over [0,T] (the "climb"), then fade out finishing exactly at T
    music_af = (f"afade=t=in:st=0:d=0.6,"
                f"volume='min({a.hi},{a.lo}+({a.hi}-{a.lo})*t/{T})':eval=frame,"
                f"afade=t=out:st={max(0.0,T-fo):.3f}:d={fo}")
    # gentle ducking only (voice stays clear, but the cinematic bed remains clearly present)
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
             "-ss", f"{a.offset:.3f}", "-t", f"{T:.3f}", "-i", a.track,
             "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", raw])
        ok = rndr.apply_loudnorm_two_pass(Path(raw), Path(a.out))
        if not ok:
            import shutil; shutil.copy(raw, a.out)
    print(f"[done] {a.out} ({ffprobe_duration(a.out):.2f}s, music [0,{T:.1f}]s offset={a.offset}s loudnorm={ok})")

if __name__ == "__main__":
    main()
