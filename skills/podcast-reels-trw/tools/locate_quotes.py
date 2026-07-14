"""Locate each clip's exact word-boundary [start, end] in the transcript.

Fuzzy-aligns the user's quote text against the Whisper word stream near the
given center timestamp (quotes may not be verbatim), then reports the matched
range + the transcript text it resolved to, so cuts land on word boundaries
(Hard Rule 6/7). Prints a review table; --emit-edl writes a per-clip EDL.
"""
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

TRANSCRIPT = Path("/home/user/claude-video-editor/edit/transcripts/Justin-Waller-vs-Therapist.json")

# (id, center_seconds, quote)
CLIPS = [
    ("hook", 51*60+0,  "Yeah. We're incentivized not to show it. Because? Because that's how it works."),
    ("c12", 87*60+58,  "And it's not an illusion in my mind, because if it was an illusion in my mind, then I wouldn't have the people I have in my life. Yeah."),
    ("c13", 76*60+39,  "That's not going to happen to you. I want to dodge it. I want to dodge it."),
    ("c14", 73*60+26,  "It's when I believe I am abundantly capable of achieving something and I'm not tackling it the way I should. That voice gets loud and yeah, it gets a little rude to say the least."),
    ("c15", 72*60+32,  "It is one of the only things in my life that I do not second guess ever. Ever. It's always me doing more."),
    ("c16", 50*60+40,  "And in part because men aren't necessarily showing it and that's why I think it's important for people to see even for guys like you, even for guys like Andrew. Men are incentivized not to. You guys carry pain."),
    ("c17", 47*60+18,  "But it's in that moment that they realize that you're not backtracking, that I actually think you hook them. I really believe it. I believe that."),
    ("c18", 30*60+47,  "But that's not how this game works, baby. It's not. So sometimes in life, and I think you'll agree with me here, sometimes you just gotta be a big boy and take the licks with the good."),
    ("c19", 23*60+39,  "I am, hey, let's not do it, let's not do it. But if you get in range, I'm going to fucking drop hands on you. Right."),
    ("c20", 15*60+57,  "Show me one thing that a woman has invented, which has led to me getting Instagram messages from women with like these lists. It's a dishwasher, Barbie, Wi-Fi. And I'm just like, the exception is not the rule."),
    ("c21", 1*60+31,   "And I thought it created caricatures of not just the men like yourself and Myron and Sneko, but just of men in general. And I guess I feel pretty passionate about the conversation around men and what's going on."),
    ("c22", 89*60+46,  "You think Louie knows the truth of you? You think he's not thinking. Oh yeah, that's it. Louie knows, you know, I know. I even heard him say it."),
    ("c23", 89*60+46,  "Yeah, in real life. In fact, to this day, my construction and my real estate by a long shot outpace any money I make on the internet. It's not even close."),
    ("c24", 71*60+57,  "And the other stuff is secondary to that. It's so funny. Can I tell you something? I don't think I've ever said this on camera or not."),
    ("c25", 70*60+23,  "But you know what I'm getting at, right, Justin? I mean, you can come to Jesus, but I digress. You know what I'm getting at, right? Because it's a fine line, right?"),
    ("c26", 53*60+46,  "When did it start, do you think? Because I have a feeling this pain of not being seen, like, in your goodness, recognized. Or accepted."),
    ("c27", 43*60+38,  "I did one session with them, and I said, this isn't for me. I'm not saying therapy's bullshit, it wasn't for me. Why, what happened?"),
    ("c28", 42*60+54,  "It's like the Lila Rose lady, she's like, well you're disciplined here and here and here, why can't you be disciplined? I'm like, whoa, whoa, whoa, it's not about discipline."),
    ("c29", 69*60+56,  "It's not that I'm not enough."),
    ("c31", 22*60+18,  "It's funny. I know he's incredibly proud. Does he tell you? Not directly."),
    ("c30", 51*60+0,   "We're incentivized not to show it. Because? Because that's how it works."),
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9' ]", " ", s.lower()).split() and " ".join(re.sub(r"[^a-z0-9' ]", " ", s.lower()).split()) or ""


def tok(s: str):
    return re.sub(r"[^a-z0-9']", " ", s.lower()).split()


