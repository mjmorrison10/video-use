"""Resumable chunked transcription (restart-safe).

Transcribes [start,end] in fixed chunks, saving each chunk to its own JSON so a
container restart only loses the in-flight chunk. Merges all chunks (absolute
timestamps) into the output transcript in the pipeline's word schema.

Usage:
    python transcribe_chunks.py <video> <out.json> --start S --end E --chunk 720
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

CHUNK_DIR = Path("/home/user/claude-video-editor/edit/transcripts/chunks")


def extract_wav(video, start, dur, dest):
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{dur:.3f}",
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, required=True)
    ap.add_argument("--chunk", type=float, default=720.0)
    ap.add_argument("--model", default="small.en")
    args = ap.parse_args()

    from faster_whisper import WhisperModel
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=0)

    starts = []
    s = args.start
    while s < args.end:
        starts.append(s); s += args.chunk

    with tempfile.TemporaryDirectory() as tmp:
        for i, cs in enumerate(starts):
            ce = min(args.end, cs + args.chunk)
            cf = CHUNK_DIR / f"chunk_{int(cs):06d}.json"
            if cf.exists():
                print(f"chunk {i+1}/{len(starts)} [{cs:.0f}-{ce:.0f}] cached", flush=True)
                continue
            print(f"chunk {i+1}/{len(starts)} [{cs:.0f}-{ce:.0f}] transcribing", flush=True)
            wav = Path(tmp) / f"c{i}.wav"
            extract_wav(args.video, cs, ce - cs, wav)
            segs, _ = model.transcribe(str(wav), language="en", word_timestamps=True,
                                       vad_filter=True, vad_parameters={"min_silence_duration_ms": 300})
            words = []
            for seg in segs:
                for w in (seg.words or []):
                    t = (w.word or "").strip()
                    if t:
                        words.append({"type": "word", "text": t,
                                      "start": round(w.start + cs, 3),
                                      "end": round(w.end + cs, 3), "speaker_id": None})
            cf.write_text(json.dumps(words))
            print(f"  chunk done: {len(words)} words", flush=True)

    # merge all chunks covering [start,end]
    allw = []
    for cf in sorted(CHUNK_DIR.glob("chunk_*.json")):
        cs = int(cf.stem.split("_")[1])
        if args.start - 1 <= cs < args.end:
            allw.extend(json.loads(cf.read_text()))
    allw.sort(key=lambda w: w["start"])
    args.out.write_text(json.dumps({"words": allw}, indent=2))
    print(f"\nmerged {len(allw)} words -> {args.out}")


if __name__ == "__main__":
    main()
