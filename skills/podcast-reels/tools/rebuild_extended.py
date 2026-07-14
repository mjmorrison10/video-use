"""Rebuild all clip EDLs as extended clips: the RECALL quote is the HOOK at the
front, extended forward to ~TARGET seconds of content (dead-space removed),
ending on a sentence boundary. Uses the full transcript."""
import sys, json
sys.path.insert(0, "tools")
import locate_quotes as LQ
import edl_build as EB
from pathlib import Path

ED = Path("edit")
CANON = ED / "transcripts" / "Justin-Waller-vs-Therapist.json"
FULL = ED / "transcripts" / "_fulltx.json"
TARGET = 20.0

CLEAN = ["c16", "c17", "c18", "c19", "c20", "c21", "c26", "c27", "c28", "c30", "c31"]
DRIFTED = ["c12", "c13", "c14", "c15", "c22", "c23", "c24", "c25", "c29"]


def meta(cid):
    return [(c, q) for i, c, q in LQ.CLIPS if i == cid][0]


def main():
    words = json.load(open(FULL))["words"]
    json.dump({"words": words}, open(CANON, "w"))   # canonical = full transcript
    # clear old EDLs
    for p in ED.glob("clip_c*.json"):
        p.unlink()
    rows = []
    for cid in CLEAN + DRIFTED:
        c, q = meta(cid)
        r = LQ.locate_global(words, q) if cid in DRIFTED else LQ.locate(words, c, q)
        if not r or r["match_ratio"] < 0.55:
            print(f"{cid}: WEAK/NO MATCH ({r['match_ratio'] if r else 'none'})")
            continue
        start = r["start"]
        end = EB.extend_forward(words, start, r["end"], target=TARGET)
        edl = EB.build(cid, [(start, end, "CLIP")], CANON, out=ED / f"clip_{cid}.json")
        rows.append((cid, edl["total_duration_s"]))
    print("\n=== durations ===")
    for cid, d in sorted(rows):
        print(f"  {cid}: {d}s")


if __name__ == "__main__":
    main()
