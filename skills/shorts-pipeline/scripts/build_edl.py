"""Compile job.yaml + style.yaml + transcript/faces/silences -> plan.json (the vertical EDL).

Generalizes video-work/plan4.py: silence-subtraction cutting (protect ranges honored),
per-phrase onset leads, two-camera A/B assignment with lean-transition splits, and per-segment
crop rects (derived from face medians via the safe-zone math, or explicit per-camera override).

plan.json schema: {"segs":[{s,e,dur,off,W,H,x,y,cam}, ...]}  (source in/out, output offset, crop)

Usage: build_edl.py JOB.yaml   (reads edit/ siblings; writes edit/plan.json)
"""
import argparse, json, os, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, load_yaml, even, clamp, ffprobe_dims  # noqa

def derive_crop(fx, fy, fw, SW, SH, style):
    F = style["framing"]; OW = style["output"]["width"]
    wmax = min(F["crop_w_bounds"][1], int(SH * 9 / 16))
    wmin = min(F["crop_w_bounds"][0], wmax)
    W = clamp(fw * OW / F["target_face_w_px"], wmin, wmax)
    H = W * 16 / 9
    if H > SH:
        H = SH; W = H * 9 / 16
    W, H = even(W), even(H)
    cx = even(clamp(round(fx - F["face_target"]["x"] * W), 0, SW - W))
    cy = even(clamp(round(fy - F["face_target"]["y"] * H), 0, SH - H))
    return dict(W=W, H=H, x=cx, y=cy)

