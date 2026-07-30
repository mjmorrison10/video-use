#!/usr/bin/env python3
"""Face-track the subject and inject per-segment crop into a cutspec.

Two modes:

  --mode recognize  ENROLL one person's face (SFace embeddings from known
        close-ups) and in every sampled frame pick the detected face that best
        matches them. Needed when several faces share the frame at similar size
        — e.g. a two-shot podcast, where a "largest face" rule flip-flops
        between host and guest and leaves the subject off-screen.

  --mode largest    Pick the biggest face in each frame. Correct when the shot
        grammar already follows the speaker (single-subject scenes, interviews
        cut to whoever is talking), and it needs no enrollment.

Either way the subject's horizontal centre becomes the cover-crop
objectPosition (cropX); if they drift across a segment we emit a
cropX->cropXEnd pan, and camera cuts inside a segment are split out.

Usage: face_track.py CUTSPEC.json PROXY.mp4 [-o OUT.json]
                     [--mode largest|recognize] [--enroll t1,t2,...]
"""
import argparse, json, subprocess, tempfile, os
import cv2, numpy as np

OUT_W, OUT_H = 1080, 1920
HERE = os.path.dirname(__file__)
YUNET = os.path.join(HERE, 'yunet.onnx')
SFACE = os.path.join(HERE, 'sface.onnx')
# Set from the proxy in main(): the cover-crop maths depends on the source's
# real aspect, which is NOT always 16:9 (e.g. after cropping burnt-in subs off).
PROXY = None
SCALED_W = OVERFLOW = None
COSINE = cv2.FaceRecognizerSF_FR_COSINE
MATCH_THR = 0.30   # cosine sim above which a face is "Andrew" (SFace default 0.363, relaxed for sunglasses/profile)

det = cv2.FaceDetectorYN.create(YUNET, '', (320, 320), 0.5, 0.3, 5000)
rec = cv2.FaceRecognizerSF.create(SFACE, '')

# Andrew enrollment: confirmed frontal close-ups (proxy seconds).
ENROLL_TS = [4640.0, 4648.0, 2527.0, 10045.0, 8324.0]
MODE = 'recognize'


def _grab(t, tmp, name='f.png'):
    fp = os.path.join(tmp, name)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', f'{t:.3f}', '-i', PROXY,
                    '-frames:v', '1', fp], check=False)
    return cv2.imread(fp)


MIN_FACE_W = 0.035   # faces below this fraction of frame width are background
MIN_SCORE = 0.75     # YuNet confidence; low-scoring boxes are usually furniture


def _faces(img):
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    n, faces = det.detect(img)
    if faces is None:
        return []
    # Background heads and spurious boxes otherwise win "largest" ties and yank
    # the crop to the frame edge for a fraction of a second.
    return [f for f in faces if f[2] >= MIN_FACE_W * w and f[14] >= MIN_SCORE]


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


def subject_cx(img):
    """Centre-x (0-1) of the subject's face in this frame, or None."""
    fs = _faces(img)
    if len(fs) == 0:
        return None
    if MODE == 'largest':
        best = max(fs, key=lambda f: f[2] * f[3])
    else:
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
MIN_RUN = 3       # samples; a shot shorter than this is a detection glitch, not a cut


def sample_cx(a, b, tmp, prev):
    """Dense (t, cx) samples across [a,b]; None cx filled by holding the last
    known subject position (or prev/0.5 at the very start)."""
    n = max(3, int((b - a) / STEP))
    ts = [a + 0.12 + (b - a - 0.24) * i / (n - 1) for i in range(n)]
    raw = []
    last = prev
    for t in ts:
        img = _grab(t, tmp)
        cx = subject_cx(img) if img is not None else None
        if cx is not None:
            last = cx
        raw.append((t, cx if cx is not None else last))
    # if the head was blank until first detection, back-fill it
    first = next((c for _, c in raw if c is not None), 0.5)
    return [(t, c if c is not None else first) for t, c in raw]


def _median3(samples):
    """Kill single-sample outliers before they look like camera cuts. A real cut
    holds its new position for several samples and survives the filter; one bad
    detection (a background face winning "largest" for a frame) does not."""
    if len(samples) < 3:
        return samples
    out = [samples[0]]
    for i in range(1, len(samples) - 1):
        med = float(np.median([samples[i - 1][1], samples[i][1], samples[i + 1][1]]))
        out.append((samples[i][0], med))
    out.append(samples[-1])
    return out


def split_runs(samples):
    """Split the sample list at camera cuts (big cx jumps). Returns list of runs,
    each a contiguous list of (t, cx)."""
    samples = _median3(samples)
    runs, cur = [], [samples[0]]
    for prev_s, s in zip(samples, samples[1:]):
        if abs(s[1] - prev_s[1]) >= CUT_JUMP:
            runs.append(cur); cur = [s]
        else:
            cur.append(s)
    runs.append(cur)
    # Absorb runs too short to be a real shot — a 0.3s crop jump reads as a
    # glitch even when the detection behind it was correct.
    while len(runs) > 1:
        i = min(range(len(runs)), key=lambda k: len(runs[k]))
        if len(runs[i]) >= MIN_RUN:
            break
        j = i - 1 if i == len(runs) - 1 else (i + 1 if i == 0 else
             (i - 1 if len(runs[i - 1]) >= len(runs[i + 1]) else i + 1))
        runs[j] = sorted(runs[i] + runs[j])
        runs.pop(i)
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
    ap.add_argument('--mode', choices=['largest', 'recognize'], default='recognize')
    ap.add_argument('--enroll', help='comma-separated proxy seconds of subject close-ups')
    a = ap.parse_args()

    global PROXY, MODE, ENROLL_TS, SCALED_W, OVERFLOW
    PROXY, MODE = a.proxy, a.mode
    if a.enroll:
        ENROLL_TS = [float(t) for t in a.enroll.split(',')]
    pw, ph = (int(x) for x in subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries',
         'stream=width,height', '-of', 'csv=p=0:s=x', PROXY],
        capture_output=True, text=True, check=True).stdout.strip().split('x'))
    SCALED_W = pw * (OUT_H / ph)
    OVERFLOW = SCALED_W - OUT_W
    if OVERFLOW <= 0:
        raise SystemExit(f"proxy {pw}x{ph} is narrower than 9:16 — nothing to pan")
    print(f"# proxy {pw}x{ph} -> scaled {SCALED_W:.0f}px wide, {OVERFLOW:.0f}px of pan, mode={MODE}")

    spec = json.load(open(a.cutspec))
    out_segs = []
    with tempfile.TemporaryDirectory() as tmp:
        if MODE == 'recognize':
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
