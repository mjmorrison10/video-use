#!/usr/bin/env python3
"""Chunked, word-level transcription via faster-whisper (no API key).

Handoff gotcha #1: full-file Whisper passes on this content truncate/drop words.
Mitigation: transcribe in ~180s windows and keep each word whose start falls
inside the window, then concatenate. Emits a flat word list compatible with the
video-use / Scribe schema so downstream (editorial + Remotion caption builder)
can consume it uniformly.

Usage:
  uv run --with faster-whisper python transcribe_whisper.py AUDIO.wav \
      -o edit/transcript.json [--model medium.en] [--chunk 180] [--lang en]
"""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", help="16kHz mono wav")
    ap.add_argument("-o", "--out", default="transcript.json")
    ap.add_argument("--model", default="medium.en")
    ap.add_argument("--chunk", type=float, default=180.0, help="chunk seconds")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    from faster_whisper import WhisperModel, decode_audio

    print(f"[stt] loading audio {args.audio}", flush=True)
    sr = 16000
    audio = decode_audio(args.audio, sampling_rate=sr)
    total_s = len(audio) / sr
    end_s = args.end if args.end is not None else total_s
    print(f"[stt] duration={total_s:.1f}s, transcribing [{args.start:.0f},{end_s:.0f}]s "
          f"in {args.chunk:.0f}s chunks with model={args.model}", flush=True)

    print("[stt] loading model (may download on first run)...", flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    words = []
    full_text_parts = []
    lo = args.start
    while lo < end_s:
        hi = min(lo + args.chunk, end_s)
        a = int(lo * sr)
        b = int(hi * sr)
        seg_audio = audio[a:b]
        segments, _info = model.transcribe(
            seg_audio,
            language=args.lang,
            word_timestamps=True,
            condition_on_previous_text=False,
            vad_filter=True,
            beam_size=5,
        )
        kept = 0
        for seg in segments:
            if seg.words is None:
                continue
            for w in seg.words:
                wstart = w.start + lo
                wend = w.end + lo
                # keep only words that begin inside this window (dedup at seams)
                if wstart < lo or wstart >= hi:
                    continue
                text = w.word
                words.append({
                    "text": text,
                    "start": round(wstart, 3),
                    "end": round(wend, 3),
                    "type": "word",
                    "speaker_id": "speaker_0",
                })
                full_text_parts.append(text)
                kept += 1
        print(f"[stt] chunk [{lo:.0f},{hi:.0f}]s -> {kept} words "
              f"(total {len(words)})", flush=True)
        lo = hi

    out = {
        "language_code": args.lang,
        "text": "".join(full_text_parts).strip(),
        "words": words,
        "source_audio": str(Path(args.audio).resolve()),
        "model": args.model,
    }
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"[stt] wrote {len(words)} words -> {outp}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
