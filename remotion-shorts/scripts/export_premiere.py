#!/usr/bin/env python3
"""Export a rendered Remotion short as an Adobe Premiere-importable package.

The Remotion render is flattened — captions, music and the CTA card are burned
in, so there is nothing left to polish. This rebuilds the same edit as an NLE
timeline:

  <name>.xml   FCP7 XML (xmeml v4) — the cuts, against an assembled media file
               that carries handles, so cuts can still be trimmed/extended.
  <name>.edl   CMX3600 with MASTER timecodes, for conforming against the full
               original interview instead of the assembled media.
  <name>_captions.srt            one cue per rendered caption page
  <name>_captions_sentences.srt  same words merged into sentence-length cues
  README.md    import steps + the burned-in text Premiere cannot recover

Timecode base is whole-frame non-drop (the sources here are true 30fps).

Usage:
  export_premiere.py --job jobs/x.json --snap jobs/x.snap.cutspec.json \
      --cutspec jobs/x.cutspec.json --master /path/interview.mp4 \
      --transcript /path/words.json --outdir /path/premiere [--handles 2.0] [--vf ...]
"""
import argparse, json, subprocess, sys
from pathlib import Path

FPS = 30


# ---------- formatters ----------
def tc(sec: float, fps: int = FPS) -> str:
    """HH:MM:SS:FF non-drop, for EDL and XML."""
    f = int(round(sec * fps))
    h, rem = divmod(f, 3600 * fps)
    m, rem = divmod(rem, 60 * fps)
    s, ff = divmod(rem, fps)
    return f"{h:02d}:{m:02d}:{s:02d}:{ff:02d}"


def srt_ts(sec: float) -> str:
    """HH:MM:SS,mmm (same shape as helpers/render.py::_srt_timestamp)."""
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def fr(sec: float, fps: int = FPS) -> int:
    return int(round(sec * fps))


def tcf(frames: int, fps: int = FPS) -> str:
    """HH:MM:SS:FF from an exact frame count."""
    h, rem = divmod(frames, 3600 * fps)
    m, rem = divmod(rem, 60 * fps)
    s, ff = divmod(rem, fps)
    return f"{h:02d}:{m:02d}:{s:02d}:{ff:02d}"


def lay_out(segs, fps: int = FPS):
    """Walk the cuts once and fix every frame number here, so the record timeline
    is gapless by construction and each clip's source length is defined as its
    record length. Rounding beatIn/beatOut and offsetSec independently lets a clip
    come out a frame longer in source than on the timeline, which an NLE reads as
    a speed change."""
    rows, rec = [], 0
    for s in segs:
        n = fr(s["durSec"], fps)
        src_in = fr(s["beatIn"], fps)
        rows.append({**s, "recIn": rec, "recOut": rec + n,
                     "srcIn": src_in, "srcOut": src_in + n, "frames": n})
        rec += n
    return rows, rec


