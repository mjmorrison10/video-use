"""Local faster-whisper transcription -> canonical schema.

Canonical transcript.json schema (both STT paths emit this):
  {language, duration, segments:[{start,end,text,words:[{word,start,end}]}],
   words:[{word,start,end}]}   # `words` is the flat list the pipeline indexes into

Usage:
  stt.py SOURCE [--out edit/transcript.json] [--model medium.en] [--force]
  stt.py SOURCE --start 48 --end 53      # REGION MODE: prints absolute-time words to stdout
                                         # (for isolated re-transcription of a mis-heard spot)
"""
import argparse, json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, run, ffprobe_duration, extract_wav, edit_dir_for  # noqa

def transcribe(wav, model_name, params, device, compute_type):
    from faster_whisper import WhisperModel
    m = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, info = m.transcribe(wav, **params)
    out_segments, flat = [], []
    for seg in segments:
        ws = []
        for w in (seg.words or []):
            wd = {"word": w.word, "start": round(w.start, 3), "end": round(w.end, 3)}
            ws.append(wd); flat.append(wd)
        out_segments.append({"start": round(seg.start, 3), "end": round(seg.end, 3),
                             "text": seg.text.strip(), "words": ws})
    return info, out_segments, flat

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out")
    ap.add_argument("--model")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    style = load_style()["stt"]
    model_name = a.model or style["model"]
    params = dict(style["params"])
    device, compute = style["device"], style["compute_type"]

    region = a.start is not None or a.end is not None
    out = a.out or os.path.join(edit_dir_for(a.source), "transcript.json")

    if not region and not a.force and os.path.exists(out):
        d = json.load(open(out))
        print(f"[cached] {out} ({len(d['words'])} words)"); return

    with tempfile.TemporaryDirectory() as td:
        wav = extract_wav(a.source, os.path.join(td, "a.wav"), a.start, a.end)
        info, segs, flat = transcribe(wav, model_name, params, device, compute)

    if region:
        off = a.start or 0.0
        print(f"=== region {a.start}-{a.end}s (absolute times) ===")
        for w in flat:
            print(f"  [{w['start']+off:7.2f}-{w['end']+off:7.2f}] {w['word']!r}")
        return

    payload = {"language": info.language, "duration": round(info.duration, 3),
               "segments": segs, "words": flat}
    json.dump(payload, open(out, "w"), indent=1)
    with open(os.path.splitext(out)[0] + ".txt", "w") as f:
        for i, w in enumerate(flat):
            f.write(f"{i:4d} [{w['start']:7.2f}-{w['end']:7.2f}] {w['word']!r}\n")
    print(f"[done] {out}  ({len(flat)} words, {payload['duration']:.1f}s)")

if __name__ == "__main__":
    main()
