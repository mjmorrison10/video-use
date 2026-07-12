"""Self-eval artifacts for the agent to inspect before delivery (does NOT auto-pass/fail):
  1. verify/contact.jpg   — one labeled frame per segment (framing + captions at a glance)
  2. trouble report        — re-transcribes RENDERED audio at known trouble spots (span-first
     words, onset-lead words, protect-range words) and prints expected vs heard, so the agent
     catches clipped/missing words (the "Son"/"famous before" class of bug).

Usage: selfcheck.py RENDERED.mp4 JOB.yaml   (reads sibling edit/plan.json, edit/transcript.json)
"""
import argparse, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, load_yaml, run, extract_wav  # noqa

def out_time_of(word_start, segs):
    """Map a source word-start to its output time via the best-overlap (or containing) segment."""
    best, bov = None, -1
    for s in segs:
        if s["s"] <= word_start <= s["e"]:
            return s["off"] + (word_start - s["s"])
        ov = min(word_start + 0.05, s["e"]) - max(word_start, s["s"])
        if ov > bov:
            bov, best = ov, s
    return best["off"] + (max(word_start, best["s"]) - best["s"]) if best else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rendered")
    ap.add_argument("job")
    a = ap.parse_args()
    job = load_yaml(a.job)
    ed = os.path.join(os.path.dirname(os.path.abspath(job["video"]["source"])), "edit")
    segs = json.load(open(os.path.join(ed, "plan.json")))["segs"]
    words = json.load(open(os.path.join(ed, "transcript.json")))["words"]
    over = {int(k): v for k, v in (job.get("text_overrides") or {}).items()}
    vdir = os.path.join(ed, "verify"); os.makedirs(vdir, exist_ok=True)

    # ---- 1. contact sheet: one frame per segment at its midpoint ----
    from PIL import Image, ImageDraw
    thumbs = []
    with tempfile.TemporaryDirectory() as td:
        for i, s in enumerate(segs):
            mid = s["off"] + s["dur"] / 2
            fp = os.path.join(td, f"t{i:03d}.jpg")
            run(["ffmpeg", "-v", "error", "-ss", f"{mid:.3f}", "-i", a.rendered,
                 "-frames:v", "1", "-vf", "scale=270:480", fp])
            im = Image.open(fp).convert("RGB")
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 120, 22], fill=(0, 0, 0))
            d.text((3, 4), f"{i} {s['cam']} {mid:.1f}s", fill=(0, 255, 0))
            thumbs.append(im)
    cols = 7; rows = (len(thumbs) + cols - 1) // cols
    w, h = thumbs[0].size
    sheet = Image.new("RGB", (cols * w, rows * h), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet_path = os.path.join(vdir, "contact.jpg")
    sheet.save(sheet_path, quality=88)
    print(f"[contact] {sheet_path}  ({len(thumbs)} segments, {cols}x{rows})")

    # ---- 2. trouble-spot re-transcription of RENDERED audio ----
    trouble = {}  # word_index -> output_time
    for span in job["spans"]:
        trouble[span["words"][0]] = None
    for k in (job.get("onset_leads") or {}):
        trouble[int(k)] = None
    for (t0, t1) in (job.get("protect") or []):
        for i, w in enumerate(words):
            if t0 <= w["start"] <= t1:
                trouble[i] = None
    for i in list(trouble):
        trouble[i] = out_time_of(words[i]["start"], segs)

    from faster_whisper import WhisperModel
    style = load_style()["stt"]
    m = WhisperModel(style["model"], device=style["device"], compute_type=style["compute_type"])
    report = ["=== trouble-spot check (expected vs heard in RENDERED audio) ==="]
    with tempfile.TemporaryDirectory() as td:
        for i in sorted(trouble, key=lambda i: trouble[i] or 0):
            ot = trouble[i]
            if ot is None:
                continue
            wav = extract_wav(a.rendered, os.path.join(td, "r.wav"), max(0, ot - 1.0), ot + 1.4)
            segs_h, _ = m.transcribe(wav, word_timestamps=False, vad_filter=False,
                                     condition_on_previous_text=False, beam_size=5)
            heard = " ".join(s.text.strip() for s in segs_h)
            expect = over.get(i, words[i]["word"].strip())
            ok = expect.strip(".,!?").lower() in heard.lower()
            report.append(f"  [{ot:6.2f}s] expect {expect!r:22} {'OK ' if ok else 'CHECK'} heard: {heard!r}")
    txt = "\n".join(report)
    open(os.path.join(vdir, "trouble.txt"), "w").write(txt + "\n")
    print(txt)
    print(f"[trouble] {os.path.join(vdir,'trouble.txt')}")

if __name__ == "__main__":
    main()
