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


CUT_JUMP = 0.14   # |cx| jump between adjacent samples => camera cut
STEP = 0.3        # sampling interval (s)


def sample_cx(a, b, tmp, prev):
    """Dense (t, cx) samples across [a,b]; None cx filled by holding the last
    known Andrew position (or prev/0.5 at the very start)."""
    n = max(3, int((b - a) / STEP))
    ts = [a + 0.12 + (b - a - 0.24) * i / (n - 1) for i in range(n)]
    raw = []
    last = prev
    for t in ts:
        img = _grab(t, tmp)
        cx = andrew_cx(img) if img is not None else None
        if cx is not None:
            last = cx
        raw.append((t, cx if cx is not None else last))
    # if the head was blank until first detection, back-fill it
    first = next((c for _, c in raw if c is not None), 0.5)
    return [(t, c if c is not None else first) for t, c in raw]


def split_runs(samples):
    """Split the sample list at camera cuts (big cx jumps). Returns list of runs,
    each a contiguous list of (t, cx)."""
    runs, cur = [], [samples[0]]
    for prev_s, s in zip(samples, samples[1:]):
        if abs(s[1] - prev_s[1]) >= CUT_JUMP:
            runs.append(cur); cur = [s]
        else:
            cur.append(s)
    runs.append(cur)
    return runs


def emit_runs(a, b, samples):
    """Turn a segment's samples into 1+ sub-segments, split at camera cuts.
    Each sub-segment gets a static crop, or a pan if Andrew drifts smoothly."""
    runs = split_runs(samples)
    subs = []
    for i, run in enumerate(runs):
        # time span this run covers within [a,b]
        lo = a if i == 0 else (run[0][0] + runs[i - 1][-1][0]) / 2
        hi = b if i == len(runs) - 1 else (run[-1][0] + runs[i + 1][0][0]) / 2
        cxs = [c for _, c in run]
        med = float(np.median(cxs))
        cstart = float(np.median(cxs[:max(1, len(cxs) // 3)]))
        cend = float(np.median(cxs[-max(1, len(cxs) // 3):]))
        seg = {"inSec": round(lo, 3), "outSec": round(hi, 3)}
        if abs(cx_to_cropx(cend) - cx_to_cropx(cstart)) >= 0.10:
            seg["cropX"] = cx_to_cropx(cstart)
            seg["cropXEnd"] = cx_to_cropx(cend)
            seg["cropPanSec"] = round(hi - lo, 2)
        else:
            seg["cropX"] = cx_to_cropx(med)
        subs.append(seg)
    return subs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cutspec'); ap.add_argument('proxy'); ap.add_argument('-o', '--out')
    a = ap.parse_args()
    spec = json.load(open(a.cutspec))
    out_segs = []
    with tempfile.TemporaryDirectory() as tmp:
        enroll(tmp)
        prev = None
        for s in spec['segments']:
            samples = sample_cx(s['inSec'], s['outSec'], tmp, prev)
            prev = samples[-1][1]
            base = {k: v for k, v in s.items() if k not in ('cropX', 'cropXEnd', 'cropPanSec')}
            for sub in emit_runs(s['inSec'], s['outSec'], samples):
                seg = {**base, **sub}
                out_segs.append(seg)
                tag = f"pan {seg['cropX']}->{seg.get('cropXEnd')}" if 'cropXEnd' in seg else f"crop {seg['cropX']}"
                print(f"  [{seg['inSec']:.2f}-{seg['outSec']:.2f}] {tag}")
    spec['segments'] = out_segs
    out = a.out or a.cutspec
    json.dump(spec, open(out, 'w'), ensure_ascii=False, indent=1)
    print(f"# face-tracked -> {out} ({len(out_segs)} segs)")


if __name__ == '__main__':
    main()
