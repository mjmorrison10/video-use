#!/usr/bin/env python3
"""Transcribe a video/audio file with Whisper large-v3 and emit the three
deliverables we always want:

  <base>_full.txt        plain prose, paragraph breaks on natural pauses
  <base>_sentences.srt   one cue per sentence, real punctuation preserved
  <base>_words.json      word-level {text,start,end} — feeds the clip pipeline

large-v3 (not -turbo) with beam_size 5 is the most accurate config; on CPU it
runs ~2-3x slower than realtime, so this is a background job.

Usage: transcribe_all.py INPUT --outdir DIR --base NAME [--threads 4]
                                [--start S --end E]  (transcribe a slice only)
"""
import argparse, json, os, subprocess, sys, tempfile, time
from pathlib import Path


def ts_srt(t):
    ms = int(round(t * 1000)); h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


SENT_END = (".", "?", "!")


def sentences(words, max_chars=200, max_gap=1.2, pause_break=0.45, pause_min=90):
    """Split the word stream into sentence cues. Punctuation first; for the
    unpunctuated lowercase stretches Whisper sometimes emits, fall back to a
    real speech pause rather than a blunt character cut."""
    cues, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt_gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 99
        joined = "".join(x["text"] for x in cur).strip()
        unpunctuated = not any(c in joined for c in SENT_END)
        if (w["text"].strip().rstrip("\"”'").endswith(SENT_END)
                or nxt_gap >= max_gap
                or len(joined) >= max_chars
                or (unpunctuated and len(joined) >= pause_min and nxt_gap >= pause_break)):
            cues.append((cur[0]["start"], cur[-1]["end"], joined))
            cur = []
    if cur:
        cues.append((cur[0]["start"], cur[-1]["end"], "".join(x["text"] for x in cur).strip()))
    return cues


def paragraphs(words, gap=0.55, min_chars=420):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w["text"].strip())
        nxt_gap = (words[i + 1]["start"] - w["end"]) if i + 1 < len(words) else 99
        if nxt_gap >= gap and len(" ".join(cur)) >= min_chars:
            out.append(" ".join(cur)); cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--outdir", required=True); ap.add_argument("--base", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--end", type=float, default=None)
    a = ap.parse_args()

    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory() as tmp:
        # always decode from a 16k mono wav; ffmpeg handles any container
        wav = os.path.join(tmp, "a.wav")
        cmd = ["ffmpeg", "-y", "-v", "error"]
        if a.start is not None:
            cmd += ["-ss", f"{a.start:.3f}"]
        cmd += ["-i", a.input]
        if a.end is not None:
            cmd += ["-to", f"{a.end - (a.start or 0):.3f}"]
        subprocess.run(cmd + ["-ac", "1", "-ar", "16000", "-vn", wav], check=True)

        t0 = time.time()
        print(f"loading {a.model} ({a.threads} threads)...", flush=True)
        model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=a.threads)
        print("transcribing...", flush=True)
        segs, info = model.transcribe(
            wav, language="en", beam_size=5, word_timestamps=True,
            vad_filter=True, condition_on_previous_text=False)
        off = a.start or 0.0
        words = []
        for s in segs:
            for w in (s.words or []):
                if w.start is None or w.end is None:
                    continue
                words.append({"text": w.word, "start": round(w.start + off, 3),
                              "end": round(w.end + off, 3), "type": "word"})
            print(f"  {s.end + off:8.1f}s", end="\r", flush=True)

    if not words:
        sys.exit("no words transcribed")
    took = time.time() - t0

    (outdir / f"{a.base}_words.json").write_text(json.dumps(
        {"text": " ".join(w["text"].strip() for w in words), "words": words}, ensure_ascii=False))

    cues = sentences(words)
    (outdir / f"{a.base}_sentences.srt").write_text("\n".join(
        f"{i}\n{ts_srt(s)} --> {ts_srt(e)}\n{t}\n" for i, (s, e, t) in enumerate(cues, 1)))

    paras = paragraphs(words)
    (outdir / f"{a.base}_full.txt").write_text("\n\n".join(paras) + "\n")

    print(f"\n[stt] {len(words)} words, {len(cues)} sentences, {len(paras)} paragraphs "
          f"| span {words[0]['start']:.1f}-{words[-1]['end']:.1f}s | {took/60:.1f} min")
    for f in (f"{a.base}_full.txt", f"{a.base}_sentences.srt", f"{a.base}_words.json"):
        print(f"   {outdir/f}")


if __name__ == "__main__":
    main()
