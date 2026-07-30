#!/usr/bin/env python3
"""Turn a hand-edited SRT into Remotion captionPages, verbatim.

When a human fixes captions (in Premiere, or by editing the SRT directly) their
phrasing IS the edit: pages break where a person would breathe, currency stays
numeric ("$160,000", not "$160" + ",000"), and connective words are kept. Feeding
that back through the auto-grouper in build_props.py would undo all of it, so
this path bypasses grouping entirely — one cue in, one caption page out.

Token contract matches CaptionPage.tsx, which renders each token with
`whiteSpace: "pre"` and supplies no separators of its own: every token after the
first carries a leading space.

Usage: srt_to_pages.py FIXED.srt [-o pages.json] [--check]
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from caption_text import strip_punct, tokens_for_page  # noqa: E402

CUE = re.compile(
    r"(\d+)\s*\n"
    r"(\d\d):(\d\d):(\d\d)[,.](\d{3})\s*-->\s*(\d\d):(\d\d):(\d\d)[,.](\d{3})\s*\n"
    r"(.*?)(?=\n\s*\n|\Z)",
    re.S,
)


def _ms(h, m, s, ms):
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def parse(srt_text):
    cues = []
    for mt in CUE.finditer(srt_text):
        g = mt.groups()
        text = " ".join(g[9].split())          # collapse newlines/runs inside a cue
        if not text:
            continue
        cues.append({"startMs": _ms(*g[1:5]), "endMs": _ms(*g[5:9]), "text": text})
    return cues


def to_pages(cues):
    """A hand-edited SRT is caption TRUTH for phrasing and timing, but it still
    goes through the house punctuation rule — an editor writing "lecture room,"
    means the phrasing, not the comma."""
    pages = []
    for c in cues:
        pages.append({
            "startMs": c["startMs"],
            "endMs": c["endMs"],
            "tokens": tokens_for_page(c["text"].split()),
        })
    return pages


def _ts(ms):
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(pages):
    """Round-trip back to SRT so the ingest can be proven lossless."""
    return "\n".join(
        f"{i}\n{_ts(p['startMs'])} --> {_ts(p['endMs'])}\n"
        f"{''.join(t['text'] for t in p['tokens']).strip()}\n"
        for i, p in enumerate(pages, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt"); ap.add_argument("-o", "--out")
    ap.add_argument("--check", action="store_true",
                    help="verify the pages round-trip back to the source SRT")
    a = ap.parse_args()

    src = Path(a.srt).read_text(encoding="utf-8-sig")
    cues = parse(src)
    if not cues:
        sys.exit(f"no cues parsed from {a.srt}")
    pages = to_pages(cues)

    if a.check:
        want = parse(src)
        got = parse(to_srt(pages))
        # punctuation is intentionally dropped, so compare against the stripped source
        norm = lambda t: " ".join(x for x in (strip_punct(w) for w in t.split()) if x)
        bad = [(w, g) for w, g in zip(want, got)
               if w["startMs"] != g["startMs"] or w["endMs"] != g["endMs"]
               or norm(w["text"]) != g["text"]]
        assert len(want) == len(got), f"cue count {len(want)} -> {len(got)}"
        assert not bad, f"{len(bad)} cues changed, first: {bad[0]}"
        print(f"[srt] round-trip OK — {len(pages)} cues, timing identical, text punctuation-stripped")

    words = sum(len(p["tokens"]) for p in pages)
    span = pages[-1]["endMs"] / 1000
    if a.out:
        Path(a.out).write_text(json.dumps(pages, ensure_ascii=False, indent=1))
    else:
        print(json.dumps(pages, ensure_ascii=False, indent=1))
    print(f"[srt] {len(pages)} pages, {words} words, ends {span:.2f}s"
          + (f" -> {a.out}" if a.out else ""), file=sys.stderr)


if __name__ == "__main__":
    main()