def xesc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------- FCP7 XML ----------
def build_xml(name, segs, media_name, media_path, media_dur, music, seq_frames, w=1080, h=1920):
    """segs: rows from the assemble map (beatIn/beatOut are positions IN the
    assembled file; offsetSec is the position on the output timeline)."""
    def file_el(fid, fname, fpath, dur_frames, has_video=True):
        vid = (f"<video><samplecharacteristics><width>{w}</width>"
               f"<height>{h}</height></samplecharacteristics></video>") if has_video else ""
        return (f'<file id="{fid}"><name>{xesc(fname)}</name>'
                f'<pathurl>file://localhost{xesc(fpath)}</pathurl>'
                f"<rate><timebase>{FPS}</timebase><ntsc>FALSE</ntsc></rate>"
                f"<duration>{dur_frames}</duration>"
                f"<media>{vid}<audio><channelcount>2</channelcount></audio></media></file>")

    v_items, a_items = [], []
    for i, s in enumerate(segs):
        st, en = s["recIn"], s["recOut"]
        in_, out_ = s["srcIn"], s["srcOut"]
        # first reference defines the file, the rest point at it by id
        f_v = file_el("file-1", media_name, media_path, fr(media_dur)) if i == 0 else '<file id="file-1"/>'
        f_a = '<file id="file-1"/>'
        nm = xesc(s.get("beat") or f"seg{i+1}")
        v_items.append(
            f'<clipitem id="cv-{i+1}"><name>{nm}</name><enabled>TRUE</enabled>'
            f"<duration>{fr(media_dur)}</duration>"
            f"<rate><timebase>{FPS}</timebase><ntsc>FALSE</ntsc></rate>"
            f"<start>{st}</start><end>{en}</end><in>{in_}</in><out>{out_}</out>{f_v}</clipitem>")
        a_items.append(
            f'<clipitem id="ca-{i+1}"><name>{nm}</name><enabled>TRUE</enabled>'
            f"<duration>{fr(media_dur)}</duration>"
            f"<rate><timebase>{FPS}</timebase><ntsc>FALSE</ntsc></rate>"
            f"<start>{st}</start><end>{en}</end><in>{in_}</in><out>{out_}</out>{f_a}"
            f"<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>"
            f"</clipitem>")

    music_track = ""
    if music:
        mdur = fr(music["durSec"])
        music_track = (
            "<track>"
            f'<clipitem id="cm-1"><name>{xesc(music["name"])}</name><enabled>TRUE</enabled>'
            f"<duration>{mdur}</duration>"
            f"<rate><timebase>{FPS}</timebase><ntsc>FALSE</ntsc></rate>"
            f"<start>0</start><end>{min(seq_frames, mdur)}</end>"
            f"<in>{fr(music.get('startSec', 0))}</in><out>{fr(music.get('startSec', 0)) + min(seq_frames, mdur)}</out>"
            + file_el("file-2", music["name"], music["path"], mdur, has_video=False)
            + "<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>"
            "</clipitem></track>")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">\n'
        f'<sequence id="{xesc(name)}"><name>{xesc(name)}</name>'
        f"<duration>{seq_frames}</duration>"
        f"<rate><timebase>{FPS}</timebase><ntsc>FALSE</ntsc></rate>"
        "<media><video><format><samplecharacteristics>"
        f"<width>{w}</width><height>{h}</height>"
        f"<rate><timebase>{FPS}</timebase><ntsc>FALSE</ntsc></rate>"
        "</samplecharacteristics></format>"
        "<track>" + "".join(v_items) + "</track></video>"
        "<audio><track>" + "".join(a_items) + "</track>" + music_track + "</audio>"
        "</media></sequence>\n</xmeml>\n")


# ---------- CMX3600 EDL ----------
def build_edl(title, segs, reel="AX", clip_name="interview859.mp4"):
    out = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    for i, s in enumerate(segs, 1):
        m_in = fr(s['masterIn'])
        out.append(f"{i:03d}  {reel:<8} V     C        "
                   f"{tcf(m_in)} {tcf(m_in + s['frames'])} "
                   f"{tcf(s['recIn'])} {tcf(s['recOut'])}")
        out.append(f"* FROM CLIP NAME: {clip_name}")
        if s.get("beat"):
            out.append(f"* COMMENT: {s['beat']}")
        out.append("")
    return "\n".join(out)


# ---------- SRT ----------
def srt_from_pages(pages):
    cues = []
    for i, p in enumerate(pages, 1):
        txt = "".join(t["text"] for t in p["tokens"]).strip()
        cues.append(f"{i}\n{srt_ts(p['startMs']/1000)} --> {srt_ts(p['endMs']/1000)}\n{txt}\n")
    return "\n".join(cues)


MIN_WORD_INSIDE = 0.08   # a word with less than this inside the cut is edge bleed


