"""Re-burn captions onto existing per-clip bases (no reframe needed).

Uses edit/work/<cid>/base.mp4 (post-crop, pre-caption, pre-loudnorm), rebuilds
the ASS with the current style, burns it, and loudnorms -> edit/out/clip_<cid>.mp4.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as P
import ass_captions as AC
import render_crop as RC
import render as R

ED = P.edit_dir()


def main():
    cids = sys.argv[1:] or [p.stem.replace("clip_", "") for p in sorted(ED.glob("clip_c*.json"))]
    for cid in cids:
        edl_path = ED / f"clip_{cid}.json"
        base = ED / "work" / cid / "base.mp4"
        if not base.exists():
            print(f"{cid}: no base, skip"); continue
        edl = json.loads(edl_path.read_text())
        ass = ED / "work" / cid / "master.ass"
        AC.write_ass(AC.build_events(edl, ED), ass)         # transcripts at edit/transcripts
        out = ED / "out" / f"clip_{cid}.mp4"
        tmp = out.with_suffix(".prenorm.mp4")
        RC.burn_ass(base, ass, tmp)
        R.apply_loudnorm_two_pass(tmp, out, preview=False)
        tmp.unlink(missing_ok=True)
        print(f"{cid}: re-burned -> {out.name}")


if __name__ == "__main__":
    main()
