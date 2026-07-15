"""Render the vertical base video from plan.json: per-segment crop+scale+fps reframe with
30ms audio fades, then lossless concat. No captions, no loudnorm (captions.py does those).

Reuses helpers/render.py for the HDR tonemap chain and lossless concat (the hard-won bits).

Usage: render_vertical.py PLAN.json --source SRC -o base.mp4
"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, run, REPO, ffprobe_dims  # noqa
sys.path.insert(0, os.path.join(REPO, "helpers"))
import render as rndr  # noqa

def fit_filter(pre, OW, OH, FPS, src_w, src_h, center=False):
    """Full 16:9 frame scaled to output width over a blurred, darkened fill of itself.
    center=False -> band biased toward the upper-middle so captions sit below it in the blurred
    zone (podcast/chart). center=True -> band vertically centred (cinematic; no black-bar look on
    an uncaptioned drama clip)."""
    fg_h = int(round(OW * src_h / src_w / 2) * 2)
    vy = (OH - fg_h) // 2 if center else max(80, (OH - fg_h) // 2 - 300)
    return (f"[0:v]{pre}split=2[bg][fg];"
            f"[bg]scale={OW}:{OH}:force_original_aspect_ratio=increase,crop={OW}:{OH},"
            f"boxblur=30:2,eq=brightness=-0.30:saturation=0.7[bgb];"
            f"[fg]scale={OW}:-2:flags=lanczos[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:{vy}:shortest=1,setsar=1,fps={FPS}[v]")

# --- "pip" mode layout constants (1080x1920) ---
B = 6                 # white card border px
BG = "0x111318"       # solid card background (no blur)
SPK_CARD_H = 660      # overlay card fixed height; width derived from the source region aspect
SPK_CARD_Y = 782      # overlay card top (below the speaker's face, above captions)
CH_CARD_W = 1030      # chart card width; height derived from source aspect
CH_CARD_CY = 806      # chart card vertical centre

def even(v):
    return int(round(v / 2) * 2)

def pip_filter(seg, pre, OW, OH, FPS, src_w, src_h):
    """filter_complex for a pip segment (single source input, uses a `color` filter source
    for the solid bg — no extra ffmpeg inputs needed).
    mode 'speaker' -> speaker fills frame (+ optional overlay card of what they reference);
    mode 'chart'   -> the full frame as a clean bordered card centred on a solid bg."""
    if seg.get("mode") == "chart":
        cw = even(CH_CARD_W); ch = even(round(cw * src_h / src_w))
        cx = (OW - (cw + 2 * B)) // 2; cy = CH_CARD_CY - (ch + 2 * B) // 2
        return (f"color=c={BG}:s={OW}x{OH}:r={FPS}[bg];"
                f"[0:v]{pre}scale={cw}:{ch}:flags=lanczos,"
                f"pad={cw+2*B}:{ch+2*B}:{B}:{B}:white[card];"
                f"[bg][card]overlay={cx}:{cy}:shortest=1,setsar=1,fps={FPS}[v]")
    crop = f"[0:v]{pre}crop={seg['W']}:{seg['H']}:{seg['x']}:{seg['y']},scale={OW}:{OH}:flags=lanczos,setsar=1"
    ov = seg.get("ov")
    if not ov:
        return f"{crop},fps={FPS}[v]"
    ch = even(SPK_CARD_H); cw = even(min(OW - 80, round(ch * ov["w"] / ov["h"])))
    ox = (OW - (cw + 2 * B)) // 2
    return (f"{crop}[main];"
            f"[0:v]crop={ov['w']}:{ov['h']}:{ov['x']}:{ov['y']},scale={cw}:{ch}:flags=lanczos,"
            f"pad={cw+2*B}:{ch+2*B}:{B}:{B}:white[card];"
            f"[main][card]overlay={ox}:{SPK_CARD_Y}:shortest=1,fps={FPS}[v]")

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
    src_w, src_h = ffprobe_dims(a.source)

    paths = []
    for i, s in enumerate(segs):
        dur = s["e"] - s["s"]
        out = segdir / f"s{i:03d}.mp4"
        af = f"afade=t=in:st=0:d={FADE},afade=t=out:st={dur-FADE:.3f}:d={FADE}"
        cmd = ["ffmpeg", "-y", "-ss", f"{s['s']:.3f}", "-i", str(a.source), "-t", f"{dur:.3f}"]
        if s.get("mode") in ("speaker", "chart"):
            cmd += ["-filter_complex", pip_filter(s, pre, OW, OH, FPS, src_w, src_h),
                    "-map", "[v]", "-map", "0:a", "-af", af]
        elif s.get("cam") in ("FIT", "FITC"):
            cmd += ["-filter_complex", fit_filter(pre, OW, OH, FPS, src_w, src_h, center=(s.get("cam") == "FITC")),
                    "-map", "[v]", "-map", "0:a", "-af", af]
        else:
            vf = f"{pre}crop={s['W']}:{s['H']}:{s['x']}:{s['y']},scale={OW}:{OH}:flags=lanczos,setsar=1,fps={FPS}"
            cmd += ["-vf", vf, "-af", af]
        cmd += ["-vsync", "cfr", "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
                "-crf", str(CRF), "-preset", PRESET,
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)]
        run(cmd)
        paths.append(out)

    rndr.concat_segments(paths, Path(a.out), ed)
    from _util import ffprobe_duration
    print(f"[done] {a.out}  ({len(segs)} segs, {ffprobe_duration(a.out):.2f}s, hdr={hdr})")

if __name__ == "__main__":
    main()
