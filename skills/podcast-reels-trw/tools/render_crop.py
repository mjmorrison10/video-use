"""Per-shot auto-crop 9:16 renderer with ASS captions.

For each EDL range:
  - reframe.analyze -> SHOTS (segments between scene cuts), each with a face
    anchor + size.
  - VIDEO: extract each shot with its OWN static crop (adaptive zoom from the
    shot's face size, anchor placed on the template crosshair) + scale to
    1080x1920 + grade. Concat the shot videos.
  - AUDIO: extract the whole range once, continuous, with 30ms fades only at the
    range edges (real cut boundaries) — so internal shot cuts don't dip.
  - Mux video+audio into the range segment.
Then: concat range segments (Rule 2) -> burn ASS captions LAST (Rule 1) -> loudnorm.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as P         # noqa: E402
HELPERS = P.helpers_dir()
sys.path.insert(0, str(HELPERS))
import render as R          # noqa: E402
import reframe as RF        # noqa: E402
import ass_captions as AC   # noqa: E402

OUT_W, OUT_H = 1080, 1920
NOSE_FX, NOSE_FY = 0.508, 0.314      # anchor target from the user's template
TARGET_FACE = 600.0
S_MIN, S_MAX = 1.9, 3.6


def crop_dims(face_h, smax=S_MAX):
    s = min(smax, max(S_MIN, TARGET_FACE / max(1.0, face_h)))
    cw = int(round(OUT_W / s / 2) * 2)
    ch = int(round(OUT_H / s / 2) * 2)
    return min(cw, RF.SRC_W), min(ch, RF.SRC_H)


def _run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def extract_shot_video(source, abs_start, dur, ax, ay, face_h, coverage, grade, out, preview, punch=False):
    smax = S_MAX if coverage >= 0.65 else 2.3
    cw, ch = crop_dims(face_h, smax)
    x = int(min(max(0.0, ax - NOSE_FX * cw), RF.SRC_W - cw))
    y = int(min(max(0.0, ay - NOSE_FY * ch), RF.SRC_H - ch))
    # reframe computes anchors/dims in a normalized SRC_W×SRC_H (1920×1080) space
    # (it resizes frames internally), so normalize the real frame to that space
    # first — makes the crop correct for ANY source resolution (e.g. 1280×720).
    vf = f"scale={RF.SRC_W}:{RF.SRC_H},crop={cw}:{ch}:{x}:{y},scale={OUT_W}:{OUT_H}"
    if grade:
        vf += f",{grade}"
    if punch:   # zoom-punch transition at a speaker/scene cut: 1.12x -> 1.0x over ~4 frames
        z = "max(1,1.12-0.033*n)"
        vf += f",scale=w='{OUT_W}*{z}':h='{OUT_H}*{z}':eval=frame,crop={OUT_W}:{OUT_H}"
    preset, crf = ("medium", "22") if preview else ("fast", "20")
    _run(["ffmpeg", "-y", "-ss", f"{abs_start:.3f}", "-i", str(source), "-t", f"{dur:.3f}",
          "-an", "-vf", vf, "-c:v", "libx264", "-preset", preset, "-crf", crf,
          "-pix_fmt", "yuv420p", "-r", "24", "-video_track_timescale", "12288", str(out)])


def extract_range_audio(source, abs_start, dur, out):
    fade_out = max(0.0, dur - 0.03)
    af = f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out:.3f}:d=0.03"
    _run(["ffmpeg", "-y", "-ss", f"{abs_start:.3f}", "-i", str(source), "-t", f"{dur:.3f}",
          "-vn", "-af", af, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)])


def extract_range(source, r_start, r_dur, shots, grade, out_seg, edit_dir, idx, preview):
    tmp = edit_dir / "clips_graded"
    tmp.mkdir(parents=True, exist_ok=True)
    shot_vids = []
    for si, sh in enumerate(shots):
        s0 = max(0.0, sh["start"]); s1 = min(r_dur, sh["end"])
        if s1 - s0 < 0.06:
            continue
        v = tmp / f"seg_{idx:02d}_shot_{si:02d}.mp4"
        extract_shot_video(source, r_start + s0, s1 - s0, sh["ax"], sh["ay"],
                           sh["face_h"], sh["coverage"], grade, v, preview, punch=(si > 0))
        shot_vids.append(v)
    if not shot_vids:
        return False
    # concat shot videos (video only)
    vlist = edit_dir / f"_v{idx}.txt"
    vlist.write_text("".join(f"file '{p.resolve()}'\n" for p in shot_vids))
    vcat = tmp / f"seg_{idx:02d}_v.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(vlist), "-c", "copy", str(vcat)])
    vlist.unlink(missing_ok=True)
    # continuous audio for the whole range
    acat = tmp / f"seg_{idx:02d}_a.m4a"
    extract_range_audio(source, r_start, r_dur, acat)
    # mux
    _run(["ffmpeg", "-y", "-i", str(vcat), "-i", str(acat), "-map", "0:v", "-map", "1:a",
          "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(out_seg)])
    return True


def burn_ass(base_path, ass_path, out_path):
    ass_abs = str(ass_path.resolve()).replace(":", r"\:")
    _run(["ffmpeg", "-y", "-i", str(base_path), "-filter_complex", f"[0:v]ass='{ass_abs}'[outv]",
          "-map", "[outv]", "-map", "0:a", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
          "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(out_path)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--no-loudnorm", action="store_true")
    args = ap.parse_args()

    edl_path = args.edl.resolve()
    edl = json.loads(edl_path.read_text())
    edit_dir = edl_path.parent
    out_path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    grade = R.resolve_grade_filter(edl.get("grade"))
    grade = "" if grade == "__AUTO__" else grade
    sources = edl["sources"]

    seg_paths = []
    for i, r in enumerate(edl["ranges"]):
        src_path = R.resolve_path(sources[r["source"]], edit_dir)
        start = float(r["start"]); end = float(r["end"]); dur = end - start
        rf = RF.analyze(src_path, start, end)
        out_seg = edit_dir / "clips_graded" / f"seg_{i:02d}.mp4"
        print(f"  [{i:02d}] {start:.2f}-{end:.2f} ({dur:.1f}s) {len(rf['shots'])} shots", flush=True)
        if extract_range(src_path, start, dur, rf["shots"], grade, out_seg, edit_dir, i, args.preview):
            seg_paths.append(out_seg)

    base = edit_dir / ("base_preview.mp4" if args.preview else "base.mp4")
    R.concat_segments(seg_paths, base, edit_dir)

    ass_path = edit_dir / "master.ass"
    AC.write_ass(AC.build_events(edl, edit_dir), ass_path)

    if args.no_loudnorm:
        burn_ass(base, ass_path, out_path)
    else:
        tmp = out_path.with_suffix(".prenorm.mp4")
        burn_ass(base, ass_path, tmp)
        R.apply_loudnorm_two_pass(tmp, out_path, preview=args.preview)
        tmp.unlink(missing_ok=True)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\ndone: {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