def hms(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def locate(words, center, quote, win=70.0, pad_pre=0.06, pad_post=0.10):
    # window words
    ww = [w for w in words if w.get("type") == "word" and w.get("start") is not None
          and center - win <= w["start"] <= center + win]
    if not ww:
        return None
    trans_tokens = [tok(w["text"])[0] if tok(w["text"]) else "" for w in ww]
    qtokens = tok(quote)
    sm = SequenceMatcher(None, trans_tokens, qtokens, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None
    a_start = blocks[0].a
    a_end = blocks[-1].a + blocks[-1].size  # exclusive
    matched = ww[a_start:a_end]
    if not matched:
        return None
    start = matched[0]["start"] - pad_pre
    end = matched[-1]["end"] + pad_post
    matched_ratio = sum(b.size for b in blocks) / max(1, len(qtokens))
    text = " ".join(w["text"] for w in matched)
    return {
        "start": round(max(0.0, start), 3),
        "end": round(end, 3),
        "dur": round(end - start, 3),
        "match_ratio": round(matched_ratio, 2),
        "text": text,
    }


def locate_global(words, quote, pad_pre=0.06, pad_post=0.10):
    """Find the best fuzzy match for `quote` ANYWHERE in the transcript.

    For drifted clips whose given timestamp is wrong. Anchors candidate windows
    at occurrences of the quote's longest content words, scores each with
    SequenceMatcher, returns the best word-boundary range.
    """
    ww = [w for w in words if w.get("type") == "word" and w.get("start") is not None]
    trans_tokens = [tok(w["text"])[0] if tok(w["text"]) else "" for w in ww]
    qtokens = tok(quote)
    if not qtokens:
        return None
    qlen = len(qtokens)
    # anchor tokens = the longest content words in the quote
    content = sorted(set(t for t in qtokens if len(t) >= 5), key=len, reverse=True)[:4]
    anchor_set = set(content) if content else set(qtokens)
    cand_idx = [i for i, t in enumerate(trans_tokens) if t in anchor_set]
    if not cand_idx:
        cand_idx = list(range(0, len(trans_tokens), max(1, qlen // 2)))

    best = None
    seen_windows = set()
    for ci in cand_idx:
        lo = max(0, ci - qlen)
        if lo in seen_windows:
            continue
        seen_windows.add(lo)
        hi = min(len(ww), lo + int(qlen * 2.2) + 4)
        window = trans_tokens[lo:hi]
        sm = SequenceMatcher(None, window, qtokens, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
        if not blocks:
            continue
        ratio = sum(b.size for b in blocks) / qlen
        a0 = lo + blocks[0].a
        a1 = lo + blocks[-1].a + blocks[-1].size
        if best is None or ratio > best["match_ratio"]:
            matched = ww[a0:a1]
            if not matched:
                continue
            best = {
                "start": round(max(0.0, matched[0]["start"] - pad_pre), 3),
                "end": round(matched[-1]["end"] + pad_post, 3),
                "dur": round(matched[-1]["end"] - matched[0]["start"], 3),
                "match_ratio": round(ratio, 2),
                "text": " ".join(w["text"] for w in matched),
            }
    return best


def locate_turboscribe(words, t_start, quote, window=420.0, pad_pre=0.06, pad_post=0.10,
                       min_ratio=0.55):
    """TRW: TurboScribe timestamps mark the START of a large (~6min) segment, so
    several different hooks can all read the same `t_start`. Treat `t_start` as a
    window hint, not a location: search by CONTENT inside `[t_start, t_start+window]`
    first; if nothing clears `min_ratio`, fall back to a global fuzzy match so a
    badly-drifted timestamp still resolves.

    Returns the located range dict (same schema as `locate`), plus a `via` field
    telling you whether it hit inside the window or fell back to global.
    """
    ww = [w for w in words if w.get("type") == "word" and w.get("start") is not None
          and t_start - 2.0 <= w["start"] <= t_start + window]
    best = None
    if ww:
        trans_tokens = [tok(w["text"])[0] if tok(w["text"]) else "" for w in ww]
        qtokens = tok(quote)
        if qtokens:
            qlen = len(qtokens)
            content = sorted(set(t for t in qtokens if len(t) >= 5), key=len, reverse=True)[:4]
            anchor_set = set(content) if content else set(qtokens)
            cand_idx = [i for i, t in enumerate(trans_tokens) if t in anchor_set]
            if not cand_idx:
                cand_idx = list(range(0, len(trans_tokens), max(1, qlen // 2)))
            seen = set()
            for ci in cand_idx:
                lo = max(0, ci - qlen)
                if lo in seen:
                    continue
                seen.add(lo)
                hi = min(len(ww), lo + int(qlen * 2.2) + 4)
                sm = SequenceMatcher(None, trans_tokens[lo:hi], qtokens, autojunk=False)
                blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
                if not blocks:
                    continue
                ratio = sum(b.size for b in blocks) / qlen
                if best is None or ratio > best["match_ratio"]:
                    matched = ww[lo + blocks[0].a: lo + blocks[-1].a + blocks[-1].size]
                    if not matched:
                        continue
                    best = {
                        "start": round(max(0.0, matched[0]["start"] - pad_pre), 3),
                        "end": round(matched[-1]["end"] + pad_post, 3),
                        "dur": round(matched[-1]["end"] - matched[0]["start"], 3),
                        "match_ratio": round(ratio, 2),
                        "text": " ".join(w["text"] for w in matched),
                        "via": "window",
                    }
    if best is not None and best["match_ratio"] >= min_ratio:
        return best
    g = locate_global(words, quote, pad_pre=pad_pre, pad_post=pad_post)
    if g is not None:
        g["via"] = "global"
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcript", type=Path, default=TRANSCRIPT)
    ap.add_argument("--only", default=None, help="comma-separated clip ids")
    args = ap.parse_args()

    data = json.loads(args.transcript.read_text())
    words = data["words"]
    only = set(args.only.split(",")) if args.only else None

    for cid, center, quote in CLIPS:
        if only and cid not in only:
            continue
        r = locate(words, center, quote)
        print(f"\n=== {cid}  (center {hms(center)}) ===")
        if not r:
            print("  NO MATCH in window — needs manual check")
            continue
        print(f"  range: {r['start']:.2f}..{r['end']:.2f}  ({r['dur']:.1f}s)  match={r['match_ratio']}")
        print(f"  [{hms(r['start'])} -> {hms(r['end'])}]")
        print(f"  transcript: {r['text']}")


if __name__ == "__main__":
    main()
