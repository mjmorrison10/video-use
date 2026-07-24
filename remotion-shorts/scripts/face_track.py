#!/usr/bin/env python3
"""Face-track ANDREW (by recognition) and inject per-segment crop into a cutspec.

The podcast is a two-shot: Andrew camera-left, the interviewer camera-right,
often with near-equal face sizes. A "largest face" rule flip-flops between them,
so instead we ENROLL Andrew's face (SFace embeddings from known close-ups) and,
in every sampled frame, pick the detected face that best matches Andrew. His
horizontal centre becomes the cover-crop objectPosition (cropX); if he drifts
across a segment we emit a cropX->cropXEnd pan.

Usage: face_track.py CUTSPEC.json PROXY.mp4 [-o OUT.json]
"""
import argparse, json, subprocess, tempfile, os
import cv2, numpy as np

PROXY_W, PROXY_H = 1920, 1080
OUT_W, OUT_H = 1080, 1920
SCALED_W = PROXY_W * (OUT_H / PROXY_H)
OVERFLOW = SCALED_W - OUT_W
HERE = os.path.dirname(__file__)
YUNET = os.path.join(HERE, 'yunet.onnx')
SFACE = os.path.join(HERE, 'sface.onnx')
PROXY = os.path.join(HERE, 'jackkneel.mp4')
COSINE = cv2.FaceRecognizerSF_FR_COSINE
MATCH_THR = 0.30   # cosine sim above which a face is "Andrew" (SFace default 0.363, relaxed for sunglasses/profile)

det = cv2.FaceDetectorYN.create(YUNET, '', (320, 320), 0.5, 0.3, 5000)
rec = cv2.FaceRecognizerSF.create(SFACE, '')

# Andrew enrollment: confirmed frontal close-ups (proxy seconds).
ENROLL_TS = [4640.0, 4648.0, 2527.0, 10045.0, 8324.0]


def _grab(t, tmp, name='f.png'):
    fp = os.path.join(tmp, name)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{t:.3f}', '-i', PROXY,
                    '-frames:v', '1', fp], check=False)
    return cv2.imread(fp)


def _faces(img):
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    n, faces = det.detect(img)
    return faces if faces is not None else []


def _feat(img, face):
    return rec.feature(rec.alignCrop(img, face))


ANDREW = []


def enroll(tmp):
    for t in ENROLL_TS:
        img = _grab(t, tmp, 'e.png')
        if img is None:
            continue
        fs = _faces(img)
        if len(fs) == 0:
            continue
        # in a close-up Andrew is the largest face
        f = max(fs, key=lambda f: f[2] * f[3])
        ANDREW.append(_feat(img, f))
    if not ANDREW:
        raise SystemExit("enrollment failed: no Andrew faces")
    # sanity: enrolled faces should agree with each other
    if len(ANDREW) >= 2:
        sims = [rec.match(ANDREW[0], e, COSINE) for e in ANDREW[1:]]
        print(f"# enrolled {len(ANDREW)} refs, self-sim {['%.2f'%s for s in sims]}")


def andrew_cx(img):
    """Centre-x of the face best matching Andrew, or None."""
    fs = _faces(img)
    best, bestsim = None, -1.0
    for f in fs:
        sim = max(rec.match(_feat(img, f), e, COSINE) for e in ANDREW)
        if sim > bestsim:
            best, bestsim = f, sim
    if best is None or bestsim < MATCH_THR:
        return None
    return (best[0] + best[2] / 2) / img.shape[1]


def cx_to_cropx(cx):
    p = (cx * SCALED_W - OUT_W / 2) / OVERFLOW
    return round(min(1.0, max(0.0, p)), 3)


def track_segment(a, b, tmp, prev):
    dur = b - a
    nsamp = max(4, int(dur / 0.4))
    ts = [a + 0.15 + (dur - 0.3) * i / (nsamp - 1) for i in range(nsamp)]
    got = []
    for t in ts:
        img = _grab(t, tmp)
        if img is None:
            continue
        cx = andrew_cx(img)
        if cx is not None:
            got.append((t, cx))
    if not got:
        return {"cropX": prev if prev is not None else 0.5}, prev
    firsts = [c for t, c in got if t <= a + dur / 3]
    lasts = [c for t, c in got if t >= b - dur / 3]
    all_cx = [c for _, c in got]
    med = float(np.median(all_cx))
    cstart = float(np.median(firsts)) if firsts else med
    cend = float(np.median(lasts)) if lasts else med
    cropX, cropXEnd = cx_to_cropx(cstart), cx_to_cropx(cend)
    if abs(cropXEnd - cropX) >= 0.10:
        return {"cropX": cropX, "cropXEnd": cropXEnd, "cropPanSec": round(dur, 2)}, cend
    return {"cropX": cx_to_cropx(med)}, med


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cutspec'); ap.add_argument('proxy'); ap.add_argument('-o', '--out')
    a = ap.parse_args()
    spec = json.load(open(a.cutspec))
    with tempfile.TemporaryDirectory() as tmp:
        enroll(tmp)
        prev = None
        for s in spec['segments']:
            crop, prev = track_segment(s['inSec'], s['outSec'], tmp, prev)
            s.pop('cropXEnd', None); s.pop('cropPanSec', None)
            s.update(crop)
            tag = f"pan {s['cropX']}->{s.get('cropXEnd')}" if 'cropXEnd' in s else f"crop {s['cropX']}"
            print(f"  [{s['inSec']:.2f}-{s['outSec']:.2f}] {tag}")
    out = a.out or a.cutspec
    json.dump(spec, open(out, 'w'), ensure_ascii=False, indent=1)
    print(f"# face-tracked -> {out}")


if __name__ == '__main__':
    main()
