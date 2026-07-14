"""Analyze each music track's audio features for clip matching.

Extracts tempo (BPM), energy (RMS), brightness (spectral centroid), and
harmonic/percussive balance from the first ~60s of each track. Writes
music/analysis.json.
"""
import json, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np
import librosa
sys.path.insert(0, str(Path(__file__).resolve().parent))
import project as P

MUSIC = P.music_dir()
EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def analyze(path):
    y, sr = librosa.load(str(path), sr=22050, mono=True, offset=15.0, duration=30.0)
    if y.size == 0:
        y, sr = librosa.load(str(path), sr=22050, mono=True, duration=30.0)
    if y.size == 0:
        return None
    tempo = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr)[0]).ravel()[0])
    rms = float(np.mean(librosa.feature.rms(y=y)))
    cent = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
    return {
        "tempo": round(tempo, 1),
        "energy": round(rms, 4),
        "brightness": round(cent, 0),
    }


def main():
    outpath = MUSIC / "analysis.json"
    out = json.loads(outpath.read_text()) if outpath.exists() else {}   # resume
    files = [p for p in MUSIC.rglob("*") if p.suffix.lower() in EXTS]
    for i, p in enumerate(sorted(files)):
        key = str(p.relative_to(MUSIC))
        if key in out:
            continue
        try:
            feat = analyze(p)
            if feat:
                out[key] = feat
                print(f"[{i+1}/{len(files)}] {p.name[:45]:45s} bpm={feat['tempo']:5.0f} "
                      f"energy={feat['energy']:.3f} bright={feat['brightness']:.0f}", flush=True)
                outpath.write_text(json.dumps(out, indent=2))     # incremental save
        except Exception as e:
            print(f"[{i+1}] {p.name}: ERR {e}", flush=True)
    print(f"\nanalyzed {len(out)} tracks -> music/analysis.json")


if __name__ == "__main__":
    main()
