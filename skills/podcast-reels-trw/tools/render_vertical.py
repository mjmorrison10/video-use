"""Vertical (9:16) blurred-fill renderer for podcast clips.

Reuses video-use/helpers/render.py for everything that must stay hard-rule
correct — lossless per-segment concat, output-timeline master SRT (Rule 5),
subtitles-LAST compositing (Rule 1), loudnorm — and ONLY overrides the
per-segment extraction so each segment is composed as a 1080x1920 blurred-fill
layout: the 16:9 frame centered and sharp over a blurred, cover-scaled copy of
itself.

30ms audio fades at every segment edge are preserved (Rule 3). Cuts must be
placed on word boundaries by the EDL author (Rule 6/7).

Usage:
    python render_vertical.py <edl.json> -o out.mp4 --build-subtitles
    python render_vertical.py <edl.json> -o out.mp4 --preview --build-subtitles
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as P  # noqa: E402
HELPERS = P.helpers_dir()
sys.path.insert(0, str(HELPERS))

import render as R  # noqa: E402  (reuse the hard-rule-correct pipeline)


def extract_segment_vertical(
    source: Path,
    seg_start: float,
    duration: float,
    grade_filter: str,
    out_path: Path,
    preview: bool = False,
    draft: bool = False,
) -> None:
    """Extract a range as a 1080x1920 blurred-fill segment with 30ms fades."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if draft:
        W, H = 720, 1280
        preset, crf = "ultrafast", "28"
    elif preview:
        W, H = 1080, 1920
        preset, crf = "medium", "22"
    else:
        W, H = 1080, 1920
        preset, crf = "fast", "20"

    src_label = "[0:v]"
    pre = ""
    if R.is_hdr_source(source):
        pre = f"[0:v]{R.TONEMAP_CHAIN}[src];"
        src_label = "[src]"

    fg_chain = f"scale={W}:-2"
    if grade_filter:
        fg_chain += f",{grade_filter}"

    # background: cover-scale + crop to full frame, then blur
    # foreground: fit to width, sharp, centered
    vf = (
        f"{pre}"
        f"{src_label}split=2[bg][fg];"
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},gblur=sigma=20[bgb];"
        f"[fg]{fg_chain}[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[outv]"
    )

    fade_out_start = max(0.0, duration - 0.03)
    aud = (
        f"[0:a]afade=t=in:st=0:d=0.03,"
        f"afade=t=out:st={fade_out_start:.3f}:d=0.03[outa]"
    )

    filter_complex = vf + ";" + aud

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seg_start:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-pix_fmt", "yuv420p", "-r", "24",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def extract_all_segments_vertical(edl, edit_dir, preview, draft=False):
    resolved = R.resolve_grade_filter(edl.get("grade"))
    is_auto = resolved == "__AUTO__"
    clips_dir = edit_dir / (
        "clips_draft" if draft else ("clips_preview" if preview else "clips_graded")
    )
    clips_dir.mkdir(parents=True, exist_ok=True)

    ranges = edl["ranges"]
    sources = edl["sources"]
    seg_paths = []
    print(f"extracting {len(ranges)} vertical segment(s) → {clips_dir.name}/")
    for i, r in enumerate(ranges):
        src_name = r["source"]
        src_path = R.resolve_path(sources[src_name], edit_dir)
        start = float(r["start"])
        end = float(r["end"])
        duration = end - start
        out_path = clips_dir / f"seg_{i:02d}_{src_name}.mp4"
        if is_auto:
            seg_filter, _ = R.auto_grade_for_clip(src_path, start=start, duration=duration, verbose=False)
        else:
            seg_filter = resolved
        note = r.get("beat") or r.get("note") or ""
        print(f"  [{i:02d}] {src_name}  {start:8.2f}-{end:8.2f}  ({duration:5.2f}s)  {note}")
        extract_segment_vertical(src_path, start, duration, seg_filter, out_path, preview=preview, draft=draft)
        seg_paths.append(out_path)
    return seg_paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--build-subtitles", action="store_true")
    ap.add_argument("--no-subtitles", action="store_true")
    ap.add_argument("--no-loudnorm", action="store_true")
    args = ap.parse_args()

    import json
    edl_path = args.edl.resolve()
    edl = json.loads(edl_path.read_text())
    edit_dir = edl_path.parent
    out_path = args.output.resolve()

    segment_paths = extract_all_segments_vertical(edl, edit_dir, preview=args.preview, draft=args.draft)

    base_name = "base_draft.mp4" if args.draft else ("base_preview.mp4" if args.preview else "base.mp4")
    base_path = edit_dir / base_name
    R.concat_segments(segment_paths, base_path, edit_dir)

    subs_path = None
    if not args.no_subtitles:
        if args.build_subtitles:
            subs_path = edit_dir / "master.srt"
            R.build_master_srt(edl, edit_dir, subs_path)
        elif edl.get("subtitles"):
            subs_path = R.resolve_path(edl["subtitles"], edit_dir)
            if not subs_path.exists():
                subs_path = None

    overlays = edl.get("overlays") or []
    if args.no_loudnorm:
        R.build_final_composite(base_path, overlays, subs_path, out_path, edit_dir)
    else:
        tmp = out_path.with_suffix(".prenorm.mp4")
        R.build_final_composite(base_path, overlays, subs_path, tmp, edit_dir)
        R.apply_loudnorm_two_pass(tmp, out_path, preview=args.draft)
        tmp.unlink(missing_ok=True)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\ndone: {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
