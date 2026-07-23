#!/usr/bin/env python3
"""Face-track the speaker and inject per-segment crop into a snapped cutspec.

For each segment, sample frames from the full proxy, detect the largest face
(Andrew is the foreground subject), and convert its horizontal centre to the
cover-crop objectPosition (cropX) that puts him in frame centre. If he drifts
across the segment, emit a cropX->cropXEnd pan instead of a static crop.

Usage: face_track.py SNAPPED_CUTSPEC.json PROXY.mp4 [-o OUT.json]
"""
import argparse, json, subprocess, tempfile, os
import cv2, numpy as np

PROXY_W, PROXY_H = 1920, 1080          # source frame
OUT_W, OUT_H = 1080, 1920              # 9:16 output
SCALED_W = PROXY_W * (OUT_H / PROXY_H)  # width after cover-scaling to fill height
OVERFLOW = SCALED_W - OUT_W
MODEL = os.path.join(os.path.dirname(__file__), 'yunet.onnx')

det = cv2.FaceDetectorYN.create(MODEL, '', (320, 320), 0.6, 0.3, 5000)


def face_cx(proxy, t, tmp):
    """Largest-face normalized centre-x at time t, or None."""
    fp = os.path.join(tmp, 'f.png')
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{t:.3f}', '-i', proxy,
                    '-frames:v', '1', fp], check=False)
    img = cv2.imread(fp)
    if img is None:
        return None
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    n, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    # largest face = foreground subject (Andrew)
    f = max(faces, key=lambda f: f[2] * f[3])
    return (f[0] + f[2] / 2) / w


def cx_to_cropx(cx):
    """Map face centre-x (0..1 of source) to objectPosition fraction so the
    face lands at output centre under object-fit: cover."""
    p = (cx * SCALED_W - OUT_W / 2) / OVERFLOW
    return round(min(1.0, max(0.0, p)), 3)


def track_segment(proxy, a, b, tmp, prev):
    dur = b - a
    nsamp = max(3, int(dur / 0.5))
    ts = [a + 0.15 + (dur - 0.3) * i / (nsamp - 1) for i in range(nsamp)]
    cxs = [face_cx(proxy, t, tmp) for t in ts]
    got = [(t, c) for t, c in zip(ts, cxs) if c is not None]
    if not got:
        return {"cropX": prev if prev is not None else 0.5}, prev
    # split into first / last third to detect a pan
    firsts = [c for t, c in got if t <= a + dur / 3]
    lasts = [c for t, c in got if t >= b - dur / 3]
    all_cx = [c for _, c in got]
    med = float(np.median(all_cx))
    cstart = float(np.median(firsts)) if firsts else med
    cend = float(np.median(lasts)) if lasts else med
    cropX = cx_to_cropx(cstart)
    cropXEnd = cx_to_cropx(cend)
    if abs(cropXEnd - cropX) >= 0.10:  # meaningful drift -> pan and hold
        return {"cropX": cropX, "cropXEnd": cropXEnd, "cropPanSec": round(dur, 2)}, cend
    return {"cropX": cx_to_cropx(med)}, med


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cutspec'); ap.add_argument('proxy')
    ap.add_argument('-o', '--out')
    a = ap.parse_args()
    spec = json.load(open(a.cutspec))
    prev = None
    with tempfile.TemporaryDirectory() as tmp:
        for s in spec['segments']:
            crop, prev = track_segment(a.proxy, s['inSec'], s['outSec'], tmp, prev)
            s.pop('cropXEnd', None); s.pop('cropPanSec', None)
            s.update(crop)
            tag = f"pan {s['cropX']}->{s.get('cropXEnd')}" if 'cropXEnd' in s else f"crop {s['cropX']}"
            print(f"  [{s['inSec']:.2f}-{s['outSec']:.2f}] {tag}")
    out = a.out or a.cutspec
    json.dump(spec, open(out, 'w'), ensure_ascii=False, indent=1)
    print(f"# face-tracked -> {out}")


if __name__ == '__main__':
    main()
