"""Windowed local transcription with faster-whisper.

Transcribes only the time windows around a set of center timestamps (the
clip moments), then merges them into ONE transcript JSON in the exact shape
the video-use pipeline expects:

    {"words": [{"type": "word", "text": "...", "start": s, "end": e,
                "speaker_id": null}, ...]}

This is a drop-in replacement for helpers/transcribe.py (ElevenLabs Scribe) —
pack_transcripts.py and render.py's SRT builder read the same `words` array.
No diarization (Whisper doesn't do it); speaker_id is null.

Usage:
    python transcribe_whisper_windows.py <video> <out.json> \
        --model small.en --pad 35 [--full]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Center timestamps (seconds) for each clip moment + the hook.
# Derived from the user's HH:MM:SS clip list.
CENTERS = {
    "hook_30": 51 * 60 + 0,      # 0:51:00
    "c12": 87 * 60 + 58,         # 1:27:58
    "c13": 76 * 60 + 39,         # 1:16:39
    "c14": 73 * 60 + 26,         # 1:13:26
    "c15": 72 * 60 + 32,         # 1:12:32
    "c16": 50 * 60 + 40,         # 0:50:40
    "c17": 47 * 60 + 18,         # 0:47:18
    "c18": 30 * 60 + 47,         # 0:30:47
    "c19": 23 * 60 + 39,         # 0:23:39
    "c20": 15 * 60 + 57,         # 0:15:57
    "c21": 1 * 60 + 31,          # 0:01:31
    "c22": 89 * 60 + 46,         # 1:29:46 (shares ts with c23)
    "c23": 89 * 60 + 46,         # 1:29:46
    "c24": 71 * 60 + 57,         # 1:11:57
    "c25": 70 * 60 + 23,         # 1:10:23
    "c26": 53 * 60 + 46,         # 0:53:46
    "c27": 43 * 60 + 38,         # 0:43:38
    "c28": 42 * 60 + 54,         # 0:42:54
    "c29": 69 * 60 + 56,         # 1:09:56
}


def merge_windows(centers, pad, merge_gap=5.0):
    """Return merged [start, end] intervals covering every center ± pad."""
    ivals = sorted((max(0.0, c - pad), c + pad) for c in centers)
    merged = []
    for s, e in ivals:
        if merged and s <= merged[-1][1] + merge_gap:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def extract_wav(video, start, end, dest):
    dur = end - start
    cmd = [
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(video),
        "-t", f"{dur:.3f}", "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--pad", type=float, default=35.0)
    ap.add_argument("--full", action="store_true", help="Transcribe the entire file instead of windows")
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    if args.full:
        windows = [[0.0, None]]
    else:
        windows = merge_windows(CENTERS.values(), args.pad)

    print(f"loading model {args.model} (cpu/int8)...", flush=True)
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=0)

    all_words = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (start, end) in enumerate(windows):
            if end is None:
                # full-file: extract everything
                wav = Path(tmp) / f"w{i}.wav"
                cmd = ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1",
                       "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                offset = 0.0
            else:
                wav = Path(tmp) / f"w{i}.wav"
                extract_wav(video, start, end, wav)
                offset = start
            print(f"  window {i+1}/{len(windows)}  [{start:.0f}s..{'end' if end is None else f'{end:.0f}s'}]", flush=True)
            segments, _ = model.transcribe(
                str(wav), language="en", word_timestamps=True,
                vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
            )
            for seg in segments:
                if not seg.words:
                    continue
                for w in seg.words:
                    txt = (w.word or "").strip()
                    if not txt:
                        continue
                    all_words.append({
                        "type": "word",
                        "text": txt,
                        "start": round(w.start + offset, 3),
                        "end": round(w.end + offset, 3),
                        "speaker_id": None,
                    })

    all_words.sort(key=lambda w: w["start"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"words": all_words}, indent=2))
    print(f"\nsaved {len(all_words)} words -> {args.out}")


if __name__ == "__main__":
    main()
