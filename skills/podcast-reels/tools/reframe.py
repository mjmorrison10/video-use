"""Active-speaker auto-reframe for a 16:9 -> 9:16 punch-in.

For a given source range, detect faces per sampled frame (OpenCV Haar), decide
who is talking via lip-region motion, and emit a smoothed crop-center-x timeline
(piecewise, with short ramps at speaker switches). The render step turns this
into an ffmpeg crop x-expression so the 9:16 window follows the active speaker.

Justin is on the LEFT, therapist on the RIGHT (per the user) — used only as a
tie-break / fallback when no face is detected (default to the left / main
speaker).

Output JSON: {"seg_dur": float, "crop_w": int, "holds": [[t_rel, cx], ...]}
cx = crop-center x in SOURCE pixels.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from pathlib import Path as _Path

CROP_W = 608          # 9:16 window width for a 1080-tall source
SRC_W, SRC_H = 1920, 1080
CX_MIN, CX_MAX = CROP_W // 2, SRC_W - CROP_W // 2
SAMPLE_FPS = 8.0
HOLD_S = 1.1          # min time a speaker must stay active before we switch
DEFAULT_CX = 640      # left-third (Justin) fallback

_MODEL = str(_Path(__file__).resolve().parent / "yunet.onnx")
_detector = cv2.FaceDetectorYN.create(_MODEL, "", (SRC_W, SRC_H), 0.5, 0.3, 5000)


def detect_faces(frame_bgr):
    """Return list of dicts: {bbox:(x,y,w,h), cx, mouth:(mx,my)} for each face."""
    _detector.setInputSize((frame_bgr.shape[1], frame_bgr.shape[0]))
    _, faces = _detector.detect(frame_bgr)
    out = []
    if faces is None:
        return out
    for f in faces:
        x, y, w, h = f[0], f[1], f[2], f[3]
        # mouth corners: right (10,11), left (12,13)
        mx = (f[10] + f[12]) / 2.0
        my = (f[11] + f[13]) / 2.0
        out.append({
            "bbox": (int(x), int(y), int(w), int(h)),
            "cx": int(x + w / 2),
            "nose": (float(f[8]), float(f[9])),   # nose-tip landmark
            "mouth": (float(mx), float(my)),
            "mw": float(abs(f[12] - f[10])) or float(w) * 0.4,
        })
    return out


def mouth_motion(prev_gray, gray, face):
    mx, my = face["mouth"]
    r = max(10.0, face["mw"] * 0.9)
    x0 = int(max(0, mx - r)); x1 = int(min(gray.shape[1], mx + r))
    y0 = int(max(0, my - r * 0.7)); y1 = int(min(gray.shape[0], my + r * 0.7))
    a = prev_gray[y0:y1, x0:x1].astype(np.int16)
    b = gray[y0:y1, x0:x1].astype(np.int16)
    if a.size == 0 or a.shape != b.shape:
        return 0.0
    return float(np.mean(np.abs(b - a)))


CLOSEUP_W = 150       # face width above this = close-up (reliable speaker)
LEFT_BIAS = 2.6       # Justin (left) is the main speaker: strong tie-break toward left
SWITCH_PX = 180       # cx delta that counts as "the other person"


def analyze(video: Path, start: float, end: float):
    cap = cv2.VideoCapture(str(video))
    seg_dur = end - start
    step = 1.0 / SAMPLE_FPS

    # Pass 1: per-sample face records with mouth-motion + scene-cut flags.
    CUT_THRESH = 22.0     # mean abs frame diff (0-255 downscaled) above = shot cut
    recs = []             # {t, faces, cut}
    prev_gray = None
    prev_small = None
    t = 0.0
    while t < seg_dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, (start + t) * 1000.0)
        ok, frame = cap.read()
        if not ok:
            break
        if frame.shape[1] != SRC_W:
            frame = cv2.resize(frame, (SRC_W, SRC_H))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (64, 36))
        cut = False
        if prev_small is not None:
            cut = float(np.mean(np.abs(small.astype(np.int16) - prev_small.astype(np.int16)))) > CUT_THRESH
        faces = detect_faces(frame)
        for f in faces:
            f["motion"] = mouth_motion(prev_gray, gray, f) if prev_gray is not None else 0.0
        recs.append({"t": round(t, 3), "faces": faces, "cut": cut})
        prev_gray = gray
        prev_small = small
        t += step
    cap.release()

    if not recs:
        return {"seg_dur": round(seg_dur, 3), "crop_w": CROP_W, "holds": [[0.0, DEFAULT_CX]]}

    # Pass 2: per-sample active face -> anchor (cx of bbox, ~nose height) + fh.
    # Anchor uses the bbox center-x (stable on turned/profile heads, unlike the
    # nose-tip landmark which drifts) and a point ~55% down the bbox as the
    # vertical "nose" line.
    win = max(1, int(0.6 * SAMPLE_FPS))
    anchors = []   # (ax, ay) or None per sample
    fhs = []       # bbox height or None per sample
    for i, rc in enumerate(recs):
        faces = rc["faces"]
        if not faces:
            anchors.append(None); fhs.append(None); continue
        fs = sorted(faces, key=lambda f: f["bbox"][2], reverse=True)
        lw = fs[0]["bbox"][2]
        second_w = fs[1]["bbox"][2] if len(fs) > 1 else 0
        if lw >= CLOSEUP_W and (len(fs) == 1 or lw >= 1.4 * second_w):
            pick = fs[0]                                    # close-up: trust it
        else:
            lo, hi = max(0, i - win), min(len(recs), i + win + 1)
            lsum = rsum = 0.0
            for j in range(lo, hi):
                for f in recs[j]["faces"]:
                    if f["cx"] < SRC_W // 2:
                        lsum += f["motion"]
                    else:
                        rsum += f["motion"]
            want_left = lsum * LEFT_BIAS >= rsum
            side = [f for f in faces if (f["cx"] < SRC_W // 2) == want_left]
            pick = max(side, key=lambda f: f["bbox"][2]) if side else fs[0]
        bx, by, bw, bh = pick["bbox"]
        anchors.append((float(bx + bw / 2.0), float(by + 0.55 * bh)))
        fhs.append(float(bh))

    coverage = sum(1 for a in anchors if a is not None) / max(1, len(anchors))

    # Pass 3: segment into SHOTS at scene cuts; each shot = one static crop from
    # the median face in that shot. No-face shots -> center + wide framing.
    CENTER = (SRC_W / 2.0, SRC_H * 0.42)
    bounds = sorted(set([0] + [i for i, rc in enumerate(recs) if i > 0 and rc.get("cut")] + [len(recs)]))
    shots = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        seg_a = [anchors[k] for k in range(a, b) if anchors[k] is not None]
        segf = [fhs[k] for k in range(a, b) if fhs[k] is not None]
        if seg_a:
            ax = float(np.median([p[0] for p in seg_a]))
            ay = float(np.median([p[1] for p in seg_a]))
            fh = float(np.median(segf)) if segf else 120.0
            cov = len(seg_a) / max(1, b - a)
        else:
            ax, ay = CENTER; fh = 90.0; cov = 0.0
        t0 = recs[a]["t"]
        t1 = recs[b]["t"] if b < len(recs) else seg_dur
        shots.append({"start": round(t0, 3), "end": round(t1, 3),
                      "ax": round(ax, 1), "ay": round(ay, 1),
                      "face_h": round(fh, 1), "coverage": round(cov, 2)})
    if shots:
        shots[0]["start"] = 0.0
        shots[-1]["end"] = round(seg_dur, 3)
    else:
        shots = [{"start": 0.0, "end": round(seg_dur, 3), "ax": CENTER[0], "ay": CENTER[1],
                  "face_h": 120.0, "coverage": 0.0}]
    face_h = float(np.median([f for f in fhs if f is not None])) if any(f is not None for f in fhs) else 200.0
    return {"seg_dur": round(seg_dur, 3), "shots": shots,
            "face_h": round(face_h, 1), "coverage": round(coverage, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("start", type=float)
    ap.add_argument("end", type=float)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    result = analyze(args.video, args.start, args.end)
    args.out.write_text(json.dumps(result, indent=2))
    print(f"holds: {len(result['holds'])}  -> {args.out}")
    for t, nx, ny in result["holds"]:
        print(f"  t={t:6.2f}s  nose=({nx:.0f},{ny:.0f})")


if __name__ == "__main__":
    main()