def resolve_cameras(job, SW, SH, style):
    cams_cfg = job["cameras"]
    if cams_cfg == "center-crop":
        W = even(min(int(SH * 9 / 16), SW)); H = even(min(SH, int(W * 16 / 9)))
        W = even(min(W, int(H * 9 / 16)))
        return {"C": dict(W=W, H=H, x=even((SW - W) // 2), y=even((SH - H) // 2), cam="C")}, None
    out = {}
    for name, c in cams_cfg.items():
        if "crop" in c:
            cr = c["crop"]; out[name] = dict(W=cr["W"], H=cr["H"], x=cr["x"], y=cr["y"], cam=name)
        else:
            out[name] = dict(cam=name, **derive_crop(c["fx"], c["fy"], c["face_w"], SW, SH, style))
    return out, cams_cfg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    a = ap.parse_args()
    job = load_yaml(a.job)
    style = load_style()
    ed = os.path.join(os.path.dirname(os.path.abspath(job["video"]["source"])), "edit")
    words = json.load(open(os.path.join(ed, "transcript.json")))["words"]
    sil = [tuple(x) for x in json.load(open(os.path.join(ed, "silences.json")))]

    # "fit" mode: no cropping/faces — the full 16:9 frame is letterboxed over a blurred fill
    # (render_vertical handles the compositing). Good for chart/screen-share content where
    # cropping would cut off graphs. Faces/cameras are not needed.
    FIT = job.get("cameras") == "fit"
    if FIT:
        track, cams_meta = [], None
        SW, SH = ffprobe_dims(job["video"]["source"])
    else:
        track = json.load(open(os.path.join(ed, "face_track.json")))
        cams_meta = json.load(open(os.path.join(ed, "cameras.json")))
        SW, SH = cams_meta["source"]["w"], cams_meta["source"]["h"]

    C = style["cutting"]
    SIL_MIN, EDGE, LEAD_MAX = C["sil_min_remove_s"], C["edge_pad_s"], C["lead_max_s"]
    MIN_SEG = style["framing"]["min_cam_segment_s"]
    BIAS = C.get("lean_split_bias_s", 0.2)
    MIN_KEEP = 0.12

    PROTECT = [tuple(p) for p in job.get("protect", [])]
    leads = {int(k): v for k, v in (job.get("onset_leads") or {}).items()}
    sf = job.get("subject_filter") or {"fx": [0, SW], "fy": [0, SH], "w": [0, SW]}

    def protected(s, e):
        return any(ps < e and pe > s for ps, pe in PROTECT)

    def subtract(s, e):
        cuts = sorted((max(ss, s), min(se, e)) for ss, se in sil
                      if se - ss >= SIL_MIN and se > s and ss < e and not protected(ss, se))
        outs, pos = [], s
        for cs, ce in cuts:
            if cs + EDGE - pos > MIN_KEEP:
                outs.append((pos, cs + EDGE))
            pos = ce - EDGE
        if e - pos > MIN_KEEP:
            outs.append((pos, e))
        return outs

    # "follow" mode: per-segment crop centered on the dominant (closest/largest) face — for
    # multi-camera or general content where the framing changes with the source's own cuts.
    import statistics as _st
    FOLLOW = job.get("cameras") == "follow"
    Wc = even(min(style["framing"]["crop_w_bounds"][1], int(SH * 9 / 16)))
    Hc = even(min(SH, int(Wc * 16 / 9))); Wc = even(min(Wc, int(Hc * 9 / 16)))
    CENTER = dict(W=Wc, H=Hc, x=even((SW - Wc) // 2), y=even((SH - Hc) // 2), cam="F")

    def seg_follow(s, e):
        dets = [p for p in track if p["fx"] is not None and s - 0.15 <= p["t"] <= e + 0.15
                and sf["w"][0] <= p["w"] <= sf["w"][1]
                and sf["fy"][0] <= p["fy"] <= sf["fy"][1]
                and sf["fx"][0] <= p["fx"] <= sf["fx"][1]]
        if not dets:
            return dict(CENTER)
        # cluster faces by x (gap-split) and pick ONE cluster — the closest/active subject —
        # never average across two people (that lands the crop between them, e.g. on the pool).
        ds = sorted(dets, key=lambda p: p["fx"])
        clusters = [[ds[0]]]
        for p in ds[1:]:
            if p["fx"] - clusters[-1][-1]["fx"] <= 200:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        def med(vals):
            v = sorted(vals); return v[len(v) // 2]
        chosen = max(clusters, key=lambda c: (med([p["w"] for p in c]), len(c)))  # largest face wins
        fx = int(med([p["fx"] for p in chosen])); fy = int(med([p["fy"] for p in chosen]))
        fw = int(med([p["w"] for p in chosen]))
        c = derive_crop(fx, fy, fw, SW, SH, style); c["cam"] = "F"; return c

    if FIT:
        CAM, cams_cfg = {"FIT": dict(W=SW, H=SH, x=0, y=0, cam="FIT")}, None
    elif FOLLOW:
        CAM, cams_cfg = {"F": CENTER}, None
    else:
        CAM, cams_cfg = resolve_cameras(job, SW, SH, style)
    single_cam = None if len(CAM) > 1 else next(iter(CAM))
    ftx = style["framing"]["face_target"]["x"]
    # each camera's implied subject face-x (from fx if given, else recovered from the crop rect)
    def cam_face_fx(name):
        c = cams_cfg[name] if cams_cfg else {}
        if "fx" in c:
            return c["fx"]
        r = CAM[name]
        return r["x"] + ftx * r["W"]
    # two-camera A/B split threshold (midpoint of the two camera fx, or job override)
    split_fx = None
    if cams_cfg and len(cams_cfg) == 2 and single_cam is None:
        names = list(cams_cfg.keys())
        split_fx = job.get("split_fx")
        if split_fx is None:
            split_fx = sum(cam_face_fx(n) for n in names) / 2
        lo_name = min(names, key=cam_face_fx)
        hi_name = max(names, key=cam_face_fx)
    else:
        lo_name = hi_name = single_cam

    def real_dets(s, e):
        return sorted((p["t"], p["fx"]) for p in track if p["fx"] is not None
                      and s - 0.15 <= p["t"] <= e + 0.15
                      and sf["w"][0] <= p["w"] <= sf["w"][1]
                      and sf["fy"][0] <= p["fy"] <= sf["fy"][1]
                      and sf["fx"][0] <= p["fx"] <= sf["fx"][1])

    def cam_of(fx):
        return lo_name if fx < split_fx else hi_name

    def cam_segments(s, e):
        if single_cam:
            return [(s, e, single_cam)]
        d = real_dets(s, e)
        A = [t for t, fx in d if fx < split_fx]
        B = [t for t, fx in d if fx >= split_fx]
        if min(len(A), len(B)) < 2:
            return [(s, e, hi_name if len(B) > len(A) else lo_name)]
        best, bt, to = 0, None, None
        for i in range(1, len(d)):
            ca, cb = cam_of(d[i - 1][1]), cam_of(d[i][1])
            if ca != cb and abs(d[i][1] - d[i - 1][1]) > best:
                best = abs(d[i][1] - d[i - 1][1])
                bt = (d[i - 1][0] + BIAS) if cb == lo_name else (d[i][0] - BIAS)
                to = cb
        if bt is None:
            return [(s, e, hi_name if len(B) > len(A) else lo_name)]
        bt = clamp(bt, s + BIAS, e - BIAS)
        first = cam_of(d[0][1])
        if bt - s < MIN_SEG or e - bt < MIN_SEG:
            return [(s, e, hi_name if len(B) > len(A) else lo_name)]
        return [(s, bt, first), (bt, e, to)]

    segs, off = [], 0.0
    for span in job["spans"]:
        a0, b0 = span["words"]
        subs = subtract(words[a0]["start"], words[b0]["end"])
        if subs:
            cap = clamp(leads.get(a0, 0.0), 0, LEAD_MAX)
            gap = (words[a0]["start"] - words[a0 - 1]["end"]) if a0 > 0 else 9
            lead = clamp(gap - 0.05, 0, cap)
            ns = max(0.0, subs[0][0] - lead)
            if a0 > 0:
                ns = max(ns, words[a0 - 1]["end"])
            subs[0] = (ns, subs[0][1])
        for (s, e) in subs:
            if FOLLOW:
                segs.append(dict(s=round(s, 3), e=round(e, 3), dur=round(e - s, 3),
                                 off=round(off, 3), **seg_follow(s, e)))
                off += e - s
            else:
                for (ss, ee, cam) in cam_segments(s, e):
                    segs.append(dict(s=round(ss, 3), e=round(ee, 3), dur=round(ee - ss, 3),
                                     off=round(off, 3), **CAM[cam]))
                    off += ee - ss

    json.dump({"segs": segs}, open(os.path.join(ed, "plan.json"), "w"), indent=1)
    print(f"[done] {len(segs)} segments, TOTAL={off:.2f}s  cameras={dict(Counter(s['cam'] for s in segs))}")
    lo, hi = style["output"]["target_len_s"]
    if not (lo <= off <= hi):
        print(f"[WARN] duration {off:.1f}s outside target {lo}-{hi}s")

if __name__ == "__main__":
    main()
