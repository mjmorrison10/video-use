"""Word-styled ASS captions: serif font, neon-green power words.

Builds an ASS subtitle file on the OUTPUT timeline (Hard Rule 5:
out = word.start - seg_start + seg_offset) from the per-source transcript +
EDL ranges. Chunks ~3 words (break on punctuation); within each chunk, content
("power") words are colored neon green, the rest white. Burned LAST by the
renderer (Hard Rule 1).

Usage:
    python ass_captions.py <edl.json> -o master.ass
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PLAY_W, PLAY_H = 1080, 1920
FONT = "DejaVu Serif"
FONT_SIZE = 60
MARGIN_V = 0               # Alignment 5 = middle-center; MarginV unused
# Neon cyan-blue highlight (#00E0FF), same black outline as white words, no glow.
NEON = r"{\c&H00FFE000&\3c&H00000000&\3a&H00&\bord5\blur0}"
WHITE = r"{\c&H00FFFFFF&\3c&H00000000&\3a&H00&\bord5\blur0}"
# Pop: start at 50% scale, snap to 100% over 25ms (skipped on a clip's 1st line).
POP = r"{\fscx50\fscy50\t(0,25,\fscx100\fscy100)}"
MAX_WORDS = 3
PUNCT_BREAK = set(".,!?;:")
SENT_END = set(".!?")

STOP = set("""a an the and or but so if of to in on at for with as is are was were be been being
it its it's this that these those i you he she we they them me him her us my your his their our
do does did done doing have has had not no yeah so just like was were am pat i'm you're it's that's
there here what when where who how why to too very can could would should will shall may might must
about into over than then out up down off we're we'll we've you'll you've they're they'll i'll i've
don't doesn't didn't isn't aren't wasn't won't can't couldn't wouldn't he's she's there's that'll
gonna wanna gotta kinda sorta really very get got getting one thing""".split())


FILLER = {"mm", "hmm", "mmhmm", "mmhmm", "mhm", "mm-hmm", "uh", "um", "uhh", "umm",
          "er", "ah", "huh", "hm", "mmm", "uhhuh", "uh-huh"}


def is_filler(word: str) -> bool:
    w = re.sub(r"[^a-z-]", "", word.lower())
    return w in FILLER or (len(w) <= 3 and set(w) <= set("mh-"))


def is_power(word: str) -> bool:
    w = re.sub(r"[^a-z']", "", word.lower())
    if len(w) < 3:
        return False
    if w in STOP:
        return False
    return True


def srt_ass_time(seconds: float) -> str:
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{c:02d}"


def words_in_range(transcript, t0, t1):
    out = []
    for w in transcript.get("words", []):
        if w.get("type") != "word":
            continue
        ws, we = w.get("start"), w.get("end")
        if ws is None or we is None:
            continue
        if we <= t0 or ws >= t1:
            continue
        out.append(w)
    return out


def build_events(edl, edit_dir):
    transcripts_dir = edit_dir / "transcripts"
    sources = edl["sources"]
    events = []
    seg_offset = 0.0
    for r in edl["ranges"]:
        src = r["source"]
        seg_start = float(r["start"]); seg_end = float(r["end"])
        seg_dur = seg_end - seg_start
        tr_path = transcripts_dir / f"{src}.json"
        if not tr_path.exists():
            seg_offset += seg_dur
            continue
        transcript = json.loads(tr_path.read_text())
        ws = words_in_range(transcript, seg_start, seg_end)

        # New caption at every sentence end (.!?) or every MAX_WORDS. Commas do
        # NOT force a break, so chunks stay clean and each new sentence starts a
        # fresh caption.
        chunk = []
        for w in ws:
            txt = (w.get("text") or "").strip()
            if not txt:
                continue
            chunk.append(w)
            ends_sentence = txt[-1] in SENT_END
            if ends_sentence or len(chunk) >= MAX_WORDS:
                events.append(_emit(chunk, seg_start, seg_end, seg_offset))
                chunk = []
        if chunk:
            events.append(_emit(chunk, seg_start, seg_end, seg_offset))
        seg_offset += seg_dur
    return [e for e in events if e]


def _emit(chunk, seg_start, seg_end, seg_offset):
    local_start = max(seg_start, chunk[0].get("start", seg_start))
    local_end = min(seg_end, chunk[-1].get("end", seg_end))
    out_start = max(0.0, local_start - seg_start) + seg_offset
    out_end = max(0.0, local_end - seg_start) + seg_offset
    if out_end <= out_start:
        out_end = out_start + 0.4
    parts = []
    for w in chunk:
        t = re.sub(r"\s+", " ", (w.get("text") or "").strip()).rstrip(",.;:!?")
        if not t or is_filler(t):
            continue
        color = NEON if is_power(t) else WHITE
        parts.append(f"{color}{t.upper()}")
    if not parts:
        return None
    text = " ".join(parts) + WHITE
    return (out_start, out_end, text)


def write_ass(events, out_path):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pop,{FONT},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,2,5,60,60,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for i, (a, b, t) in enumerate(sorted(events, key=lambda e: e[0])):
        pop = "" if i == 0 else POP        # skip the pop on the clip's first line
        lines.append(f"Dialogue: 0,{srt_ass_time(a)},{srt_ass_time(b)},Pop,,0,0,0,,{pop}{t}")
    out_path.write_text("\n".join(lines))
    print(f"ASS captions -> {out_path.name} ({len(events)} events)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edl", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    args = ap.parse_args()
    edl = json.loads(args.edl.read_text())
    edit_dir = args.edl.resolve().parent
    events = build_events(edl, edit_dir)
    write_ass(events, args.out)


if __name__ == "__main__":
    main()
