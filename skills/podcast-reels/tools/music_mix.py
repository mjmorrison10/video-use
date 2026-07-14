"""Mix a track under a clip using the story-arc technique.

The music uses the best BUILDING segment of the track and CUTS OUT right before
the clip's climax (the final payoff sentence), so the punchline lands in clean
silence. Music sits under the speech and is limited to avoid clipping.

Usage: python music_mix.py <cid> <track_path> <out.mp4> [gain]
"""
import sys, json, subprocess
from pathlib import Path
sys.path.insert(0, "tools")
from music_segment import find_best_segment

ED = Path("edit")
FULL = ED / "transcripts" / "Justin-Waller-vs-Therapist.json"


def clip_words_output(cid):
    edl = json.loads((ED / f"clip_{cid}.json").read_text())
    words = json.loads(FULL.read_text())["words"]
    out = []
    seg_offset = 0.0
    for r in edl["ranges"]:
        ss, se = float(r["start"]), float(r["end"])
        for w in words:
            if w.get("type") != "word":
                continue
            s, e = w.get("start"), w.get("end")
            if s is None or e is None or e <= ss or s >= se:
                continue
            out.append((max(0.0, s - ss) + seg_offset, (w.get("text") or "").strip()))
        seg_offset += se - ss
    out.sort()
    return out, seg_offset


def compute_climax(cid, punch_words=2, tail_min=0.35, tail_max=0.8):
    """Music drops right before the final PUNCH (the last few words), so the
    mic-drop lands in a short (~1.2-3s) silence — not the whole final sentence."""
    ws, total = clip_words_output(cid)
    if not ws:
        return total - tail_max, total
    climax = ws[-punch_words][0] if len(ws) > punch_words else ws[0][0]
    tail = total - climax
    if tail < tail_min:
        climax = total - tail_min
    elif tail > tail_max:
        climax = total - tail_max
    climax = max(3.0, climax)
    return round(climax, 2), round(total, 2)


TARGET_RMS = 0.04     # steady background-bed level (all tracks normalized to this)


def mix(cid, track, out_path, gain=None, level=1.0, compress=False):
    clip = ED / "out" / f"clip_{cid}.mp4"
    climax, total = compute_climax(cid)
    seg_start, seg_rms = find_best_segment(track, climax)
    # normalize each track's segment to a consistent bed level, then hold it at a
    # STEADY low volume under the speech (no ducking -> no pumping). `level` is a
    # per-clip trim; `compress` tames a loud build spike.
    g = (gain if gain is not None else min(3.0, max(0.05, TARGET_RMS / max(seg_rms, 1e-4)))) * level
    fade_out_st = max(0.1, climax - 0.5)
    comp = "acompressor=threshold=0.12:ratio=4:attack=20:release=250," if compress else ""
    af = (f"[1:a]{comp}afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out_st:.2f}:d=0.5,"
          f"volume={g:.3f}[m];"
          f"[0:a][m]amix=inputs=2:normalize=0:duration=first[mix];"
          f"[mix]alimiter=limit=0.97[a]")
    cmd = ["ffmpeg", "-y", "-i", str(clip), "-ss", f"{seg_start:.2f}", "-t", f"{climax:.2f}",
           "-i", str(track), "-filter_complex", af, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print(f"{cid}: climax@{climax}s/{total}s  music seg@{seg_start}s  -> {out_path}")


if __name__ == "__main__":
    cid, track, out = sys.argv[1], sys.argv[2], sys.argv[3]
    gain = float(sys.argv[4]) if len(sys.argv) > 4 else 0.22
    mix(cid, track, Path(out), gain)
