"""Detect faces across a video, then cluster by horizontal position so the agent can pick
the subject and define <=2 fixed 'cameras' in job.yaml.

Writes:
  edit/face_track.json  -> flat list of ALL plausible detections: [{t,fx,fy,w,h}, ...]
  edit/cameras.json     -> {source:{w,h}, n_detections, fx_percentiles, clusters:[
                              {fx,fy,w,count,fx_range:[lo,hi],t_coverage,sample_t}, ...]}

Plausibility bounds (reject hands-as-faces, tiny/huge boxes) come from style.yaml:framing
as fractions of the source dimensions. Clustering is a deterministic 1D gap-split on fx.
The agent reads cameras.json (and may sample frames at each cluster's sample_t) to decide
which cluster(s) are the subject vs other people, then writes cameras/subject_filter to job.yaml.

Usage: faces.py SOURCE [--fps 3]
"""
import argparse, glob, json, os, statistics as st, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, run, edit_dir_for  # noqa

def detect_boxes(gray, frontal, profile):
    import cv2
    boxes = []
    for c in (frontal, profile):
        for (x, y, w, h) in c.detectMultiScale(gray, 1.1, 5, minSize=(70, 70)):
            boxes.append((x, y, w, h))
    W = gray.shape[1]
    for (x, y, w, h) in profile.detectMultiScale(cv2.flip(gray, 1), 1.1, 5, minSize=(70, 70)):
        boxes.append((W - (x + w), y, w, h))
    return boxes

def cluster_1d(dets, gap=160, min_count=4):
    """Greedy gap-split on fx (deterministic). dets: list of dicts with 'fx'."""
    if not dets:
        return []
    s = sorted(dets, key=lambda d: d["fx"])
    clusters, cur = [], [s[0]]
    for d in s[1:]:
        if d["fx"] - cur[-1]["fx"] <= gap:
            cur.append(d)
        else:
            clusters.append(cur); cur = [d]
    clusters.append(cur)
    return [c for c in clusters if len(c) >= min_count]

def main():
    import cv2
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--fps", type=float, default=3.0)
    a = ap.parse_args()
    ed = edit_dir_for(a.source)
    style = load_style()["framing"]

    # source dims
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(a.source)])
    SW, SH = [int(x) for x in r.stdout.strip().split("x")[:2]]
    fy_min = style["subject_fy_min_frac"] * SH
    fy_max = style["subject_fy_max_frac"] * SH
    w_lo, w_hi = [f * SW for f in style["subject_w_bounds_frac"]]

    frontal = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    profile = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")

    track = []
    with tempfile.TemporaryDirectory() as td:
        run(["ffmpeg", "-v", "error", "-i", str(a.source), "-vf", f"fps={a.fps}",
             os.path.join(td, "f_%05d.jpg")])
        frames = sorted(glob.glob(os.path.join(td, "f_*.jpg")))
        for i, fp in enumerate(frames):
            t = (i + 0.5) / a.fps
            img = cv2.imread(fp)
            gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
            for (x, y, w, h) in detect_boxes(gray, frontal, profile):
                fx, fy = int(x + w / 2), int(y + h / 2)
                if w_lo <= w <= w_hi and fy_min <= fy <= fy_max:
                    track.append({"t": round(t, 2), "fx": fx, "fy": fy, "w": int(w), "h": int(h)})

    json.dump(track, open(os.path.join(ed, "face_track.json"), "w"))

    clusters = cluster_1d(track)
    total_t = len({d["t"] for d in track}) or 1
    cam_out = []
    for c in clusters:
        cam_out.append({
            "fx": int(st.median(d["fx"] for d in c)),
            "fy": int(st.median(d["fy"] for d in c)),
            "w":  int(st.median(d["w"] for d in c)),
            "count": len(c),
            "fx_range": [min(d["fx"] for d in c), max(d["fx"] for d in c)],
            "t_coverage": round(len({d["t"] for d in c}) / total_t, 2),
            "sample_t": round(st.median(sorted(d["t"] for d in c)), 2),
        })
    cam_out.sort(key=lambda c: -c["count"])
    fxs = sorted(d["fx"] for d in track)
    pct = lambda p: fxs[int(p * (len(fxs) - 1))] if fxs else None
    cams = {"source": {"w": SW, "h": SH}, "n_detections": len(track),
            "fx_percentiles": {"p10": pct(.10), "p50": pct(.50), "p90": pct(.90)},
            "clusters": cam_out}
    json.dump(cams, open(os.path.join(ed, "cameras.json"), "w"), indent=1)
    print(f"[done] {len(track)} detections, {len(cam_out)} clusters:")
    for c in cam_out:
        print(f"   fx={c['fx']:4} fy={c['fy']:3} w={c['w']:3} n={c['count']:4} "
              f"range={c['fx_range']} cover={c['t_coverage']} @t={c['sample_t']}")

if __name__ == "__main__":
    main()
