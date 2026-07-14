"""Re-render every clip EDL to out/ with render_crop, each in an ISOLATED
working dir so parallel renders don't clobber shared intermediates
(base.mp4, master.ass, clips_graded/, _concat.txt)."""
import glob, subprocess, sys, shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import project as P
ED = P.edit_dir()
OUT = P.out_dir()
WORK = P.work_dir()
edls = sorted(e for e in glob.glob(str(ED / "clip_c*.json")) if "ref" not in e)


def render(edl):
    cid = Path(edl).stem.replace("clip_", "")
    wd = WORK / cid
    wd.mkdir(parents=True, exist_ok=True)
    tl = wd / "transcripts"
    if not tl.exists():
        tl.symlink_to(ED / "transcripts")
    shutil.copy(edl, wd / "clip.json")          # edit_dir = wd (isolated intermediates)
    out = OUT / f"clip_{cid}.mp4"
    r = subprocess.run([sys.executable, str(HERE / "render_crop.py"), str(wd / "clip.json"),
                        "-o", str(out)], capture_output=True, text=True)
    ok = r.returncode == 0 and out.exists()
    if not ok:
        print(f"{cid}: FAIL {r.stderr[-200:]}", flush=True)
    return cid, ok


print(f"rendering {len(edls)} clips (3 workers, isolated)...", flush=True)
done = 0
with ThreadPoolExecutor(max_workers=3) as ex:
    for cid, ok in ex.map(render, edls):
        done += 1
        print(f"  [{done}/{len(edls)}] {cid} {'done' if ok else 'FAILED'}", flush=True)
print("ALL DONE", flush=True)
