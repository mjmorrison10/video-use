#!/usr/bin/env python3
"""Assemble the "Stand Up For Tate" job: VO bookends around a face-tracked cut.

Unlike the other builders, this video has three sources of truth on one
timeline:

  * two narration stems (edge-tts) that own the head and tail, over B-roll,
  * a face-tracked lecture cut whose ranges are in MASTER time and have to be
    laid end-to-end on the OUTPUT timeline,
  * captions for both, which therefore come from two different word streams.

Everything downstream keys off `offsetSec`, so the one thing this script must
get exactly right is the master->output mapping; captions are derived from it
rather than being timed independently.

Usage: build_standup_job.py --tracked T.json --words W.json
                            --vo-intro A.json --vo-close B.json -o job.json
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from caption_text import clean, tokens_for_page  # noqa: E402

# Lit in cyan. The spine of the argument only — justice/injustice, the silence,
# and the duty. Lighting every noun would flatten the ones that matter.
POWER = ["injustice", "justice", "protest", "unfair", "anything", "affected",
         "nobody", "citizen", "guilty", "death", "silent", "tate"]

MAX_CHARS = 26          # a caption page must read in one glance on a phone
MAX_WORDS = 4
PAGE_GAP = 0.42         # a pause this long ends the page regardless of length
CUT_GAP = 0.30          # master-time jump this big means the audio was cut here


def _mk(cur):
    return {
        "startMs": round(cur[0]["out_s"] * 1000),
        "endMs": round(cur[-1]["out_e"] * 1000),
        "tokens": tokens_for_page(x["text"] for x in cur),
    }


def pages(words):
    """Group an output-timed word stream into caption pages.

    Breaks on sentence punctuation and real pauses before length — phrase-level
    pages read better than fixed word counts (the lesson from the hand-fixed
    TRW859 captions). A trailing comma only ends a page that already has words
    in it, so a lone connective never becomes its own card."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt["out_s"] - w["out_e"]) if nxt else 99
        # the audio itself was spliced here — the page must not straddle the cut
        cut = nxt is not None and (nxt["src_s"] - w["src_e"]) >= CUT_GAP
        txt = "".join(x["text"] for x in cur).strip()
        t = w["text"].strip()
        if (t.endswith((".", "?", "!"))
                or (t.endswith((",", ";", ":")) and len(cur) >= 2)
                or gap >= PAGE_GAP or cut
                or len(txt) >= MAX_CHARS or len(cur) >= MAX_WORDS
                or nxt is None):
            pg = _mk(cur)
            if cut:
                pg["_cut"] = True   # audio splice here: nothing may fold across it
            out.append(pg); cur = []

    # Fold a one-word orphan back into the page before it — a single word
    # flashing alone reads as a glitch, not emphasis.
    merged = []
    for p in out:
        if (merged and len(p["tokens"]) == 1 and not merged[-1].get("_cut")
                and p["startMs"] - merged[-1]["endMs"] <= PAGE_GAP * 1000
                and sum(len(t["text"]) for t in merged[-1]["tokens"] + p["tokens"]) <= MAX_CHARS + 8):
            # tokens carry their own separator, so the folded-in word needs one
            merged[-1]["tokens"] += [{"text": " " + p["tokens"][0]["text"].lstrip()}]
            merged[-1]["endMs"] = p["endMs"]
        else:
            merged.append(p)
    for p in merged:
        p.pop("_cut", None)
    return merged


def map_words(master, ranges, tracked):
    """Move master-timeline words onto the output timeline.

    A word counts as belonging to a range when enough of it actually plays
    there. Requiring the word's nominal START to fall inside would both keep
    words whose audio was cut away (a trailing "thank" that never sounds) and
    drop words Whisper dated early — it puts "if" at 142.14 when the speaker
    says it at 142.84, so a range starting at 142.78 would caption
    "you don't help bring about justice" over audio that says "if you don't"."""
    out, seen = [], set()
    for s, r in zip(tracked, ranges):
        d = r["offsetSec"] - r["inSec"]
        for i, w in enumerate(master):
            ov = min(w["end"], r["outSec"]) - max(w["start"], r["inSec"])
            if ov <= 0 or i in seen:
                continue
            if ov < min(0.5 * (w["end"] - w["start"]), 0.25):
                continue
            seen.add(i)
            # Clamp into the range's own output span. Whisper's extents spill
            # past both ends of a tight cut, and an unclamped word lands outside
            # the range it belongs to — interleaving with a neighbouring beat
            # and captioning a word seconds before it is spoken.
            lo, hi = r["offsetSec"], r["offsetSec"] + (r["outSec"] - r["inSec"])
            out.append({"text": w["text"], "src_s": w["start"], "src_e": w["end"],
                        "out_s": min(max(w["start"] + d, lo), hi),
                        "out_e": min(max(w["end"] + d, lo), hi)})
    out.sort(key=lambda w: w["out_s"])
    return out


