#!/usr/bin/env python3
"""Snap a cut-spec's segment boundaries into the SILENT dead-space around words.

The problem: Whisper/ElevenLabs word timestamps are not frame-accurate, and an
editor often sets inSec/outSec to a word's labelled start/end. A word's real
attack can begin a few ms *before* its labelled start, and its tail can ring on
*after* its labelled end -- so the cut lands inside the word and clips it. This
is exactly the thing you fix by hand in Premiere: place every cut inside the
silent gap (dead space) BETWEEN words, never inside a word.

This script does it from the audio waveform:
  - reads the project audio (16 kHz mono PCM WAV) and builds a short-time energy
    envelope,
  - for each segment, finds the transcript words that fall inside it (same rule
    build_props.py uses: word.start in [inSec, outSec)),
  - detects the ACTUAL audio onset of the first kept word and the ACTUAL audio
    offset of the last kept word (energy crossing the silence threshold near the
    labelled times),
  - moves inSec back to sit in the dead-space just before that onset (with a
    small pre-roll) and outSec forward to sit in the dead-space just after that
    offset (with a small post-roll),
  - clamps so it never crosses into the neighbouring word (never adds/drops a
    word) -- the SAME words survive, just with clean boundaries.

Output is a new cut-spec (default <cutspec>.snapped.cutspec.json, or --inplace),
plus a per-boundary report of old -> new and whether each landed in silence.

Usage:
  uv run --with numpy python scripts/snap_cuts.py \
      jobs/heartfat_clip1.cutspec.json \
      /home/user/videos/heartfat/edit/transcript.json \
      /home/user/videos/heartfat/audio.wav [--inplace] [--report]
"""
import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np

HOP = 0.005        # 5 ms energy hop
WIN = 0.025        # 25 ms energy window
PREROLL = 0.06     # keep >=60 ms of dead-space before the first word's onset
POSTROLL = 0.08    # keep >=80 ms of dead-space after the last word's tail
EDGE_MARGIN = 0.03 # never plant a cut within 30 ms of a neighbouring word
# How far around a labelled time we hunt for the true onset/offset.
SEARCH = 0.25


