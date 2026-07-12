"""Render the vertical base video from plan.json: per-segment crop+scale+fps reframe with
30ms audio fades, then lossless concat. No captions, no loudnorm (captions.py does those).

Reuses helpers/render.py for the HDR tonemap chain and lossless concat (the hard-won bits).

Usage: render_vertical.py PLAN.json --source SRC -o base.mp4
"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, run, REPO  # noqa
sys.path.insert(0, os.path.join(REPO, "helpers"))
import render as rndr  # noqa

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--source", required=True)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    style = load_style()
    OW, OH, FPS = style["output"]["width"], style["output"]["height"], style["output"]["fps"]
    CRF, PRESET = style["output"]["crf"], style["output"]["x264_preset"]
    FADE = style["cutting"]["fade_s"]

    segs = json.load(open(a.plan))["segs"]
    ed = Path(a.out).parent
    segdir = ed / "seg"; segdir.mkdir(parents=True, exist_ok=True)
    hdr = rndr.is_hdr_source(Path(a.source))
    pre = (rndr.TONEMAP_CHAIN + ",") if hdr else ""

    paths = []
    for i, s in enumerate(segs):
        dur = s["e"] - s["s"]
        out = segdir / f"s{i:03d}.mp4"
        vf = f"{pre}crop={s['W']}:{s['H']}:{s['x']}:{s['y']},scale={OW}:{OH}:flags=lanczos,setsar=1,fps={FPS}"
        af = f"afade=t=in:st=0:d={FADE},afade=t=out:st={dur-FADE:.3f}:d={FADE}"
        run(["ffmpeg", "-y", "-ss", f"{s['s']:.3f}", "-i", str(a.source), "-t", f"{dur:.3f}",
             "-vf", vf, "-af", af, "-vsync", "cfr",
             "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
             "-crf", str(CRF), "-preset", PRESET,
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)])
        paths.append(out)

    rndr.concat_segments(paths, Path(a.out), ed)
    from _util import ffprobe_duration
    print(f"[done] {a.out}  ({len(segs)} segs, {ffprobe_duration(a.out):.2f}s, hdr={hdr})")

if __name__ == "__main__":
    main()
