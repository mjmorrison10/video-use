"""Build clip EDLs from the analyst agents' story picks.

Reads edit/picks.json (list of {cid, start_ts, end_ts, ending_line, story}),
snaps start to the nearest word and end to the last word of `ending_line`
(precise), then builds a dead-space-removed EDL per clip.
"""
import sys, json, re
from difflib import SequenceMatcher
from pathlib import Path
sys.path.insert(0, "tools")
import edl_build as EB

ED = Path("edit")
FULL = ED / "transcripts" / "Justin-Waller-vs-Therapist.json"


def tok(s):
    return re.sub(r"[^a-z0-9']", " ", s.lower()).split()


def snap_start(words, ts):
    cand = [w for w in words if w.get("type") == "word" and w.get("start") is not None]
    return min(cand, key=lambda w: abs(w["start"] - ts))["start"]


def snap_end(words, end_ts, ending_line):
    win = [w for w in words if w.get("type") == "word" and w.get("start") is not None
           and end_ts - 30 <= w["start"] <= end_ts + 12]
    tw = [tok(w["text"])[0] if tok(w["text"]) else "" for w in win]
    et = tok(ending_line or "")
    if et and win:
        sm = SequenceMatcher(None, tw, et, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
        if blocks and sum(b.size for b in blocks) >= max(2, 0.5 * len(et)):
            a_end = blocks[-1].a + blocks[-1].size
            return win[min(a_end, len(win)) - 1]["end"]
    cand = [w for w in words if w.get("type") == "word" and w.get("end") is not None]
    return min(cand, key=lambda w: abs(w["end"] - end_ts))["end"]


def main():
    words = json.load(open(FULL))["words"]
    picks = json.load(open(ED / "picks.json"))
    for p in ED.glob("clip_c*.json"):
        p.unlink()
    rows = []
    for p in picks:
        cid = p["cid"]
        s = snap_start(words, float(p["start_ts"])) - 0.05
        e = snap_end(words, float(p["end_ts"]), p.get("ending_line", "")) + 0.10
        if e - s < 3.0:
            print(f"{cid}: too short after snap ({e-s:.1f}s), skipping"); continue
        edl = EB.build(cid, [(round(max(0.0, s), 3), round(e, 3), "CLIP")], FULL,
                       out=ED / f"clip_{cid}.json")
        rows.append((cid, edl["total_duration_s"], p.get("story", "")))
    print("\n=== clips ===")
    for cid, d, story in sorted(rows):
        print(f"  {cid}: {d}s — {story[:70]}")


if __name__ == "__main__":
    main()
