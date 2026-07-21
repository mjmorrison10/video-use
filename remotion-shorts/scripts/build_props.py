#!/usr/bin/env python3
"""Turn an editorial cut-spec + word transcript into a Remotion job JSON.

The cut-spec lists chosen source spans (word-boundary in/out seconds). This script:
  - computes each span's OUTPUT offset by running sum (like video-use render.py),
  - collects the transcript words inside each span and re-times them to the OUTPUT
    timeline,
  - applies caption word replacements (e.g. censor "hoe" -> "wife"),
  - groups words into caption PAGES of 2-3 words that restart on every sentence
    (or uses a manual `captionGroups` list of word-counts for exact control),
  - emits props matching src/Short/schema.ts (shortSchema).

Cut-spec extras:
  "captionReplace": {"hoe": "wife"}      # cleaned-word -> replacement (case-insensitive)
  "captionGroups":  [3,2,2,...]          # optional: exact words-per-page, in order
  segment "mute": true                    # drop that segment's audio (censor)

Usage:
  python build_props.py CUTSPEC.json TRANSCRIPT.json -o JOB.json [--dump-words]
"""
import argparse
import json
import re
import sys
from pathlib import Path

SENT_END = (".", "?", "!")

# House style shared by every clip. A cut-spec's "style" block overrides these
# per-clip (e.g. powerWords, hook color). Keeps all clips visually consistent.
DEFAULT_STYLE = {
    "highlightColor": "#FFD60A",
    "accentColor": "#FFD60A",   # yellow power words + hook
    "textColor": "white",
    "strokeColor": "black",
    "fontSize": 58,             # Big Shoulders is condensed; 58 restores punch
    "captionPosition": "center",
    "uppercase": True,
    "powerWords": [],
}

# Punctuation stripped from caption DISPLAY text (grouping still uses the
# originals to detect sentence ends). Apostrophes and % are kept.
_PUNCT_RE = re.compile(r"[.,!?;:\"“”‘’—…()\[\]]")


def strip_punct(text: str) -> str:
    return _PUNCT_RE.sub("", text)


def load(p):
    return json.loads(Path(p).read_text())


def clean(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower()).strip()


def apply_replace(text: str, repl: dict) -> str:
    """Replace the core word while preserving leading space + trailing punctuation."""
    key = clean(text)
    if key not in repl:
        return text
    m = re.match(r"^(\s*)(.*?)([^A-Za-z0-9]*)$", text)
    lead, _core, trail = m.group(1), m.group(2), m.group(3)
    return f"{lead}{repl[key]}{trail}"


def ends_sentence(text: str) -> bool:
    return text.strip().endswith(SENT_END)


def group_auto(words):
    """2-3 words per page; flush on sentence-ending punctuation. Bias to 2, allow a
    3rd only when it is a short (<=3 char) connector that does not end a sentence."""
    pages, cur = [], []
    i, n = 0, len(words)
    while i < n:
        cur.append(words[i])
        t = words[i]["text"]
        if ends_sentence(t):
            pages.append(cur); cur = []
        elif len(cur) >= 3:
            pages.append(cur); cur = []
        elif len(cur) == 2:
            nxt = words[i + 1] if i + 1 < n else None
            take3 = (
                nxt is not None
                and len(clean(nxt["text"])) <= 3
                and not ends_sentence(nxt["text"])
            )
            if not take3:
                pages.append(cur); cur = []
        i += 1
    if cur:
        pages.append(cur)
    return pages


