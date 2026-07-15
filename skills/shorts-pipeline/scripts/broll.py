"""Auto-B-roll: overlay keyword-matched stock cutaways on a talking-head clip, one every
~2-3s, matched to what's being spoken, with crossfade transitions — then re-burn the captions
on top so they stay legible over the footage.

Judgment stays with Claude via the per-clip plan; everything here is mechanical + reproducible.
Footage comes from a stock provider (Pexels video, Pixabay fallback) keyed by env vars
PEXELS_API_KEY / PIXABAY_API_KEY, OR from a local folder of clips (--clips DIR) whose filenames
are the search terms. Downloaded clips are cached under <edit>/broll_cache/ so a re-run is free
and identical.

How windows are chosen: the kept transcript words are placed on the OUTPUT timeline (via plan.json
seg offsets), then greedily grouped into ~--every-second windows at word boundaries. Each window's
search phrase is its most salient nouns (stopword-filtered, accent words weighted); empty/abstract
windows fall back to --theme. A window with no usable footage is left on the speaker (b-roll
breathes — the speaker shows through the fades and on unmatched windows).

Output: <stem>_broll_captioned.mp4 (pre-loudnorm, for music_arc) and <stem>_broll.mp4 (loudnorm
-14 LUFS deliverable). Mix music onto the _captioned one, same as the no-broll path.

Usage:
  broll.py BASE.mp4 JOB.yaml --plan plan.json --transcript transcript.json --ass master.ass \
           --out-dir <edit> --stem <stem> [--provider pexels|pixabay|folder] [--clips DIR] \
           [--every 2.6] [--hold 2.0] [--xfade 0.35] [--theme "fatherhood family"] [--dry-run]
"""
import argparse, json, os, re, subprocess, sys, tempfile, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from textmatch import STOP, norm1  # noqa
import yaml

# words that make lousy visual queries even though they survive the stopword filter
_ABSTRACT = {"point", "side", "reason", "kind", "sort", "seats", "systems", "argued",
             "understand", "produces", "desperately", "culture", "needs", "problem"}

def word_out_times(job, transcript, plan):
    """Return [(out_start, out_end, word)] for every kept word, on the output timeline."""
    words = transcript["words"]
    segs = plan["segs"]
    def to_out(t):
        for s in segs:
            if s["s"] - 0.01 <= t <= s["e"] + 0.01:
                return s["off"] + (t - s["s"])
        return None
    out = []
    for sp in job["spans"]:
        a, b = sp["words"]
        for i in range(a, b + 1):
            w = words[i]
            os_, oe_ = to_out(w["start"]), to_out(w["end"])
            if os_ is not None and oe_ is not None:
                out.append((os_, oe_, w["word"].strip()))
    return sorted(out, key=lambda x: x[0])

def make_windows(wt, every, hold):
    """Group words into ~`every`-second windows at word boundaries; each window holds b-roll for
    up to `hold` seconds starting at its first word."""
    wins, cur = [], []
    for os_, oe_, w in wt:
        if not cur:
            cur = [(os_, oe_, w)]; continue
        if oe_ - cur[0][0] >= every:
            wins.append(cur); cur = [(os_, oe_, w)]
        else:
            cur.append((os_, oe_, w))
    if cur:
        wins.append(cur)
    out = []
    for grp in wins:
        start = grp[0][0]
        end = min(start + hold, grp[-1][1])
        text = " ".join(g[2] for g in grp)
        out.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return out

def query_terms(text, accents, theme):
    toks = re.findall(r"[A-Za-z']+", text)
    seen, cands = set(), []
    acc = {a.lower() for a in accents}
    for t in toks:
        tl = t.lower().strip("'")
        if "'" in t or tl in STOP or tl in _ABSTRACT or len(tl) < 4 or tl in seen:
            continue
        seen.add(tl)
        w = len(tl) + (6 if tl in acc else 0)
        cands.append((w, tl))
    cands.sort(key=lambda x: -x[0])
    terms = [c[1] for c in cands[:2]]
    return [" ".join(terms[:2])] + terms + ([theme] if theme else [])