def srt_sentences(segs, words, max_chars=72):
    """Remap master-time words onto the output timeline, then cut cues at
    sentence punctuation (falling back on a pause) — keeps real punctuation and
    currency intact, unlike the punctuation-stripped on-screen pages.

    Cues never span a cut: each beat is its own thought, and the snap leaves ~40ms
    of the *next* word at each out-point, which must not be written as content."""
    cues = []
    for s in segs:
        flat = []
        for w in words:
            if not (s["masterIn"] <= w["start"] < s["masterOut"]):
                continue
            if min(w["end"], s["masterOut"]) - w["start"] < MIN_WORD_INSIDE:
                continue                      # trailing-word bleed, not spoken content
            flat.append({"text": w["text"],
                         "start": s["offsetSec"] + (w["start"] - s["masterIn"]),
                         "end": s["offsetSec"] + (min(w["end"], s["masterOut"]) - s["masterIn"])})
        cur = []
        for i, w in enumerate(flat):
            cur.append(w)
            last = i == len(flat) - 1
            gap = (flat[i + 1]["start"] - w["end"]) if not last else 9
            joined = "".join(x["text"] for x in cur).strip()
            if (w["text"].strip().endswith((".", "?", "!")) or gap >= 0.45
                    or len(joined) >= max_chars or last):
                cues.append((cur[0]["start"], cur[-1]["end"], joined))
                cur = []
    return "\n".join(f"{i}\n{srt_ts(a)} --> {srt_ts(b)}\n{t}\n"
                     for i, (a, b, t) in enumerate(cues, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True); ap.add_argument("--snap", required=True)
    ap.add_argument("--cutspec", required=True); ap.add_argument("--master", required=True)
    ap.add_argument("--transcript", required=True); ap.add_argument("--outdir", required=True)
    ap.add_argument("--handles", type=float, default=2.0)
    ap.add_argument("--vf", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--skip-assemble", action="store_true")
    a = ap.parse_args()

    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    job = json.loads(Path(a.job).read_text())
    snap = json.loads(Path(a.snap).read_text())
    spec = json.loads(Path(a.cutspec).read_text())
    name = a.name or Path(a.job).stem
    media_name = f"{name}_handles.mp4"
    mapfile = outdir / f"{name}_map.json"

    # a job-shaped file carrying MASTER times (the real job was remapped to the
    # assembled media when it was rendered, so it can't drive this)
    cum, ranges = 0.0, []
    for s in snap["segments"]:
        d = s["outSec"] - s["inSec"]
        ranges.append({"inSec": s["inSec"], "outSec": s["outSec"],
                       "offsetSec": round(cum, 3), "beat": s.get("beat")})
        cum += d
    tmpjob = outdir / f"{name}_master_ranges.json"
    tmpjob.write_text(json.dumps({"ranges": ranges}, indent=1))

    if not a.skip_assemble:
        cmd = [sys.executable, str(Path(__file__).with_name("assemble_src.py")),
               str(tmpjob), a.master, "--pubdir", str(outdir),
               "--handles", str(a.handles), "--out", media_name, "--map", str(mapfile)]
        if a.vf:
            cmd += ["--vf", a.vf]
        subprocess.run(cmd, check=True)

    m = json.loads(mapfile.read_text())
    segs = m["segments"]
    media_path = str((outdir / media_name).resolve())
    media_dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", media_path],
        capture_output=True, text=True, check=True).stdout.strip())

    segs, content_frames = lay_out(segs)
    # sanity: exact lengths, gapless record, and every cut inside the media
    for i, s in enumerate(segs):
        assert s["srcOut"] - s["srcIn"] == s["recOut"] - s["recIn"], f"seg {i} length mismatch"
        assert i == 0 or segs[i - 1]["recOut"] == s["recIn"], f"gap before seg {i}"
        assert s["srcOut"] <= fr(media_dur) + 1, f"seg {i} runs past the media"
        assert abs((s["beatOut"] - s["beatIn"]) - s["durSec"]) < 1.5 / FPS, f"seg {i} map drift"
    content_sec = content_frames / FPS
    cta = job.get("cta")
    seq_frames = content_frames + (fr(cta["durSec"]) if cta else 0)

    music = None
    if job.get("music"):
        mp = Path("public") / job["music"]["src"]
        if mp.exists():
            mdur = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp)],
                capture_output=True, text=True, check=True).stdout.strip())
            music = {"name": mp.name, "path": str(mp.resolve()), "durSec": mdur,
                     "startSec": job["music"].get("startSec", 0)}

    (outdir / f"{name}.xml").write_text(
        build_xml(name, segs, media_name, media_path, media_dur, music, seq_frames))
    (outdir / f"{name}.edl").write_text(
        build_edl(name.upper(), segs, clip_name=Path(a.master).name))
    (outdir / f"{name}_captions.srt").write_text(srt_from_pages(job["captionPages"]))
    words = json.loads(Path(a.transcript).read_text())["words"]
    (outdir / f"{name}_captions_sentences.srt").write_text(srt_sentences(segs, words))

    # ---- README: everything the XML structurally cannot carry ----
    st = job.get("style", {})
    hook = spec.get("hook") or {}
    lines = [
        f"# {name} — Premiere package", "",
        f"Sequence: **1080x1920, {FPS}fps**, {seq_frames} frames "
        f"({seq_frames/FPS:.2f}s) — {content_sec:.2f}s of footage"
        + (f" + {cta['durSec']}s CTA card" if cta else ""), "",
        "## Import", "",
        f"1. Put `{media_name}` and `{Path(music['name']).name if music else '(music)'}` in one folder.",
        f"2. Premiere → File → Import → `{name}.xml`. It builds the sequence with all "
        f"{len(segs)} cuts, dialogue, and the music track.",
        f"3. If it asks to relink, point at `{media_name}`.",
        f"4. Captions: File → Import → `{name}_captions.srt` (matches the render, ~1 cue/page) "
        f"or `{name}_captions_sentences.srt` (fewer, longer cues, real punctuation). "
        "Drag onto the timeline, then restyle in the Essential Graphics panel.", "",
        f"**Handles:** every clip carries {a.handles}s of extra media on each side, so you can "
        "extend or slip any cut. The trim points are exactly where the render cut.", "",
        "## Conforming against the full interview instead", "",
        f"`{name}.edl` carries **master timecodes** into `{Path(a.master).name}` "
        f"(the {Path(a.master).name} you can pull from MEGA). Import the EDL, relink to the "
        "master, and you get the same cuts with the entire interview available — at the cost "
        "of redoing the vertical reframe (see below).", "",
        "## Vertical reframe (already baked into the handles media)", "",
        "The source is a side-by-side remote call. The 9:16 framing is a crop of his panel:",
        "",
        "```", f"crop=308:548:1226:266   # from the 1920x1080 master", "scale=1080:1920", "```",
        "",
        "In Premiere terms on a 1920x1080 clip in a 1080x1920 sequence: **Scale ≈ 350.6%**, "
        "**Position ≈ (-932, 960)**. You only need this if you conform via the EDL — "
        f"`{media_name}` is already cropped.", "",
        "## Burned-in elements the XML cannot carry", "",
        "These are Remotion React components, not media — rebuild as Premiere titles:", "",
    ]
    if hook.get("text"):
        lines += [f"- **Hook overlay** (0 → {hook.get('untilSec', 2.5)}s): `{hook['text']}`"]
    if cta:
        lines += [f"- **CTA end card** (last {cta['durSec']}s, black background): "
                  f"`{cta['text']}` / sub: `{cta.get('sub','')}`"]
    lines += [
        f"- **Caption style**: serif, uppercase, {st.get('fontSize', 58)}px, white with black "
        f"stroke, positioned {st.get('captionPosition','bottom')} "
        f"({st.get('captionBottom','')}px from bottom).",
        f"- **Power words** render in cyan `{st.get('accentColor', '#00E5FF')}` with a neon glow: "
        + ", ".join(f"`{w}`" for w in st.get("powerWords", [])), "",
        "## Music", "",
    ]
    if music:
        mj = job["music"]
        lines += [f"- `{music['name']}`, volume {mj.get('volLow')} → {mj.get('volHigh')}, "
                  f"peaking around {mj.get('climaxSec')}s (the money beat), then easing off.",
                  "- The XML puts it on A2 at unity; reapply the arc with keyframes to taste."]
    lines += ["", "## Cuts (master timecode → timeline)", "",
              "| # | Beat | Master in | Master out | Timeline |", "|---|---|---|---|---|"]
    for i, s in enumerate(segs, 1):
        lines.append(f"| {i} | {s.get('beat','')} | {tcf(fr(s['masterIn']))} "
                     f"| {tcf(fr(s['masterIn']) + s['frames'])} | {tcf(s['recIn'])} |")
    (outdir / "README.md").write_text("\n".join(lines) + "\n")

    print(f"[export] {len(segs)} cuts, seq {seq_frames}f ({seq_frames/FPS:.2f}s) -> {outdir}")
    for f in sorted(outdir.iterdir()):
        print(f"   {f.name}  ({f.stat().st_size/1e6:.1f}MB)" if f.stat().st_size > 1e6
              else f"   {f.name}")


if __name__ == "__main__":
    main()