def group_manual(words, counts):
    pages, idx = [], 0
    for c in counts:
        chunk = words[idx: idx + c]
        if chunk:
            pages.append(chunk)
        idx += c
    if idx < len(words):  # leftover -> auto-chunk the tail
        pages.extend(group_auto(words[idx:]))
    return pages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cutspec")
    ap.add_argument("transcript")
    ap.add_argument("-o", "--out", default="job.json")
    ap.add_argument("--focus", default=None,
                    help="face-tracking focus JSON (from detect_faces.py). If omitted, "
                         "auto-loads <cutspec>.focus.json when present.")
    ap.add_argument("--dump-words", action="store_true",
                    help="print the assembled output word stream (to author captionGroups)")
    args = ap.parse_args()

    spec = load(args.cutspec)
    tr = load(args.transcript)

    # Optional face-tracking pan track: one keyframe list per segment (by index).
    focus_path = args.focus
    if focus_path is None:
        guess = Path(str(args.cutspec).replace(".cutspec.json", ".focus.json"))
        if guess.exists():
            focus_path = str(guess)
    focus_segments = load(focus_path)["segments"] if focus_path else []
    repl = {clean(k): v for k, v in spec.get("captionReplace", {}).items()}
    words = [w for w in tr.get("words", []) if w.get("type", "word") == "word"
             and w.get("start") is not None and w.get("end") is not None]

    fps = spec.get("fps", 30)
    ranges, flat = [], []
    offset = 0.0
    for si, seg in enumerate(spec["segments"]):
        a, b = float(seg["inSec"]), float(seg["outSec"])
        dur = b - a
        if dur <= 0:
            print(f"[warn] skipping non-positive span {seg}", file=sys.stderr)
            continue
        ranges.append({
            "inSec": round(a, 3), "outSec": round(b, 3),
            "offsetSec": round(offset, 3),
            "framing": seg.get("framing", "cover"),
            "mute": bool(seg.get("mute", False)),
            "beat": seg.get("beat"),
            "focus": focus_segments[si] if si < len(focus_segments) else [],
            "zoom": float(seg.get("zoom", 1)),
        })
        last_we = a
        for w in words:
            ws, we = float(w["start"]), float(w["end"])
            if ws < a or ws >= b:
                continue
            out_start = (ws - a) + offset
            out_end = (min(we, b) - a) + offset
            if out_end <= out_start:
                out_end = out_start + 0.12
            flat.append({
                "text": apply_replace(w["text"], repl),
                "startMs": round(out_start * 1000),
                "endMs": round(out_end * 1000),
                "seg": si,  # which source segment this word came from
            })
            last_we = max(last_we, we)
        # CLIPPED-WORD GUARD: if a transcript word begins right at/after outSec while
        # speech was still contiguous, the segment almost certainly cut a word in half
        # (outSec was set to that word's START instead of its END). Warn loudly — this
        # is the #1 recurring authoring mistake.
        nxt = next((w for w in words if float(w["start"]) >= b), None)
        if nxt is not None and float(nxt["start"]) - last_we < 0.08:
            print(f"[warn] seg{si} outSec={b:.2f} may CLIP the word "
                  f"{nxt['text']!r} (starts {float(nxt['start']):.2f}). "
                  f"Extend outSec past its end.", file=sys.stderr)
        offset += dur

    # Merge number continuations into the previous caption token. Whisper emits
    # thousands/decimals as separate tokens with NO leading space (e.g. "£45"
    # then ",000"; "1" then ".1"). Every genuine new word carries a leading
    # space, so a token that lacks one is a continuation of the prior word --
    # glue it on so a number is one caption unit and can't split across a page.
    merged = []
    for w in flat:
        if (merged and w["text"] and not w["text"][:1].isspace()
                and w["seg"] == merged[-1]["seg"]):
            merged[-1]["text"] += w["text"]
            merged[-1]["endMs"] = w["endMs"]
        else:
            merged.append(w)
    flat = merged

    if args.dump_words:
        for i, w in enumerate(flat):
            print(f"{i:3d} {w['text']!r}")
        print(f"[dump] {len(flat)} words, total {offset:.2f}s")
        return 0

    groups = spec.get("captionGroups")
    if groups:
        pages_words = group_manual(flat, groups)
    else:
        # Group within each source segment separately so a caption page never
        # spans a hard cut (a new segment = a new sentence/thought on screen).
        pages_words = []
        run = []
        for w in flat:
            if run and w["seg"] != run[-1]["seg"]:
                pages_words.extend(group_auto(run))
                run = []
            run.append(w)
        if run:
            pages_words.extend(group_auto(run))
    strip = spec.get("stripPunctuation", True)
    caption_pages = []
    for grp in pages_words:
        caption_pages.append({
            "startMs": grp[0]["startMs"],
            "endMs": grp[-1]["endMs"],
            "tokens": [{"text": strip_punct(w["text"]) if strip else w["text"]}
                       for w in grp],
        })

    style = {**DEFAULT_STYLE, **spec.get("style", {})}
    job = {
        "videoSrc": spec.get("videoSrc", "proxy.mp4"),
        "fps": fps,
        "ranges": ranges,
        "captionPages": caption_pages,
        "music": spec.get("music"),
        "style": style,
        "hook": spec.get("hook"),
    }
    Path(args.out).write_text(json.dumps(job, ensure_ascii=False, indent=1))
    print(f"[props] {len(ranges)} spans, {len(flat)} words, "
          f"{len(caption_pages)} caption pages, total {offset:.2f}s -> {args.out}")
    if not (15 <= offset <= 45):
        print(f"[warn] duration {offset:.1f}s outside 15-45s target", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
