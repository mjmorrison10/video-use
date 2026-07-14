"""Build per-clip transcript context files for the clip-story analyst agents.

Each file: the HOOK line (must open the clip) + a timestamped, phrase-level
window of what follows, so an agent can choose the exact END point where the
hook's point lands (before any tangent) and the clip becomes a complete story.
"""
import sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as P
import locate_quotes as LQ

ED = P.edit_dir()
FULL = P.transcript_path()
CTX = P.context_dir()
CTX.mkdir(parents=True, exist_ok=True)

# Clip ids + drift flags come from edit/clips.json (project.load_clips).
DRIFTED = sorted(LQ.DRIFTED)
CLEAN = [cid for (cid, _c, _q) in LQ.CLIPS if cid not in LQ.DRIFTED]
PRE, POST = 8.0, 170.0


def meta(cid):
    return [(c, q) for i, c, q in LQ.CLIPS if i == cid][0]


def phrases(words, t0, t1):
    """Group words in [t0,t1] into phrase lines, breaking on sentence punctuation
    or gaps >= 0.6s. Each line prefixed with its absolute start second."""
    ws = [w for w in words if w.get("type") == "word" and w.get("start") is not None
          and w["start"] >= t0 and w["start"] <= t1]
    lines, cur, start, prev = [], [], None, None
    for w in ws:
        if start is None:
            start = w["start"]
        if prev is not None and w["start"] - prev >= 0.6 and cur:
            lines.append((start, " ".join(cur))); cur, start = [], w["start"]
        cur.append(w["text"].strip())
        prev = w["end"]
        if w["text"].strip()[-1:] in ".!?" and len(cur) >= 4:
            lines.append((start, " ".join(cur))); cur, start = [], None
    if cur:
        lines.append((start or t0, " ".join(cur)))
    return lines


def main():
    words = json.load(open(FULL))["words"]
    manifest = {}
    for cid in CLEAN + DRIFTED:
        c, q = meta(cid)
        r = LQ.locate_global(words, q) if cid in DRIFTED else LQ.locate(words, c, q)
        if not r:
            print(f"{cid}: NO MATCH"); continue
        hs, he = r["start"], r["end"]
        manifest[cid] = {"hook_start": hs, "hook_end": he, "quote": q}
        lines = phrases(words, hs - PRE, hs + POST)
        body = "\n".join(f"[{s:.2f}] {t}" for s, t in lines)
        txt = (f"CLIP {cid}\n"
               f"HOOK (the clip MUST open on this line): \"{q}\"\n"
               f"The hook begins around {hs:.2f}s in the timeline below.\n"
               f"Each line is prefixed with its absolute start-second [SSSS.ss].\n\n"
               f"TRANSCRIPT WINDOW:\n{body}\n")
        (CTX / f"{cid}.txt").write_text(txt)
    (CTX / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} context files -> {CTX}")


if __name__ == "__main__":
    main()
