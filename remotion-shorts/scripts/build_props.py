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
    "highlightColor": "#00E5FF",
    "accentColor": "#00E5FF",   # yellow power words + hook
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


_NUM_TAIL = ("thousand", "million", "grand", "000", "500")


def glued(prev_text, nxt) -> bool:
    """True when a page must NOT break between these two words. Transcribers split
    currency into two tokens ('$10' + ',000'/'thousand'); breaking there puts a
    bare '$10' on one page and 'THOUSAND' on the next, which reads terribly on the
    money beat."""
    if nxt is None:
        return False
    p, n = clean(prev_text), clean(nxt["text"])
    return bool(p) and p[-1].isdigit() and (n in _NUM_TAIL or (n.isdigit() and len(n) <= 3))


def group_auto(words):
    """2-3 words per page; flush on sentence-ending punctuation. Bias to 2, allow a
    3rd only when it is a short (<=3 char) connector that does not end a sentence.
    A glued currency pair may push a page to 4 rather than split the number."""
    pages, cur = [], []
    i, n = 0, len(words)
    while i < n:
        cur.append(words[i])
        t = words[i]["text"]
        nxt = words[i + 1] if i + 1 < n else None
        if ends_sentence(t):
            pages.append(cur); cur = []
        elif glued(t, nxt) and len(cur) < 4:
            pass  # keep the number and its magnitude on the same page
        elif len(cur) >= 3:
            pages.append(cur); cur = []
        elif len(cur) == 2:
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
    ap.add_argument("--dump-words", action="store_true",
                    help="print the assembled output word stream (to author captionGroups)")
    args = ap.parse_args()

    spec = load(args.cutspec)
    tr = load(args.transcript)
    repl = {clean(k): v for k, v in spec.get("captionReplace", {}).items()}
    words = [w for w in tr.get("words", []) if w.get("type", "word") == "word"
             and w.get("start") is not None and w.get("end") is not None]

    fps = spec.get("fps", 30)
    ranges, flat = [], []
    offset = 0.0
    for seg in spec["segments"]:
        a, b = float(seg["inSec"]), float(seg["outSec"])
        dur = b - a
        if dur <= 0:
            print(f"[warn] skipping non-positive span {seg}", file=sys.stderr)
            continue
        ranges.append({
            "inSec": round(a, 3), "outSec": round(b, 3),
            "offsetSec": round(offset, 3),
            "framing": seg.get("framing", "cover"),
            "cropX": seg.get("cropX", 0.5),
            "cropXEnd": seg.get("cropXEnd"),
            "cropPanSec": seg.get("cropPanSec"),
            "mute": bool(seg.get("mute", False)),
            "beat": seg.get("beat"),
        })
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
            })
        offset += dur

    if args.dump_words:
        for i, w in enumerate(flat):
            print(f"{i:3d} {w['text']!r}")
        print(f"[dump] {len(flat)} words, total {offset:.2f}s")
        return 0

    groups = spec.get("captionGroups")
    pages_words = group_manual(flat, groups) if groups else group_auto(flat)
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
        # pass through optional overlays authored in the cut-spec
        "broll": spec.get("broll", []),
        "zooms": spec.get("zooms", []),
        "zoomSteps": spec.get("zoomSteps", []),
        "cta": spec.get("cta"),
    }
    Path(args.out).write_text(json.dumps(job, ensure_ascii=False, indent=1))
    print(f"[props] {len(ranges)} spans, {len(flat)} words, "
          f"{len(caption_pages)} caption pages, total {offset:.2f}s -> {args.out}")
    if not (15 <= offset <= 45):
        print(f"[warn] duration {offset:.1f}s outside 15-45s target", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
