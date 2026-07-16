#!/usr/bin/env python3
"""Face-aware framing: detect the speaker's face across each cut-spec segment and
emit an objectPosition PAN TRACK so the 9:16 cover-crop keeps the face framed.

For each segment we sample frames (default 8 fps), find the largest face
(frontal -> profile -> mirrored profile), fill gaps, smooth the horizontal
center, then convert the face x-fraction into the CSS `object-position` percent
that centers that face inside the target crop (accounting for cover scaling).

Output (aligned by segment index to the cut-spec):
  {"targetW":1080,"targetH":1920,"segments":[[{"f":<segLocalFrame>,"px":<0..1>,"py":<0..1>}, ...], ...]}

`f` is the segment-local output frame at the project fps (Remotion resets the
frame to 0 at each <Sequence>). The Short component interpolates px/py over f.

Usage:
  uv run --with 'opencv-python-headless<5' --with numpy python scripts/detect_faces.py \
      public/proxy.mp4 jobs/<clip>.cutspec.json -o jobs/<clip>.focus.json \
      [--sample-fps 8] [--smooth-win 0.5] [--target 1080x1920]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def cover_px(fx, src_w, src_h, tw, th):
    """CSS object-position x (0..1) that centers source x-fraction fx in a
    `object-fit: cover` box. Returns 0.5 when there is no horizontal overflow."""
    scale = max(tw / src_w, th / src_h)
    ws = src_w * scale
    ox = ws - tw
    if ox <= 1e-6:
        return 0.5
    px = (fx * ws - tw / 2) / ox
    return float(min(1.0, max(0.0, px)))


def cover_py(fy, src_w, src_h, tw, th):
    scale = max(tw / src_w, th / src_h)
    hs = src_h * scale
    oy = hs - th
    if oy <= 1e-6:
        return 0.5
    py = (fy * hs - th / 2) / oy
    return float(min(1.0, max(0.0, py)))


def detect_largest(gray, fc, pf):
    """Largest face box (x,y,w,h) or None. frontal -> profile -> mirrored profile."""
    g = cv2.equalizeHist(gray)
    H, W = g.shape[:2]
    ms = (int(W * 0.06), int(W * 0.06))
    faces = list(fc.detectMultiScale(g, 1.1, 6, minSize=ms))
    if not faces:
        faces = list(pf.detectMultiScale(g, 1.1, 5, minSize=ms))
    if not faces:
        flipped = list(pf.detectMultiScale(cv2.flip(g, 1), 1.1, 5, minSize=ms))
        faces = [(W - x - w, y, w, h) for (x, y, w, h) in flipped]
    if not faces:
        return None
    return max(faces, key=lambda b: b[2] * b[3])


def reject_outliers(cxs, cys, ws):
    """Drop spurious detections (e.g. a hand read as a face): boxes whose width is
    out of a plausible face range, or whose x deviates far from the robust center."""
    idx = [i for i, v in enumerate(cxs) if v is not None]
    if len(idx) < 3:
        return cxs, cys
    xs = np.array([cxs[i] for i in idx])
    wsz = np.array([ws[i] for i in idx])
    med = float(np.median(xs))
    mad = float(np.median(np.abs(xs - med))) or 0.02
    wmed = float(np.median(wsz))
    for j, i in enumerate(idx):
        bad = (abs(xs[j] - med) > max(0.10, 3.0 * mad)
               or ws[i] < 0.10 or ws[i] > 0.40
               or abs(ws[i] - wmed) > 0.5 * wmed)
        if bad:
            cxs[i] = None
            cys[i] = None
    return cxs, cys


def fill_and_smooth(vals, win):
    """vals: list of float|None. Linear-fill gaps, hold at the ends, moving-avg smooth."""
    n = len(vals)
    known = [i for i, v in enumerate(vals) if v is not None]
    if not known:
        return None
    out = [None] * n
    for i in range(n):
        if vals[i] is not None:
            out[i] = vals[i]
    # leading/trailing hold
    for i in range(0, known[0]):
        out[i] = vals[known[0]]
    for i in range(known[-1] + 1, n):
        out[i] = vals[known[-1]]
    # interior linear interpolation
    for a, b in zip(known, known[1:]):
        if b - a > 1:
            va, vb = vals[a], vals[b]
            for i in range(a + 1, b):
                out[i] = va + (vb - va) * (i - a) / (b - a)
    # moving-average smoothing
    if win >= 3:
        arr = np.array(out, dtype=float)
        k = np.ones(win) / win
        arr = np.convolve(np.pad(arr, win // 2, mode="edge"), k, mode="valid")[:n]
        out = arr.tolist()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("cutspec")
    ap.add_argument("-o", "--out", default="focus.json")
    ap.add_argument("--sample-fps", type=float, default=8.0)
    ap.add_argument("--smooth-win", type=float, default=0.5, help="smoothing window seconds")
    ap.add_argument("--target", default="1080x1920")
    args = ap.parse_args()

    tw, th = (int(x) for x in args.target.lower().split("x"))
    spec = json.loads(Path(args.cutspec).read_text())
    proj_fps = spec.get("fps", 30)
    segs = spec["segments"]

    fc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    pf = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    cap = cv2.VideoCapture(args.video)
    src_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    src_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

    step = 1.0 / args.sample_fps
    win = max(1, int(round(args.smooth_win * args.sample_fps)))

    # first pass: raw detections per segment, plus a global fallback center
    raw_segments, all_cx, all_cy = [], [], []
    for seg in segs:
        a, b = float(seg["inSec"]), float(seg["outSec"])
        times, cxs, cys, wss = [], [], [], []
        t = a
        while t < b - 1e-6:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, fr = cap.read()
            if ok:
                box = detect_largest(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), fc, pf)
                if box is not None:
                    x, y, w, h = box
                    cx = (x + w / 2) / src_w
                    cy = (y + h / 2) / src_h
                    cxs.append(cx); cys.append(cy); wss.append(w / src_w)
                    all_cx.append(cx); all_cy.append(cy)
                else:
                    cxs.append(None); cys.append(None); wss.append(None)
                times.append(t)
            t += step
        raw_segments.append((a, times, cxs, cys, wss))

    gcx = float(np.median(all_cx)) if all_cx else 0.5
    gcy = float(np.median(all_cy)) if all_cy else 0.5

    out_segments = []
    detect_rate = []
    for (a, times, cxs, cys, wss) in raw_segments:
        cxs, cys = reject_outliers(cxs, cys, wss)
        got = sum(1 for v in cxs if v is not None)
        detect_rate.append((got, len(cxs)))
        sx = fill_and_smooth(cxs, win)
        sy = fill_and_smooth(cys, win)
        if sx is None:
            sx = [gcx] * len(times)
            sy = [gcy] * len(times)
        keyframes = []
        for t, x, y in zip(times, sx, sy):
            f = int(round((t - a) * proj_fps))
            px = cover_px(x, src_w, src_h, tw, th)
            py = cover_py(y, src_w, src_h, tw, th)
            keyframes.append({"f": f, "px": round(px, 4), "py": round(py, 4)})
        # dedup identical consecutive frames
        dedup = []
        for kf in keyframes:
            if not dedup or dedup[-1]["f"] != kf["f"]:
                dedup.append(kf)
        out_segments.append(dedup)

    cap.release()
    Path(args.out).write_text(json.dumps(
        {"targetW": tw, "targetH": th, "segments": out_segments}, indent=1))
    print(f"[faces] {len(segs)} segments, src {int(src_w)}x{int(src_h)} -> {args.out}")
    for i, (got, tot) in enumerate(detect_rate):
        pxs = [k["px"] for k in out_segments[i]]
        rng = f"{min(pxs):.2f}-{max(pxs):.2f}" if pxs else "n/a"
        print(f"  seg{i}: face {got}/{tot} frames, px {rng}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
