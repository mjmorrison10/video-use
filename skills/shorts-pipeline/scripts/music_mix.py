"""Mix a music track under a rendered clip with sidechain ducking + fades (the formalized
duck chain recovered from the shipped v7/v8), then two-pass loudnorm the final mix to -14 LUFS.

IMPORTANT: pass the PRE-loudnorm <stem>_captioned.mp4 (quiet voice) as CLIP, not the
already-normalized _clean.mp4 — mixing onto the quiet voice preserves the tuned voice/music
balance, and the final loudnorm brings the whole mix up together.

Usage: music_mix.py CAPTIONED.mp4 TRACK.(wav|mp3|m4a) -o CLIP_music.mp4 [--offset 0] [--gain 0.14]
  --offset : start position within the track (s) so its drop lands on the clip's peak
Video is stream-copied; only audio is rebuilt + normalized.
"""
import argparse, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, run, ffprobe_duration, REPO  # noqa
sys.path.insert(0, os.path.join(REPO, "helpers"))
import render as rndr  # noqa

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("track")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--gain", type=float)
    a = ap.parse_args()
    M = load_style()["music"]
    gain = a.gain if a.gain is not None else M["bed_volume"]
    d = M["duck"]
    clip_len = ffprobe_duration(a.clip)
    fout_start = max(0.0, clip_len - M["fade_out_s"])

    music_af = (f"afade=t=in:st=0:d={M['fade_in_s']},"
                f"afade=t=out:st={fout_start:.3f}:d={M['fade_out_s']},"
                f"volume={gain}")
    fc = (
        f"[0:a]asplit=2[v][key];"
        f"[1:a]{music_af}[m];"
        f"[m][key]sidechaincompress=threshold={d['threshold']}:ratio={d['ratio']}:"
        f"attack={d['attack_ms']}:release={d['release_ms']}:makeup={d['makeup']}[md];"
        f"[v][md]amix=inputs=2:normalize=0:duration=first,alimiter=limit={M['limiter']}[a]"
    )
    with tempfile.TemporaryDirectory() as td:
        raw = os.path.join(td, "mix.mp4")
        run(["ffmpeg", "-y",
             "-i", a.clip,
             "-ss", f"{a.offset:.3f}", "-i", a.track,
             "-filter_complex", fc,
             "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-movflags", "+faststart", raw])
        ok = rndr.apply_loudnorm_two_pass(Path(raw), Path(a.out))
        if not ok:
            import shutil; shutil.copy(raw, a.out)
    print(f"[done] {a.out} ({ffprobe_duration(a.out):.2f}s, gain={gain}, offset={a.offset}s, loudnorm={ok})")

if __name__ == "__main__":
    main()