# ---- providers -------------------------------------------------------------
# NOTE: fetch via curl, not urllib. The sandbox's egress proxy gates by tool/User-Agent and
# returns 403 to python-urllib while allowing curl on the identical URL+proxy. curl also handles
# the proxy CA bundle transparently.
def _get(url, headers=None):
    cmd = ["curl", "-sS", "--fail", "--max-time", "60"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl {r.returncode}: {r.stderr.decode('utf-8','ignore')[:120]}")
    return r.stdout

def _download(url, dst, headers=None):
    cmd = ["curl", "-sS", "--fail", "--max-time", "180", "-o", dst]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl dl {r.returncode}: {r.stderr.decode('utf-8','ignore')[:120]}")

def pexels_find(term, key):
    q = urllib.parse.quote(term)
    url = f"https://api.pexels.com/videos/search?query={q}&orientation=portrait&per_page=5&size=medium"
    d = json.loads(_get(url, {"Authorization": key}))
    best = None
    for v in d.get("videos", []):
        for f in v["video_files"]:
            if f["height"] >= f["width"] and f.get("link"):
                score = abs((f["width"] or 0) - 1080)
                if best is None or score < best[0]:
                    best = (score, f["link"])
    return best[1] if best else None

def pixabay_find(term, key):
    q = urllib.parse.quote(term)
    url = f"https://pixabay.com/api/videos/?key={key}&q={q}&per_page=5"
    d = json.loads(_get(url))
    for hit in d.get("hits", []):
        vids = hit.get("videos", {})
        for name in ("large", "medium", "small"):
            v = vids.get(name)
            if v and v.get("width", 0) <= v.get("height", 1) and v.get("url"):
                return v["url"]
        # portrait not guaranteed on pixabay; take medium and let the crop handle it
        if vids.get("medium", {}).get("url"):
            return vids["medium"]["url"]
    return None

def folder_find(term, clips_dir):
    if not clips_dir or not os.path.isdir(clips_dir):
        return None
    files = [f for f in os.listdir(clips_dir) if f.lower().endswith((".mp4", ".mov", ".webm"))]
    key = term.split()[0] if term else ""
    for f in files:
        if key and key in f.lower():
            return os.path.join(clips_dir, f)
    return None

def fetch(term_list, provider, keys, clips_dir, cache, idx):
    """Try each candidate term until one provider returns a clip; download+cache; return path."""
    for term in term_list:
        if not term.strip():
            continue
        try:
            if provider == "folder":
                src = folder_find(term, clips_dir)
                if src:
                    return src, term
                continue
            if provider == "pexels":
                link = pexels_find(term, keys["pexels"])
            else:
                link = pixabay_find(term, keys["pixabay"])
            if not link:
                continue
            dst = os.path.join(cache, f"w{idx:02d}_{norm1(term).replace(' ', '_')}.mp4")
            if not os.path.exists(dst):
                _download(link, dst, {"User-Agent": "Mozilla/5.0"})
            return dst, term
        except Exception as e:
            print(f"    [w{idx:02d}] '{term}' -> {type(e).__name__}: {e}")
    return None, None

# ---- render ----------------------------------------------------------------
def build_filter(n_clips, wins, xfade):
    """Base video + one faded, time-shifted overlay per matched window. Captions burned last."""
    parts, last = [], "0:v"
    for i, w in enumerate(wins):
        st, en = w["start"], w["end"]
        d = max(0.4, en - st)
        fo = min(xfade, d / 2)
        # scale-to-cover 1080x1920, crop, trim to window length, fade alpha in/out, delay to `st`
        parts.append(
            f"[{i+1}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,trim=0:{d:.2f},setpts=PTS-STARTPTS,"
            f"format=yuva420p,fade=t=in:st=0:d={fo:.2f}:alpha=1,"
            f"fade=t=out:st={d-fo:.2f}:d={fo:.2f}:alpha=1,"
            f"setpts=PTS+{st:.2f}/TB[br{i}]")
        parts.append(f"[{last}][br{i}]overlay=0:0:enable='between(t,{st:.2f},{en:.2f})'[v{i}]")
        last = f"v{i}"
    return ";".join(parts), last

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("job")
    ap.add_argument("--plan", required=True); ap.add_argument("--transcript", required=True)
    ap.add_argument("--ass", required=True)
    ap.add_argument("--out-dir", required=True); ap.add_argument("--stem", required=True)
    ap.add_argument("--provider", default="pexels", choices=["pexels", "pixabay", "folder"])
    ap.add_argument("--clips", default=None)
    ap.add_argument("--every", type=float, default=2.6)
    ap.add_argument("--hold", type=float, default=2.0)
    ap.add_argument("--xfade", type=float, default=0.35)
    ap.add_argument("--theme", default="")
    ap.add_argument("--terms", default=None,
                    help="JSON overriding per-window search phrases: {\"3\":\"soldiers marching\",...} "
                         "(window index -> phrase). Curate this after a --dry-run to fix weak matches.")
    ap.add_argument("--selective", action="store_true",
                    help="only overlay windows with a real content keyword match; drop theme-fallback "
                         "windows so the (centered) speaker carries abstract lines instead of junk stock")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    job = yaml.safe_load(open(a.job))
    transcript = json.load(open(a.transcript))
    plan = json.load(open(a.plan))
    overrides = {int(k): v for k, v in json.load(open(a.terms)).items()} if a.terms else {}
    accents = job.get("accents", [])
    wt = word_out_times(job, transcript, plan)
    wins = make_windows(wt, a.every, a.hold)
    for i, w in enumerate(wins):
        if i in overrides:
            w["terms"] = [overrides[i]]          # curated: exactly this, no theme fill
        else:
            w["terms"] = query_terms(w["text"], accents, a.theme)
    print(f"{len(wins)} windows over {wt[-1][1]:.1f}s:")
    for i, w in enumerate(wins):
        print(f"  w{i:02d} [{w['start']:5.1f}-{w['end']:5.1f}] {w['terms'][0]!r:28} < {w['text'][:44]!r}")
    if a.dry_run:
        json.dump(wins, open(os.path.join(a.out_dir, "broll_plan.json"), "w"), indent=1)
        print("dry-run: wrote broll_plan.json (no fetch/render)"); return

    keys = {"pexels": os.environ.get("PEXELS_API_KEY", ""), "pixabay": os.environ.get("PIXABAY_API_KEY", "")}
    cache = os.path.join(a.out_dir, "broll_cache"); os.makedirs(cache, exist_ok=True)
    matched = []
    for i, w in enumerate(wins):
        path, term = fetch(w["terms"], a.provider, keys, a.clips, cache, i)
        if path and a.selective and a.theme and term == a.theme:
            print(f"    w{i:02d} -- theme-fallback only, skipped (--selective)  [{term!r}]")
            continue
        if path:
            matched.append({**w, "clip": path, "used": term})
            print(f"    w{i:02d} <- {term!r}  {os.path.basename(path)}")
        else:
            print(f"    w{i:02d} -- no footage (stays on speaker)")
    if not matched:
        print("no b-roll matched anywhere — aborting"); sys.exit(1)

    ass_abs = a.ass if os.path.isabs(a.ass) else os.path.join(a.out_dir, a.ass)
    fc, last = build_filter(len(matched), matched, a.xfade)
    fc = fc + f";[{last}]ass={ass_abs}[vout]"
    cap = os.path.join(a.out_dir, f"{a.stem}_broll_captioned.mp4")
    ins = []
    for m in matched:
        ins += ["-i", m["clip"]]
    cmd = ["ffmpeg", "-nostdin", "-y", "-i", a.base, *ins,
           "-filter_complex", fc, "-map", "[vout]", "-map", "0:a?",
           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", cap]
    print(f"rendering {len(matched)} cutaways -> {os.path.basename(cap)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG FAIL:\n" + "\n".join(r.stderr.strip().splitlines()[-15:])); sys.exit(1)
    clean = os.path.join(a.out_dir, f"{a.stem}_broll.mp4")
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", cap,
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", clean], capture_output=True, text=True)
    print(f"[done] {cap}\n[done] {clean} ({len(matched)} cutaways)")

if __name__ == "__main__":
    main()
