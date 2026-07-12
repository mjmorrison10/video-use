"""Shared helpers for shorts-pipeline scripts."""
import os, subprocess, sys, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)          # skills/shorts-pipeline
REPO = os.path.dirname(os.path.dirname(SKILL_DIR))  # video-use repo root

def load_style():
    with open(os.path.join(SKILL_DIR, "style.yaml")) as f:
        return yaml.safe_load(f)

def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)

def run(cmd, check=True, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        sys.stderr.write("CMD FAILED: %s\n%s\n" % (" ".join(map(str, cmd)), (r.stderr or "")[-2000:]))
        raise SystemExit(1)
    return r

def ffprobe_duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip())

def extract_wav(src, out_wav, start=None, end=None):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if end is not None:
        cmd += ["-to", f"{end:.3f}"]
    cmd += ["-i", str(src), "-ac", "1", "-ar", "16000", "-vn", str(out_wav)]
    run(cmd)
    return out_wav

def even(v):
    return int(round(v / 2) * 2)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def edit_dir_for(source):
    d = os.path.join(os.path.dirname(os.path.abspath(source)), "edit")
    os.makedirs(d, exist_ok=True)
    return d
