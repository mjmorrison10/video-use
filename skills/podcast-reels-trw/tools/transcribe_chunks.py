"""Accurate, resumable word-level transcription (restart-safe).

WHY THIS IS WINDOWED, NOT ONE LONG PASS: faster-whisper's word timestamps are
accurate only within Whisper's first internal 30s window; past that they
ACCUMULATE drift (measured ~1.9s off by the 80s mark on a 720s pass). Cutting and
captioning both read these times, so drift makes clips start early AND captions
run ahead of the audio. The fix: transcribe in short overlapping windows and keep
each word ONLY from the window where it sits in the accurate early zone.

How it works: slide a `--window` (default 35s) with a `--stride` commit zone
(default 25s). Each window is transcribed fresh from its own start, and only the
words in its first `stride` seconds are committed (that zone is inside Whisper's
first internal 30s window, so it's accurate). The extra `window-stride` tail is
lookahead so a word straddling the commit boundary is still fully transcribed;
the next window commits it from its accurate zone. Windows are cached per start
so a container restart only loses the in-flight one.

vad_filter is OFF by default: on a long pass its silence-removal remap ALSO
drifts. Short windows don't need it.

Usage:
    python transcribe_chunks.py <video> <out.json> --end <dur> [--window 35 --stride 25]
"""
from __future__ import annotations
import argparse, json, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as P
import os as _os

# per-window cache under the project's transcripts dir
CHUNK_DIR = Path(_os.environ.get("PODCAST_CHUNK_DIR", P.chunks_dir()))


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
    ap.add_argument("--window", type=float, default=35.0, help="transcription window length (s)")
    ap.add_argument("--stride", type=float, default=25.0,
                    help="commit zone (s); must be < ~28 to stay in Whisper's accurate first-window")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--vad", action="store_true", help="enable vad_filter (off by default; it drifts)")
    args = ap.parse_args()

    from faster_whisper import WhisperModel
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=0)

    starts = []
    s = args.start
    while s < args.end:
        starts.append(s); s += args.stride

    with tempfile.TemporaryDirectory() as tmp:
        for i, cs in enumerate(starts):
            we = min(args.end, cs + args.window)        # window (with lookahead tail)
            cf = CHUNK_DIR / f"win_{int(round(cs)):06d}.json"
            if cf.exists():
                print(f"window {i+1}/{len(starts)} [{cs:.0f}-{we:.0f}] cached", flush=True)
                continue
            print(f"window {i+1}/{len(starts)} [{cs:.0f}-{we:.0f}] transcribing", flush=True)
            wav = Path(tmp) / f"w{i}.wav"
            extract_wav(args.video, cs, we - cs, wav)
            segs, _ = model.transcribe(str(wav), language="en", word_timestamps=True,
                                       vad_filter=args.vad,
                                       vad_parameters={"min_silence_duration_ms": 300} if args.vad else None)
            words = []
            for seg in segs:
                for w in (seg.words or []):
                    t = (w.word or "").strip()
                    if t:
                        words.append({"type": "word", "text": t,
                                      "start": round(w.start + cs, 3),
                                      "end": round(w.end + cs, 3), "speaker_id": None})
            cf.write_text(json.dumps(words))
            print(f"  window done: {len(words)} words", flush=True)

    # Merge: commit each window's words only from its accurate zone [cs, cs+stride)
    # (the LAST window commits to the end). This tiles the timeline with no overlap.
    allw = []
    for i, cs in enumerate(starts):
        cf = CHUNK_DIR / f"win_{int(round(cs)):06d}.json"
        if not cf.exists():
            continue
        commit_end = args.end if i == len(starts) - 1 else cs + args.stride
        for w in json.loads(cf.read_text()):
            if cs - 1e-6 <= w["start"] < commit_end:
                allw.append(w)
    allw.sort(key=lambda w: w["start"])
    args.out.write_text(json.dumps({"words": allw}, indent=2))
    print(f"\nmerged {len(allw)} words -> {args.out}")


if __name__ == "__main__":
    main()