def load_audio(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def energy_envelope(a, sr):
    """RMS energy per HOP-frame. Returns (env, hop_sec)."""
    hop = max(1, int(round(HOP * sr)))
    win = max(hop, int(round(WIN * sr)))
    # pad so frame i is centred on i*hop
    pad = win // 2
    ap = np.pad(a, (pad, pad), mode="constant")
    nfr = 1 + (len(a) - 1) // hop
    env = np.empty(nfr, dtype=np.float32)
    sq = ap * ap
    csum = np.concatenate([[0.0], np.cumsum(sq)])
    for i in range(nfr):
        s = i * hop
        e = s + win
        env[i] = np.sqrt(max(0.0, (csum[e] - csum[s]) / win))
    return env, hop / sr


def make_is_speech(env, hop_sec):
    """Global silence threshold from robust floor/peak percentiles."""
    floor = float(np.percentile(env, 20))
    peak = float(np.percentile(env, 95))
    thr = floor + 0.15 * (peak - floor)
    thr = max(thr, 1e-4)

    def frame(t):
        return int(round(t / hop_sec))

    def speech_at(t):
        i = frame(t)
        if i < 0 or i >= len(env):
            return False
        return env[i] > thr

    return speech_at, frame, thr


MIN_SIL = 0.05  # a gap must be >=50 ms of silence to count as real dead-space


def onset_gap(env, hop_sec, frame, thr, t_word):
    """Find the ACTUAL onset of the word at t_word and the silence gap before it.
    Scan BACKWARD from t_word: skip the word's own speech, then require a real
    silence run (>=MIN_SIL). Returns (onset, gap_start) or None if the word is
    butted up against the previous word (continuous speech -> no dead-space, so
    the boundary must not move earlier)."""
    hold = max(1, int(round(MIN_SIL / hop_sec)))
    iw = frame(t_word)
    i0 = max(0, frame(t_word - SEARCH))
    # step back over any speech that is the word's own early attack (a few frames
    # around the label may already be speech if the word starts before its label)
    i = min(iw, len(env) - 1)
    # walk back while speech, looking for the first silence frame
    onset_frame = i
    while i >= i0:
        if env[i] <= thr:
            # candidate silence at i; confirm it's a real gap (>=MIN_SIL silent)
            j = i
            while j >= i0 and env[j] <= thr:
                j -= 1
            if (i - j) >= hold:
                return onset_frame * hop_sec, (j + 1) * hop_sec
            # too short a dip; keep it as part of speech and continue back
            onset_frame = j
            i = j
        else:
            onset_frame = i
            i -= 1
    return None


def offset_gap(env, hop_sec, frame, thr, t_word, dur):
    """Find the ACTUAL offset (tail end) of the word ending at t_word and the
    silence gap after it. Scan FORWARD, require a real silence run. Returns
    (offset, gap_end) or None if speech runs straight into the next word."""
    hold = max(1, int(round(MIN_SIL / hop_sec)))
    iw = frame(t_word)
    i1 = min(len(env) - 1, frame(t_word + SEARCH))
    i = max(0, iw)
    offset_frame = i
    while i <= i1:
        if env[i] <= thr:
            j = i
            while j <= i1 and env[j] <= thr:
                j += 1
            if (j - i) >= hold:
                return offset_frame * hop_sec, j * hop_sec
            offset_frame = j
            i = j
        else:
            offset_frame = i + 1
            i += 1
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cutspec")
    ap.add_argument("transcript")
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--inplace", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--preroll", type=float, default=PREROLL)
    ap.add_argument("--postroll", type=float, default=POSTROLL)
    args = ap.parse_args()

    spec = json.loads(Path(args.cutspec).read_text())
    tr = json.loads(Path(args.transcript).read_text())
    words = [w for w in tr.get("words", [])
             if w.get("type", "word") == "word"
             and w.get("start") is not None and w.get("end") is not None]
    words.sort(key=lambda w: float(w["start"]))
    starts = [float(w["start"]) for w in words]
    ends = [float(w["end"]) for w in words]

    a, sr = load_audio(args.audio)
    env, hop_sec = energy_envelope(a, sr)
    speech_at, frame, thr = make_is_speech(env, hop_sec)
    dur_audio = len(a) / sr

    import bisect
    report = []
    total_moved = 0.0
    for si, seg in enumerate(spec["segments"]):
        a_in, b_out = float(seg["inSec"]), float(seg["outSec"])
        # kept words: start in [inSec, outSec)  (matches build_props.py)
        kept = [i for i in range(len(words)) if a_in <= starts[i] < b_out]
        if not kept:
            report.append((si, a_in, b_out, a_in, b_out, "no-words"))
            continue
        first_i, last_i = kept[0], kept[-1]

        # neighbours (never cross these -> never add/drop a word)
        prev_end = ends[first_i - 1] if first_i > 0 else 0.0
        next_start = starts[last_i + 1] if last_i + 1 < len(words) else dur_audio

        # ---- START boundary ----
        # Only move earlier if there is a REAL silent gap before the first word.
        # If the word butts against the previous word (deliberate mid-sentence
        # cut), leave the boundary at the labelled start -- moving it would drag
        # in the previous word's tail.
        og = onset_gap(env, hop_sec, frame, thr, starts[first_i])
        if og is None:
            new_in = a_in                              # no dead-space: don't move
            in_flag = "no-gap(keep)"
        else:
            onset, gap_start = og
            # sit preroll before the onset, but stay inside the silent gap and
            # never cross into the previous word.
            floor_in = max(gap_start, prev_end + EDGE_MARGIN)
            new_in = max(floor_in, onset - args.preroll)
            new_in = min(new_in, starts[first_i])      # never clip the attack
            in_flag = "sil" if not speech_at(new_in) else "SPEECH?"

        # ---- END boundary ----
        # Only move later if there is a REAL silent gap after the last word.
        fg = offset_gap(env, hop_sec, frame, thr, ends[last_i], dur_audio)
        if fg is None:
            new_out = b_out                            # no dead-space: don't move
            out_flag = "no-gap(keep)"
        else:
            offset, gap_end = fg
            ceil_out = min(gap_end, next_start - EDGE_MARGIN)
            new_out = min(ceil_out, offset + args.postroll)
            new_out = max(new_out, ends[last_i])       # never clip the tail
            out_flag = "sil" if not speech_at(new_out) else "SPEECH?"

        new_in = max(0.0, new_in)
        new_out = min(dur_audio, new_out)

        total_moved += abs(new_in - a_in) + abs(new_out - b_out)
        seg["inSec"] = round(new_in, 3)
        seg["outSec"] = round(new_out, 3)
        report.append((si, a_in, b_out, new_in, new_out,
                       f"in={in_flag} out={out_flag}"))

    out_path = args.cutspec if args.inplace else (
        args.out or str(Path(args.cutspec)).replace(".cutspec.json", ".snapped.cutspec.json"))
    Path(out_path).write_text(json.dumps(spec, ensure_ascii=False, indent=2))

    if args.report or True:
        print(f"[snap] {Path(args.cutspec).name}  thr={thr:.4f}  total boundary move={total_moved*1000:.0f}ms")
        for si, oi, ob, ni, nb, flag in report:
            din, dout = (ni - oi) * 1000, (nb - ob) * 1000
            print(f"  seg{si}: in {oi:.2f}->{ni:.2f} ({din:+.0f}ms)  "
                  f"out {ob:.2f}->{nb:.2f} ({dout:+.0f}ms)  [{flag}]")
    print(f"[snap] wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
