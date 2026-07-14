"""Turnkey project configuration — the ONE place episode-specific paths live.

Every tool resolves the current project through this module, so the pipeline is
episode-agnostic: drop a video in a project dir, point the tools at it, and run.
No episode path, source name, or clip list is hardcoded anywhere else.

Resolution order (each getter): env var -> project.json -> auto-detect/derive.

Env vars (all optional):
  PODCAST_PROJECT_DIR  project root (holds the .mp4 and edit/). Default: nearest
                       ancestor of CWD containing edit/ or project.json, else CWD.
  PODCAST_SRC          source video path or stem. Default: the lone .mp4 in the
                       project dir.
  PODCAST_MUSIC_DIR    music root. Default: <project>/music.
  VIDEO_USE_HELPERS    video-use/helpers dir. Default: derived from this file's
                       place in the video-use repo.

project.json in the project dir (all optional):
  {"source": "My-Episode.mp4", "src_name": "My-Episode", "music_dir": "music"}

Per-project clip inputs (the RECALL / TurboScribe list) live in
<project>/edit/clips.json, NOT in code — see load_clips().
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_HERE = Path(__file__).resolve()


def helpers_dir() -> Path:
    env = os.environ.get("VIDEO_USE_HELPERS")
    if env:
        return Path(env).expanduser()
    # this file: <repo>/skills/<skill>/tools/project.py -> repo root = parents[3]
    cand = _HERE.parents[3] / "helpers"
    if cand.is_dir():
        return cand
    for up in _HERE.parents:                      # fallback: search upward
        if (up / "helpers").is_dir():
            return up / "helpers"
    return cand


def project_dir() -> Path:
    env = os.environ.get("PODCAST_PROJECT_DIR")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        if (d / "project.json").exists() or (d / "edit").is_dir():
            return d
    return cwd


def _project_json() -> dict:
    f = project_dir() / "project.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            return {}
    return {}


def source_path() -> Path:
    pd = project_dir()
    cand = os.environ.get("PODCAST_SRC") or _project_json().get("source")
    if cand:
        p = Path(cand).expanduser()
        if p.suffix and (p.is_absolute() or (pd / p).exists() or p.exists()):
            return p if p.is_absolute() else (pd / p)
        stem = p.stem                              # a bare stem was given
        hit = next(iter(sorted(pd.glob(f"{stem}.*"))), None)
        return hit if hit else pd / f"{stem}.mp4"
    mp4s = sorted(pd.glob("*.mp4"))
    if len(mp4s) == 1:
        return mp4s[0]
    if not mp4s:
        raise SystemExit(f"[project] no .mp4 in {pd}; set PODCAST_SRC or project.json 'source'")
    raise SystemExit(f"[project] {len(mp4s)} .mp4 files in {pd}; set PODCAST_SRC to choose one")


def src_name() -> str:
    cfg = _project_json()
    if cfg.get("src_name"):
        return cfg["src_name"]
    env = os.environ.get("PODCAST_SRC")
    if env:
        return Path(env).stem
    return source_path().stem


def edit_dir() -> Path:
    return project_dir() / "edit"


def transcripts_dir() -> Path:
    return edit_dir() / "transcripts"


def transcript_path() -> Path:
    return transcripts_dir() / f"{src_name()}.json"


def chunks_dir() -> Path:
    return transcripts_dir() / "chunks"


def out_dir() -> Path:
    return edit_dir() / "out"


def work_dir() -> Path:
    return edit_dir() / "work"


def context_dir() -> Path:
    return edit_dir() / "context"


def music_dir() -> Path:
    env = os.environ.get("PODCAST_MUSIC_DIR")
    if env:
        return Path(env).expanduser()
    cfg = _project_json()
    if cfg.get("music_dir"):
        p = Path(cfg["music_dir"])
        return p if p.is_absolute() else project_dir() / p
    return project_dir() / "music"


def sources_map() -> dict:
    """The EDL `sources` map: {src_name: absolute source path}."""
    return {src_name(): str(source_path())}


def clips_file() -> Path:
    return edit_dir() / "clips.json"


def load_clips():
    """Per-project clip inputs (the RECALL / TurboScribe list), NOT hardcoded.

    Reads <project>/edit/clips.json:
      [{"id":"c16", "center":3040, "quote":"...", "drifted":false}, ...]
    `center` may be seconds (number) or "H:MM:SS". `drifted` marks a clip whose
    given timestamp is unreliable (locate globally instead of in a window).

    Returns a list of (id, center_seconds, quote, drifted) tuples — empty if the
    file is absent (the concepts-first flow doesn't need it).
    """
    f = clips_file()
    if not f.exists():
        return []
    out = []
    for c in json.loads(f.read_text()):
        center = c.get("center", c.get("timestamp", 0))
        if isinstance(center, str) and ":" in center:
            parts = [float(x) for x in center.split(":")]
            while len(parts) < 3:
                parts.insert(0, 0.0)
            center = parts[0] * 3600 + parts[1] * 60 + parts[2]
        out.append((c["id"], float(center), c.get("quote", ""), bool(c.get("drifted", False))))
    return out


if __name__ == "__main__":
    print("project_dir  :", project_dir())
    print("source_path  :", source_path() if project_dir().glob("*.mp4") else "(no mp4)")
    print("src_name     :", src_name())
    print("transcript   :", transcript_path())
    print("helpers_dir  :", helpers_dir())
    print("music_dir    :", music_dir())
    print("clips        :", len(load_clips()), "loaded")
