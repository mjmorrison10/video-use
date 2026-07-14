"""Build per-clip EDLs with dead-space removed.

Each clip = a list of top-level spans (hook, moment, ...). Every span is split
into speech sub-ranges, dropping silence gaps > GAP so there's no dead air.
Cuts land on word boundaries (Rule 6). Renders concatenate the sub-ranges with
30ms fades at each edge (Rule 3), so jump-cuts don't pop.
"""
from __future__ import annotations

import json
from pathlib import Path

ED = Path("/home/user/claude-video-editor/edit")
SRC_NAME = "Justin-Waller-vs-Therapist"
SRC = {SRC_NAME: "/home/user/claude-video-editor/Justin-Waller-vs-Therapist.mp4"}

GAP = 0.55        # silence longer than this is dead space -> cut
PAD = 0.08        # keep a little air around kept speech
MIN_LEN = 0.35    # drop sub-ranges shorter than this

# Filler / hesitation words + backchannels to CUT from the clip entirely.
import re as _re
CUT_FILLER = {"um", "umm", "ummm", "uh", "uhh", "uhhh", "er", "err", "ah", "ahh",
              "mm", "mmm", "hmm", "hmmm", "mhm", "mmhmm", "mm-hmm", "uh-huh",
              "uhhuh", "hm", "eh"}


def is_cut_filler(text):
    w = _re.sub(r"[^a-z-]", "", (text or "").lower())
    if w in CUT_FILLER:
        return True
    # collapsed forms like "mm-hmm", "uh-huh" or pure m/h strings
    return len(w) <= 5 and w != "" and set(w) <= set("mh-") and "-" in w


def keep_intervals(words, start, end, gap=GAP, pad=0.05, min_len=MIN_LEN):
    """Kept speech intervals within [start,end], dropping BOTH silence gaps
    (>= gap) AND filler words (um/uh/mm-hmm...). Breaks a run on a filler word
    or a long gap; each run becomes one interval."""
    ws = [w for w in words if w.get("type") == "word" and w.get("start") is not None
          and w.get("end") is not None and w["end"] > start and w["start"] < end]
    runs = []
    cur = []
    for w in ws:
        if is_cut_filler(w["text"]):
            if cur:
                runs.append((cur[0]["start"], cur[-1]["end"])); cur = []
            continue
        if cur and w["start"] - cur[-1]["end"] >= gap:
            runs.append((cur[0]["start"], cur[-1]["end"])); cur = []
        cur.append(w)
    if cur:
        runs.append((cur[0]["start"], cur[-1]["end"]))
    out = []
    for s, e in runs:
        s = round(max(start, s - pad), 3)
        e = round(min(end, e + pad), 3)
        if e - s >= min_len:
            out.append([s, e])
    return out or [[start, end]]


def load_words(transcript: Path):
    return json.loads(transcript.read_text())["words"]


def speech_subranges(words, start, end, gap=GAP, pad=PAD, min_len=MIN_LEN):
    ws = [w for w in words if w.get("type") == "word" and w.get("start") is not None
          and w.get("end") is not None and w["end"] > start and w["start"] < end]
    if not ws:
        return [[start, end]]
    subs = []
    s = max(start, ws[0]["start"] - pad)
    prev = ws[0]["end"]
    for w in ws[1:]:
        if w["start"] - prev > gap:
            subs.append([s, min(end, prev + pad)])
            s = w["start"] - pad
        prev = w["end"]
    subs.append([s, min(end, prev + pad)])
    subs = [[round(max(start, a), 3), round(min(end, b), 3)] for a, b in subs if b - a >= min_len]
    return subs or [[start, end]]


def extend_forward(words, start, quote_end, target=20.0, cap=45.0, cap_span=58.0):
    """Extend a clip FORWARD from its hook (quote) to ~target seconds of
    speech content, always including the full quote and ending on a sentence
    boundary. `target`/`cap` are post-dead-space content seconds."""
    ws = [w for w in words if w.get("type") == "word" and w.get("start") is not None
          and w.get("end") is not None and w["start"] >= start - 0.05
          and w["start"] < start + cap_span]
    kept = 0.0
    prev = None
    end = quote_end
    for w in ws:
        if prev is not None:
            kept += min(w["start"] - prev, GAP)     # count dead-space like removal
        kept += w["end"] - w["start"]
        prev = w["end"]
        end = w["end"]
        tok = w.get("text", "").strip()
        strong = tok[-1:] in ".!?"
        weak = tok[-1:] in ",;:"
        past_quote = w["end"] >= quote_end - 0.05
        if past_quote and kept >= target and strong:
            break
        if past_quote and kept >= target + 8 and weak:   # no sentence end: accept a clause
            break
        if kept >= 44.0:                                  # hard ceiling
            break
    return round(end, 3)


def build(clip_id, spans, transcript, grade="neutral_punch", out=None):
    """spans: list of (start, end, beat). Returns EDL dict and writes it."""
    words = load_words(transcript)
    ranges = []
    for (a, b, beat) in spans:
        for s, e in keep_intervals(words, a, b):     # drops silences AND fillers
            ranges.append({"source": SRC_NAME, "start": s, "end": e, "beat": beat})
    edl = {
        "version": 1, "sources": SRC, "ranges": ranges, "grade": grade,
        "total_duration_s": round(sum(r["end"] - r["start"] for r in ranges), 2),
    }
    out = Path(out) if out else (ED / f"clip_{clip_id}.json")
    out.write_text(json.dumps(edl, indent=2))
    print(f"{clip_id}: {len(ranges)} ranges, {edl['total_duration_s']}s -> {out.name}")
    return edl


if __name__ == "__main__":
    tr = ED / "transcripts" / f"{SRC_NAME}.json"
    # Reference: hook cold-open + clip #18, dead-space removed.
    build("ref", [(3061.36, 3066.14, "HOOK"), (1847.56, 1859.94, "MOMENT")],
          tr, out=ED / "clip_ref.json")