def vo_words(vo, shift):
    return [{"text": w["text"], "src_s": w["start"], "src_e": w["end"],
             "out_s": w["start"] + shift, "out_e": w["end"] + shift} for w in vo["words"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracked", required=True, help="face-tracked cutspec (master time)")
    ap.add_argument("--words", required=True, help="master word-level transcript")
    ap.add_argument("--vo-intro", required=True); ap.add_argument("--vo-close", required=True)
    ap.add_argument("--video", default="standup_src.mp4")
    ap.add_argument("--broll-intro", default="standup_ph_intro.mp4")
    ap.add_argument("--broll-close", default="standup_ph_close.mp4")
    ap.add_argument("--vo-intro-src", default="standup_vo_intro.wav")
    ap.add_argument("--vo-close-src", default="standup_vo_close.wav")
    ap.add_argument("--music", default=None); ap.add_argument("--music-start", type=float, default=0.0)
    ap.add_argument("--vol-low", type=float, default=0.045)
    ap.add_argument("--vol-high", type=float, default=0.085)
    ap.add_argument("--hold", type=float, default=1.8, help="end card duration")
    ap.add_argument("--close-gap", type=float, default=0.0,
                    help="beat of B-roll before the closing narration starts")
    ap.add_argument("--cta-text", default=None,
                    help="end card; omit — the house style ends on the speaker")
    ap.add_argument("--cta-line", action="append", default=[])
    ap.add_argument("--title-line", action="append", default=[],
                    help="title line over the opening; last line takes the accent")
    ap.add_argument("--title-until", type=float, default=2.5)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    tracked = json.load(open(a.tracked))["segments"]
    master = json.load(open(a.words))["words"]
    vo_in = json.load(open(a.vo_intro)); vo_out = json.load(open(a.vo_close))

    intro_d, close_d = vo_in["durSec"], vo_out["durSec"]

    # --- lay the lecture ranges end-to-end after the intro VO ---
    ranges, t = [], intro_d
    for s in tracked:
        dur = s["outSec"] - s["inSec"]
        r = {"inSec": round(s["inSec"], 3), "outSec": round(s["outSec"], 3),
             "offsetSec": round(t, 3), "framing": "cover",
             "cropX": s.get("cropX", 0.5), "cropXEnd": s.get("cropXEnd"),
             "cropPanSec": s.get("cropPanSec"), "mute": False,
             "beat": s.get("beat", "POINT")}
        ranges.append(r); t += dur
    lecture_end = t
    # The closing B-roll starts on the cut, but the narrator waits a beat: the
    # professor's last line needs to decay before another voice arrives, and
    # holding on picture rather than black keeps the gap from reading as a stall.
    close_at = lecture_end + a.close_gap
    cta_at = close_at + close_d
    total = cta_at + (a.hold if a.cta_text else 0.0)

    # --- captions ---
    lecture = map_words(master, ranges, tracked)
    caps = (pages(vo_words(vo_in, 0.0)) + pages(lecture)
            + pages(vo_words(vo_out, close_at)))
    caps.sort(key=lambda p: p["startMs"])
    overlaps = [(a, b) for a, b in zip(caps, caps[1:]) if b["startMs"] < a["startMs"]]
    assert not overlaps, f"caption pages out of order: {overlaps[0]}"

    # a page must never outlive the section it belongs to
    for p in caps:
        p["endMs"] = min(p["endMs"], round(total * 1000))

    job = {
        "videoSrc": a.video, "fps": a.fps, "ranges": ranges, "captionPages": caps,
        # The bed is loudest under the narration (no competing dialogue) and
        # drops for the body. climaxSec at the intro makes the arc high->low
        # instead of swelling into the speech.
        "music": ({"src": a.music, "startSec": a.music_start, "volLow": a.vol_low,
                   "volHigh": a.vol_high, "climaxSec": round(intro_d * 0.5, 2)}
                  if a.music else None),
        "style": {"highlightColor": "#13FFFF", "accentColor": "#13FFFF",
                  "textColor": "white", "strokeColor": "black", "fontSize": 48,
                  "captionPosition": "center", "captionBottom": 420,
                  "uppercase": True, "powerWords": POWER},
        "hook": None,
        "title": ({"lines": a.title_line, "untilSec": a.title_until, "fontSize": 55}
                  if a.title_line else None),
        # The bookends are B-roll over black: no range plays there, so these
        # cutaways ARE the picture for those sections.
        "broll": [
            {"src": a.broll_intro, "atSec": 0.0, "durSec": round(intro_d, 3),
             "trimBefore": 0.0, "framing": "letterbox", "label": "VO INTRO"},
            {"src": a.broll_close, "atSec": round(lecture_end, 3),
             "durSec": round(close_d + a.close_gap, 3),
             "trimBefore": 0.0, "framing": "letterbox", "label": "VO CLOSE"},
        ],
        "zooms": [], "zoomSteps": [],
        "voiceovers": [
            {"src": a.vo_intro_src, "atSec": 0.0, "volume": 1.0},
            {"src": a.vo_close_src, "atSec": round(close_at, 3), "volume": 1.0},
        ],
        "cta": ({"text": a.cta_text, "durSec": a.hold, "atSec": round(cta_at, 3),
                 "lines": a.cta_line} if a.cta_text else None),
        "durationSec": round(total, 3),
    }
    Path(a.out).write_text(json.dumps(job, ensure_ascii=False, indent=1))

    lit = sum(1 for p in caps for tk in p["tokens"] if clean(tk["text"]) in set(POWER))
    print(f"[standup] intro VO 0-{intro_d:.2f}  lecture {intro_d:.2f}-{lecture_end:.2f} "
          f"({len(ranges)} ranges)  close VO {close_at:.2f}-{cta_at:.2f}  "
          f"card {cta_at:.2f}-{total:.2f}")
    print(f"[standup] {len(caps)} caption pages, {lit} power words lit -> {a.out}")
    if total > 60:
        print(f"[standup] WARNING: {total:.2f}s exceeds the 60s limit")


if __name__ == "__main__":
    main()
