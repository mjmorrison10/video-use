"""Build one or more clips from an agent-authored jobs spec + a client style profile. This is
the committed orchestrator (previously video-work/build_credit.py): it writes each clip's
job.yaml, symlinks shared artifacts, enforces the first-line-is-a-hook absolute, and runs
build_edl -> render_vertical -> captions. Judgment (which spans/accents/climax) lives in the
jobs spec, authored by Claude; everything here is mechanical + reproducible.

jobs spec (JSON):
{
  "source": "/home/user/videos/<proj>/source.mp4",   # transcript.json/silences.json/face_track.json in its edit/
  "client": "orderofman",                              # -> clients/<client>.yaml style profile
  "clips": [
    {"stem": "c01_slug", "hook_text": "first words of the hook (for the absolute check)",
     "spans": [[a,b],[c,d]], "accents": ["WORD",...], "peak_word": 1657}
  ]
}

Usage: build_clips.py JOBS.json [--only c01_slug ...]
Reads clients/<client>.yaml (font/accent/pos/framing/subject_filter). Faces are only needed
for follow/pip framing; skipped for fit/center-crop.
"""
import argparse, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from textmatch import norm1  # noqa
import yaml

RUN = ["uv", "run", "--extra", "pipeline", "python"]
REPO = os.path.dirname(os.path.dirname(SKILL))

def load_profile(name):
    p = os.path.join(SKILL, "clients", f"{name}.yaml")
    if not os.path.exists(p):
        p = os.path.join(SKILL, "clients", "default.yaml")
    return yaml.safe_load(open(p))

def link(src, dst):
    if not (os.path.exists(dst) or os.path.islink(dst)):
        os.symlink(os.path.abspath(src), dst)

def sh(args, label):
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    ok = r.returncode == 0
    tail = (r.stdout if ok else r.stderr).strip().splitlines()
    print(f"  [{label}] {'OK' if ok else 'FAIL'}  {tail[-1] if tail else ''}")
    if not ok:
        print("    " + "\n    ".join(tail[-6:]))
    return ok

_FILLER = {"okay", "ok", "so", "and", "but", "now", "well", "um", "uh", "like", "yeah", "you", "know"}

def _drop_lead_filler(toks):
    i = 0
    while i < len(toks) and toks[i] in _FILLER:
        i += 1
    return toks[i:]

def first_line_is_hook(words, spans, hook_text):
    """Absolute rule: the clip's first kept words must be the selected hook. Leading verbal
    filler (okay/so/and/now/you-know…) is ignored on both sides — the matcher legitimately
    skips it, and it doesn't change which line opens the video."""
    got = _drop_lead_filler([norm1(words[i]["word"]) for i in range(spans[0][0], min(spans[0][0] + 12, spans[0][1] + 1))])
    want = _drop_lead_filler(norm1(hook_text).split())
    want5 = want[:5]
    return bool(want5) and " ".join(want5) in " ".join(got)

def build_one(spec, clip, profile, proj_edit):
    stem = clip["stem"]
    hd = os.path.join(os.path.dirname(spec["source"]), "clips", stem)
    os.makedirs(os.path.join(hd, "edit"), exist_ok=True)
    link(spec["source"], os.path.join(hd, "source.mp4"))
    for f in ("transcript.json", "transcript.txt", "silences.json", "face_track.json", "cameras.json"):
        s = os.path.join(proj_edit, f)
        if os.path.exists(s):
            link(s, os.path.join(hd, "edit", f))
    words = json.load(open(os.path.join(hd, "edit", "transcript.json")))["words"]
    spans = clip["spans"]
    if not first_line_is_hook(words, spans, clip["hook_text"]):
        print(f"  [{stem}] REJECTED — first line is not the hook (absolute rule). "
              f"first span [{spans[0][0]}-{spans[0][1]}] does not open with: {clip['hook_text'][:50]!r}")
        return False
    cap = profile.get("captions", {})
    job = {
        "video": {"drive_id": spec.get("drive_id", ""), "source": os.path.join(hd, "source.mp4"), "stem": stem},
        "hook": {"text": clip["hook_text"]},
        "notes": f"client={spec['client']}",
        "cameras": profile.get("framing", "follow"),
        "subject_filter": profile.get("subject_filter", {"fx": [0, 1920], "fy": [120, 620], "w": [130, 520]}),
        "spans": [{"words": s, **({"beat": "HOOK"} if i == 0 else {})} for i, s in enumerate(spans)],
        "accents": clip.get("accents", []),
        "text_overrides": clip.get("text_overrides", {}),
        "protect": [], "onset_leads": {},
        "peak": {"word_index": clip.get("peak_word", spans[-1][1])},
        "music": {"track": "none", "start_offset": 0},
        "style_overrides": {"captions": {k: cap[k] for k in ("font", "accent", "pos", "size") if k in cap}},
    }
    yaml.safe_dump(job, open(os.path.join(hd, "edit", "job.yaml"), "w"), sort_keys=False)
    print(f"=== {stem} ({len(spans)} spans) ===")
    ed = os.path.join(hd, "edit")
    src = os.path.join(hd, "source.mp4")
    P = f"{SKILL}/scripts"
    if job["cameras"] in ("follow", "pip") and not os.path.exists(f"{ed}/face_track.json"):
        if not sh(RUN + [f"{P}/faces.py", src, "--fps", "3"], "faces"):
            return False
    if not os.path.exists(f"{ed}/silences.json"):
        if not sh(RUN + [f"{P}/silences.py", src], "silences"):
            return False
    for scr, lbl, extra in [("build_edl.py", "build_edl", [f"{ed}/job.yaml"]),
                            ("render_vertical.py", "render", [f"{ed}/plan.json", "--source", src, "-o", f"{ed}/base.mp4"]),
                            ("captions.py", "captions", [f"{ed}/job.yaml"])]:
        if not sh(RUN + [f"{P}/{scr}"] + extra, lbl):
            return False
    return os.path.exists(f"{ed}/{stem}_clean.mp4")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs"); ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    spec = json.load(open(a.jobs))
    profile = load_profile(spec["client"])
    proj_edit = os.path.join(os.path.dirname(spec["source"]), "edit")
    res = {}
    for clip in spec["clips"]:
        if a.only and clip["stem"] not in a.only:
            continue
        res[clip["stem"]] = build_one(spec, clip, profile, proj_edit)
    print("\n=== SUMMARY ===")
    for stem, ok in res.items():
        print(f"  {'OK  ' if ok else 'FAIL'} {stem}")

if __name__ == "__main__":
    main()
