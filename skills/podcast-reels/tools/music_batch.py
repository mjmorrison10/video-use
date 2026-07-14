"""Apply the matched music to every clip -> edit/out/music_<cid>.mp4."""
import json, sys
from pathlib import Path
sys.path.insert(0, "tools")
import music_mix as M

ED = Path("edit")
mapping = json.loads((ED / "music_map.json").read_text())
levels = json.loads((ED / "music_levels.json").read_text()) if (ED / "music_levels.json").exists() else {}
for cid in sorted(mapping, key=lambda x: int(x[1:])):
    track = "music/" + mapping[cid]
    out = ED / "out" / f"music_{cid}.mp4"
    cfg = levels.get(cid, {})
    try:
        M.mix(cid, track, out, level=cfg.get("level", 1.0), compress=cfg.get("compress", False))
    except Exception as e:
        print(f"{cid}: FAIL {e}", flush=True)
print("ALL MUSIC DONE", flush=True)
