"""Generate ALL-CAPS serif ASS captions (white + neon accent words, pop animation), burn LAST
onto base.mp4, then two-pass loudnorm -> <stem>_clean.mp4.

Ports video-work/captions4.py; style constants come from style.yaml, per-video content
(accents, text_overrides, spans) from job.yaml.

Usage: captions.py JOB.yaml   (reads edit/plan.json + base.mp4; writes edit/master.ass + <stem>_clean.mp4)
"""
import argparse, json, os, sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, load_yaml, run, REPO, ffprobe_dims  # noqa
sys.path.insert(0, os.path.join(REPO, "helpers"))
import render as rndr  # noqa

def T(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    a = ap.parse_args()
    job = load_yaml(a.job)
    style = load_style()
    # per-video caption overrides (e.g. pos for the fit layout) via job.style_overrides.captions
    cap = dict(style["captions"])
    cap.update((job.get("style_overrides") or {}).get("captions", {}))
    ed = os.path.join(os.path.dirname(os.path.abspath(job["video"]["source"])), "edit")
    stem = job["video"]["stem"]
    # captions can be disabled per clip (cinematic drama scenes "breathe" uncaptioned): still
    # produce the two deliverables from base.mp4 — captioned (a copy, for music) + loudnorm clean.
    if job.get("captions", True) is False:
        captioned = os.path.join(ed, f"{stem}_captioned.mp4")
        clean = os.path.join(ed, f"{stem}_clean.mp4")
        import shutil
        shutil.copy(os.path.join(ed, "base.mp4"), captioned)
        ok = rndr.apply_loudnorm_two_pass(Path(captioned), Path(clean))
        if not ok:
            shutil.copy(captioned, clean)
        from _util import ffprobe_duration
        print(f"[done] {clean}  ({ffprobe_duration(clean):.2f}s, NO captions, loudnorm={ok})")
        return
    words = json.load(open(os.path.join(ed, "transcript.json")))["words"]
    segs = json.load(open(os.path.join(ed, "plan.json")))["segs"]

    # framing-aware caption placement: on blur-fill (fit / fit-center) clips the captions sit
    # right BELOW the video window (in the fill band), phrase-length for dialogue; on full-bleed
    # clips they use the profile position (e.g. centred) with the profile's tight word chunks.
    OW_, OH_ = style["output"]["width"], style["output"]["height"]
    framing = job.get("cameras")
    if framing in ("fit", "fit-center"):
        src_w, src_h = ffprobe_dims(job["video"]["source"])
        A = job.get("fit_aspect") or (src_w / src_h)
        fg_h = min(OH_, int(round(OW_ / A)))
        top = (OH_ - fg_h) // 2 if framing == "fit-center" else max(80, (OH_ - fg_h) // 2 - 300)
        # sit in the BOTTOM PART of the video window (overlay the lower portion), not below it
        cap["pos"] = {"x": OW_ // 2, "y": top + fg_h - max(96, int(0.09 * fg_h))}
        cap["align_an"] = 5  # centered anchor, inside the lower part of the window
        cap["max_words"] = cap.get("fit_max_words", 5)
        cap["max_chars"] = cap.get("fit_max_chars", 28)

    OVER = {int(k): v for k, v in (job.get("text_overrides") or {}).items()}
    ACCENT = {str(w).strip(".,!?").upper() for w in (job.get("accents") or [])}
    MAXW, MAXC, MERGE = cap["max_words"], cap["max_chars"], cap["merge_below_s"]

    def wtext(i):
        return OVER.get(i, words[i]["word"].strip())

    def strip(t):
        return t.strip(".,!?").upper()

    def nopunct(t):
        return "".join(c for c in t if c not in ".,!?") if cap["strip_punctuation"] else t

    # map each kept word onto the output timeline (best-overlap segment; containment fallback)
    mapped = []
    for span in job["spans"]:
        a0, b0 = span["words"]
        for i in range(a0, b0 + 1):
            ws, we = words[i]["start"], words[i]["end"]
            best, bov, bidx = None, 0, -1
            for si, s in enumerate(segs):
                ov = min(we, s["e"]) - max(ws, s["s"])
                if ov > bov:
                    bov, best, bidx = ov, s, si
            if not best or bov <= 0.02:
                for si, s in enumerate(segs):
                    if s["s"] <= ws <= s["e"]:
                        best, bidx = s, si; break
                if not best:
                    continue
            os_ = best["off"] + (max(ws, best["s"]) - best["s"])
            oe_ = best["off"] + (min(we, best["e"]) - best["s"])
            txt = wtext(i)
            if cap["uppercase"]:
                txt = txt.upper()
            mapped.append([round(os_, 3), round(max(oe_, os_ + 0.08), 3), txt, bidx])
    mapped.sort()

    # chunk <=MAXW words / <=MAXC chars; break on punctuation and segment change
    caps, chunk, chars, cur = [], [], 0, None

    def flush():
        nonlocal chunk, chars
        if chunk:
            caps.append([chunk[0][0], chunk[-1][1], [[c[0], c[1], c[2]] for c in chunk]])
            chunk, chars = [], 0

    for s, e, t, si in mapped:
        if chunk and (len(chunk) >= MAXW or chars + len(t) + 1 > MAXC or si != cur):
            flush()
        cur = si; chunk.append((s, e, t)); chars += len(t) + 1
        if t.endswith((".", "?", "!", ",")):
            flush()
    flush()
    # merge ultra-short caps (bad ASR timing) into previous so they stay readable
    merged = []
    for c in caps:
        if merged and (c[1] - c[0]) < MERGE and len(merged[-1][2]) + len(c[2]) <= 4:
            merged[-1][2] += c[2]; merged[-1][1] = c[1]
        else:
            merged.append(c)
    caps = merged
    for k in range(len(caps) - 1):
        caps[k][1] = caps[k + 1][0]
    caps[-1][1] += 0.3

    WHITE, NEON = cap["primary"], cap["accent"]
    bold = -1 if cap["bold"] else 0
    p = cap["pos"]
    style_line = (f"Style: Cap,{cap['font']},{cap['size']},{WHITE},{WHITE},"
                  f"{cap['outline_colour']},{cap['back_colour']},{bold},0,0,0,100,100,0,0,1,"
                  f"{cap['outline']},{cap['shadow']},{cap['align_an']},0,0,0,1")
    # animation: "pop" (default — scale-in karaoke, the loud house style) | "fade" (gentle
    # opacity rise, the cinematic/literary style) | "none". Default keeps existing clients identical.
    anim = cap.get("anim", "pop")
    base_tag = f"\\an{cap['align_an']}\\pos({p['x']},{p['y']})"
    if anim == "fade":
        fd = cap.get("fade", {"in": 180, "out": 120})
        POP = f"{{{base_tag}\\fad({fd['in']},{fd['out']})}}"
    elif anim == "none":
        POP = f"{{{base_tag}}}"
    else:
        pop = cap["pop"]
        POP = (f"{{{base_tag}"
               f"\\fscx{pop['fscx_from']}\\fscy{pop['fscy_from']}"
               f"\\t(0,{pop['ms']},\\fscx{pop['to']}\\fscy{pop['to']})}}")
    head = ("[Script Info]\nScriptType: v4.00+\n"
            f"PlayResX: {style['output']['width']}\nPlayResY: {style['output']['height']}\n"
            "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"{style_line}\n\n[Events]\n"
            "Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = [head]
    for cs, ce, items in caps:
        parts = [f"{{\\c{NEON if strip(t) in ACCENT else WHITE}&}}{nopunct(t)}" for (s, e, t) in items]
        lines.append(f"Dialogue: 0,{T(cs)},{T(ce)},Cap,0,0,0,,{POP}" + " ".join(parts) + r"{\c" + WHITE + "&}")
    ass_path = os.path.join(ed, "master.ass")
    open(ass_path, "w").write("\n".join(lines) + "\n")
    print(f"{len(caps)} caption chunks:")
    for c in caps:
        print("  [%5.2f-%5.2f] %s" % (c[0], c[1],
              " ".join(("[" + x[2] + "]" if strip(x[2]) in ACCENT else x[2]) for x in c[2])))

    OW, OH = style["output"]["width"], style["output"]["height"]
    CRF, PRESET = style["output"]["crf"], style["output"]["x264_preset"]
    stem = job["video"]["stem"]
    # captioned (pre-loudnorm) is kept so music_mix can preserve the tuned voice/music balance
    captioned = os.path.join(ed, f"{stem}_captioned.mp4")
    clean = os.path.join(ed, f"{stem}_clean.mp4")
    run(["ffmpeg", "-y", "-i", os.path.join(ed, "base.mp4"), "-vf", f"ass={ass_path}",
         "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
         "-crf", str(CRF), "-preset", PRESET, "-c:a", "copy", "-movflags", "+faststart", captioned])
    ok = rndr.apply_loudnorm_two_pass(Path(captioned), Path(clean))
    if not ok:
        import shutil; shutil.copy(captioned, clean)
    from _util import ffprobe_duration
    print(f"[done] {clean}  ({ffprobe_duration(clean):.2f}s, loudnorm={ok}); kept {os.path.basename(captioned)} for music")

if __name__ == "__main__":
    main()
