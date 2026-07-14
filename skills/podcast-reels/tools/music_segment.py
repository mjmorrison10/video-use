"""Find the best 'building' segment of a track for a reel.

Scans the whole song's energy envelope and returns the start offset of a window
of the requested duration that RISES toward its end (so the music swells and can
be cut right at the clip's climax). Avoids near-silent intro/outro windows.
"""
import sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import librosa


def find_best_segment(track_path, duration, step=1.0):
    y, sr = librosa.load(str(track_path), sr=22050, mono=True)
    total = len(y) / sr
    if total <= duration + 0.5:
        return 0.0                      # song shorter than needed: start at 0
    hop = 2048
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    win = duration
    best_start, best_score, best_rms = 0.0, -1e9, 0.05
    s = 0.0
    peak = float(np.max(rms)) + 1e-9
    while s + win <= total:
        m = (t >= s) & (t < s + win)
        seg = rms[m]
        if seg.size < 4:
            s += step; continue
        n = seg.size
        first = float(np.mean(seg[: n // 3]))
        last = float(np.mean(seg[-n // 3:]))
        end_peak = float(np.max(seg[-n // 4:]))
        avg = float(np.mean(seg))
        # reward: builds (last>first), ends high, decent average energy
        score = (last - first) * 2.0 + (end_peak / peak) * 1.0 + (avg / peak) * 0.6
        if avg < 0.02 * peak:           # penalize near-silent windows
            score -= 5.0
        if score > best_score:
            best_score, best_start, best_rms = score, s, avg
        s += step
    return round(best_start, 2), round(best_rms, 5)


if __name__ == "__main__":
    print(find_best_segment(sys.argv[1], float(sys.argv[2])))
