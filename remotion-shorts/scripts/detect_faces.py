#!/usr/bin/env python3
"""Face-aware framing: detect the speaker per frame and emit an objectPosition
PAN TRACK so the 9:16 cover-crop keeps the subject framed.

Detector priority:
  1. YuNet DNN (models/yunet.onnx) — robust across scales/angles/produced shots
     (small faces in wide b-roll, off-axis, composed graphics). Strongly preferred.
  2. Haar cascades (frontal -> profile -> mirrored) — fallback if the model is absent.

Per segment we sample frames, find the largest face, reject outliers (a raised
hand / background face), fill gaps, smooth, then convert the face x-fraction into
the CSS object-position percent that centers it under `object-fit: cover`.

Output (aligned by segment index to the cut-spec):
  {"targetW":1080,"targetH":1920,"segments":[[{"f":<segLocalFrame>,"px":<0..1>,"py":<0..1>}, ...], ...]}

Usage:
  uv run --with 'opencv-python-headless<5' --with numpy python scripts/detect_faces.py \
      public/<proxy>.mp4 jobs/<clip>.cutspec.json -o jobs/<clip>.focus.json \
      [--sample-fps 10] [--smooth-win 0.5] [--target 1080x1920] [--model models/yunet.onnx]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def cover_axis(f, src, other_src, t_main, t_other):
    """object-position (0..1) that centers source fraction f on the overflowing axis
    of an object-fit: cover box. Returns 0.5 when that axis does not overflow."""
    scale = max(t_main / src, t_other / other_src)
    size = src * scale
    over = size - t_main
    if over <= 1e-6:
        return 0.5
    return float(min(1.0, max(0.0, (f * size - t_main / 2) / over)))


class YuNetDetector:
    def __init__(self, model, w, h):
        self.det = cv2.FaceDetectorYN.create(model, "", (w, h), 0.6, 0.3, 5000)
        self.det.setInputSize((w, h))
        self.w, self.h = w, h

    def __call__(self, frame):
        _, faces = self.det.detect(frame)
        if faces is None or len(faces) == 0:
            return None
        b = max(faces, key=lambda f: f[2] * f[3])  # largest
        x, y, w, h = b[0], b[1], b[2], b[3]
        return (x + w / 2) / self.w, (y + h / 2) / self.h, w / self.w


class HaarDetector:
    def __init__(self, w, h):
        self.fc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.pf = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
        self.w, self.h = w, h

    def __call__(self, frame):
        g = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        ms = (int(self.w * 0.05), int(self.w * 0.05))
        faces = list(self.fc.detectMultiScale(g, 1.1, 6, minSize=ms))
        if not faces:
            faces = list(self.pf.detectMultiScale(g, 1.1, 5, minSize=ms))
        if not faces:
            flip = list(self.pf.detectMultiScale(cv2.flip(g, 1), 1.1, 5, minSize=ms))
            faces = [(self.w - x - w, y, w, h) for (x, y, w, h) in flip]
        if not faces:
            return None
        x, y, w, h = max(faces, key=lambda b: b[2] * b[3])
        return (x + w / 2) / self.w, (y + h / 2) / self.h, w / self.w


def reject_outliers(cxs, cys, ws):
    """Drop spurious detections: box width out of a plausible range, or x far from
    the robust center (e.g. a background face grabbed for a few frames)."""
    idx = [i for i, v in enumerate(cxs) if v is not None]
    if len(idx) < 3:
        return cxs, cys
    xs = np.array([cxs[i] for i in idx])
    med = float(np.median(xs))
    mad = float(np.median(np.abs(xs - med))) or 0.02
    wmed = float(np.median([ws[i] for i in idx]))
    for i in idx:
        if (abs(cxs[i] - med) > max(0.10, 3.0 * mad)
                or ws[i] < 0.02 or ws[i] > 0.6
                or abs(ws[i] - wmed) > 0.6 * wmed):
            cxs[i] = cys[i] = None
    return cxs, cys


def fill_and_smooth(vals, win):
    n = len(vals)
    known = [i for i, v in enumerate(vals) if v is not None]
    if not known:
        return None
    out = list(vals)
    for i in range(0, known[0]):
        out[i] = vals[known[0]]
    for i in range(known[-1] + 1, n):
        out[i] = vals[known[-1]]
    for a, b in zip(known, known[1:]):
        if b - a > 1:
            for i in range(a + 1, b):
                out[i] = vals[a] + (vals[b] - vals[a]) * (i - a) / (b - a)
    if win >= 3:
        arr = np.array(out, dtype=float)
        k = np.ones(win) / win
        out = np.convolve(np.pad(arr, win // 2, mode="edge"), k, mode="valid")[:n].tolist()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("cutspec")
    ap.add_argument("-o", "--out", default="focus.json")
    ap.add_argument("--sample-fps", type=float, default=10.0)
    ap.add_argument("--smooth-win", type=float, default=0.5)
    ap.add_argument("--target", default="1080x1920")
    ap.add_argument("--model", default="models/yunet.onnx")
    args = ap.parse_args()

    tw, th = (int(x) for x in args.target.lower().split("x"))
    spec = json.loads(Path(args.cutspec).read_text())
    proj_fps = spec.get("fps", 30)
    segs = spec["segments"]

    cap = cv2.VideoCapture(args.video)
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    model = Path(args.model)
    if model.exists() and hasattr(cv2, "FaceDetectorYN"):
        detect = YuNetDetector(str(model), src_w, src_h)
        which = "YuNet"
    else:
        detect = HaarDetector(src_w, src_h)
        which = "Haar"

    step = 1.0 / args.sample_fps
    win = max(1, int(round(args.smooth_win * args.sample_fps)))

    raw, all_cx, all_cy = [], [], []
    for seg in segs:
        a, b = float(seg["inSec"]), float(seg["outSec"])
        times, cxs, cys, wss = [], [], [], []
        t = a
        while t < b - 1e-6:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, fr = cap.read()
            if ok:
                r = detect(fr)
                if r is not None:
                    cx, cy, w = r
                    cxs.append(cx); cys.append(cy); wss.append(w)
                    all_cx.append(cx); all_cy.append(cy)
                else:
                    cxs.append(None); cys.append(None); wss.append(None)
                times.append(t)
            t += step
        raw.append((a, times, cxs, cys, wss))

    gcx = float(np.median(all_cx)) if all_cx else 0.5
    gcy = float(np.median(all_cy)) if all_cy else 0.5

    out_segments, rate = [], []
    for (a, times, cxs, cys, wss) in raw:
        cxs, cys = reject_outliers(cxs, cys, wss)
        rate.append((sum(1 for v in cxs if v is not None), len(cxs)))
        sx = fill_and_smooth(cxs, win)
        sy = fill_and_smooth(cys, win)
        if sx is None:
            sx = [gcx] * len(times); sy = [gcy] * len(times)
        kf = []
        for t, x, y in zip(times, sx, sy):
            f = int(round((t - a) * proj_fps))
            px = cover_axis(x, src_w, src_h, tw, th)
            py = cover_axis(y, src_h, src_w, th, tw)
            kf.append({"f": f, "px": round(px, 4), "py": round(py, 4)})
        dedup = []
        for k in kf:
            if not dedup or dedup[-1]["f"] != k["f"]:
                dedup.append(k)
        out_segments.append(dedup)

    cap.release()
    Path(args.out).write_text(json.dumps(
        {"targetW": tw, "targetH": th, "segments": out_segments}, indent=1))
    print(f"[faces] {which}: {len(segs)} segments, src {src_w}x{src_h} -> {args.out}")
    for i, (got, tot) in enumerate(rate):
        pxs = [k["px"] for k in out_segments[i]]
        rng = f"{min(pxs):.2f}-{max(pxs):.2f}" if pxs else "n/a"
        print(f"  seg{i}: face {got}/{tot}, px {rng}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
