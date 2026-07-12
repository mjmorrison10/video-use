"""Analyze a folder of music tracks so the agent can pick one and align its drop to the clip's
emotional peak. Writes music_index.json.

Per track: duration, tempo (BPM), rms_mean, peak_time (loudest moment), drop_time (largest
energy jump = the "drop"), and a downsampled energy curve. The agent chooses by vibe (filename/
artist knowledge) + tempo/energy, then sets music.start_offset = drop_time - clip_peak_time.

Usage: music_scan.py MUSIC_DIR [--out MUSIC_DIR/music_index.json]
"""
import argparse, glob, json, os

AUDIO_EXT = (".mp3", ".m4a", ".wav", ".flac", ".aac", ".ogg", ".opus")

def analyze(path):
    import numpy as np, librosa
    y, sr = librosa.load(path, mono=True)
    dur = len(y) / sr
    try:
        tp = librosa.feature.rhythm.tempo(y=y, sr=sr)
    except Exception:
        tp = librosa.beat.beat_track(y=y, sr=sr)[0]
    tempo = float(np.atleast_1d(tp).ravel()[0])
    hop = 2048
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop)
    sm = np.convolve(rms, np.ones(9) / 9, mode="same")
    peak_time = float(times[int(np.argmax(sm))])
    d = np.diff(sm)
    drop_time = float(times[int(np.argmax(d)) + 1]) if len(d) else peak_time
    # downsample energy curve to ~60 points
    step = max(1, len(sm) // 60)
    curve = [round(float(x), 4) for x in sm[::step]]
    return {"file": os.path.basename(path), "path": os.path.abspath(path),
            "duration": round(dur, 2), "bpm": round(tempo, 1),
            "rms_mean": round(float(np.mean(rms)), 4),
            "peak_time": round(peak_time, 2), "drop_time": round(drop_time, 2),
            "energy_curve": curve}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("music_dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    files = sorted(f for f in glob.glob(os.path.join(a.music_dir, "*"))
                   if f.lower().endswith(AUDIO_EXT))
    tracks = []
    for f in files:
        try:
            tracks.append(analyze(f))
            print(f"  {os.path.basename(f):40} bpm={tracks[-1]['bpm']:5} "
                  f"drop@{tracks[-1]['drop_time']:.1f}s peak@{tracks[-1]['peak_time']:.1f}s")
        except Exception as e:
            print(f"  [skip] {os.path.basename(f)}: {e}")
    out = a.out or os.path.join(a.music_dir, "music_index.json")
    json.dump({"tracks": tracks}, open(out, "w"), indent=1)
    print(f"[done] {out} ({len(tracks)} tracks)")

if __name__ == "__main__":
    main()
