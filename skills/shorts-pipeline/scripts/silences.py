"""Detect silences via ffmpeg silencedetect -> edit/silences.json (list of [start,end]).

Usage: silences.py SOURCE [--noise -45] [--min 0.25] [--out edit/silences.json]
Defaults come from style.yaml:cutting.silencedetect.
"""
import argparse, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _util import load_style, run, edit_dir_for  # noqa

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--noise", type=float)
    ap.add_argument("--min", type=float)
    ap.add_argument("--out")
    a = ap.parse_args()
    sd = load_style()["cutting"]["silencedetect"]
    noise = a.noise if a.noise is not None else sd["noise_db"]
    mind = a.min if a.min is not None else sd["min_d"]
    out = a.out or os.path.join(edit_dir_for(a.source), "silences.json")

    r = run(["ffmpeg", "-hide_banner", "-i", str(a.source),
             "-af", f"silencedetect=noise={noise}dB:d={mind}", "-f", "null", "-"],
            check=False)
    text = r.stderr or ""
    vals = re.findall(r"silence_(start|end):\s*([0-9.]+)", text)
    sils, cur = [], None
    for kind, v in vals:
        v = float(v)
        if kind == "start":
            cur = v
        elif cur is not None:
            sils.append([round(cur, 3), round(v, 3)]); cur = None
    json.dump(sils, open(out, "w"), indent=1)
    print(f"[done] {out} ({len(sils)} silences, noise={noise}dB min={mind}s)")

if __name__ == "__main__":
    main()
