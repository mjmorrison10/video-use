"""Batch-build and render clips.

Each clip = hook cold-open + the moment (dead-space removed), except #30 which
is standalone from its fuller context. Locates each moment by fuzzy-matching the
quote against the transcript, builds the EDL, renders vertical (auto-crop +
neon-blue centered captions), and writes edit/out/clip_<id>.mp4.

Usage:
    python batch.py <transcript.json> <clip_ids comma-sep>   e.g. c16,c17,c18
    python batch.py <transcript.json> clean
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import project as P
import locate_quotes as LQ
import edl_build as EB

ED = P.edit_dir()
OUT = P.out_dir()

# Clip buckets come from edit/clips.json (via project.load_clips): every clip is
# "clean" unless flagged drifted (locate globally). No hardcoded episode list.
DRIFTED = sorted(LQ.DRIFTED)
CLEAN = [cid for (cid, _c, _q) in LQ.CLIPS if cid not in LQ.DRIFTED]

MAX_MOMENT = 55.0   # guard against fuzzy over-extension


def clip_meta(cid):
    for i, c, q in LQ.CLIPS:
        if i == cid:
            return c, q
    raise KeyError(cid)


def render(edl_path, out_path):
    cmd = [sys.executable, str(HERE / "render_crop.py"), str(edl_path), "-o", str(out_path)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"    RENDER FAIL: {p.stderr[-400:]}")
        return False
    return True


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nokey=1:noprint_wrappers=1", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return -1.0


def main():
    transcript = Path(sys.argv[1])
    sel = sys.argv[2] if len(sys.argv) > 2 else "clean"
    ids = CLEAN if sel == "clean" else (DRIFTED if sel == "drifted" else sel.split(","))
    use_global = sel == "drifted"
    words = json.loads(transcript.read_text())["words"]
    OUT.mkdir(parents=True, exist_ok=True)

    def find(center, quote):
        return LQ.locate_global(words, quote) if use_global else LQ.locate(words, center, quote)

    results = []
    for cid in ids:
        print(f"\n=== {cid} ===", flush=True)
        try:
            center, quote = clip_meta(cid)
            r = find(center, quote)
            if not r or r["match_ratio"] < 0.55:
                print(f"    SKIP: weak match ({r['match_ratio'] if r else 'none'})")
                results.append((cid, "skip-weak-match", -1)); continue
            if r["dur"] > MAX_MOMENT:
                print(f"    WARN: long moment {r['dur']}s, clamping tail")
                r["end"] = r["start"] + MAX_MOMENT
            spans = [(r["start"], r["end"], "MOMENT")]   # standalone: just the moment
            edl_path = ED / f"clip_{cid}.json"
            edl = EB.build(cid, spans, transcript, out=edl_path)
            out_path = OUT / f"clip_{cid}.mp4"
            if render(edl_path, out_path):
                d = duration(out_path)
                print(f"    OK {d:.1f}s -> {out_path.name}")
                results.append((cid, "ok", d))
            else:
                results.append((cid, "render-fail", -1))
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append((cid, f"error:{e}", -1))

    print("\n===== SUMMARY =====")
    for cid, status, d in results:
        print(f"  {cid:5s}  {status:16s}  {d:.1f}s" if d > 0 else f"  {cid:5s}  {status}")


if __name__ == "__main__":
    main()
