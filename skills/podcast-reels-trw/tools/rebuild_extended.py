"""Rebuild all clip EDLs as extended clips: the RECALL quote is the HOOK at the
front, extended forward to ~TARGET seconds of content (dead-space removed),
ending on a sentence boundary. Uses the full transcript."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as P
import locate_quotes as LQ
import edl_build as EB

ED = P.edit_dir()
CANON = P.transcript_path()
TARGET = 20.0

# Clip ids + drift flags come from edit/clips.json (project.load_clips).
DRIFTED = sorted(LQ.DRIFTED)
CLEAN = [cid for (cid, _c, _q) in LQ.CLIPS if cid not in LQ.DRIFTED]


def meta(cid):
    return [(c, q) for i, c, q in LQ.CLIPS if i == cid][0]


def main():
    words = json.load(open(CANON))["words"]
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
