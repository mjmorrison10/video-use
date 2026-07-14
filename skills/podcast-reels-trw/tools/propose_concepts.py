"""CONCEPTS-FIRST hook mining for TRW.

The TRW workflow never jumps straight to building. It transcribes, then mines
EVERY viable hook from the transcript, writes a ranked `CONCEPTS.md`, and sends
it to the user to select from. Only the selected concepts get built.

This module is the plumbing for that step. The actual mining is a Workflow
fan-out of analyst agents (one per overlapping transcript window) — this file:

  1. `make_windows()` — cut the transcript into overlapping, timestamped text
     windows small enough for one analyst agent to read closely.
  2. `window_prompt()` — the exact instruction each analyst gets (mine hooks:
     punchy, quotable, curiosity-gap opening lines + the point each develops).
  3. `merge_concepts()` — dedup across windows (same hook found in two
     overlapping windows), keep the best-scored copy, sort by virality.
  4. `write_concepts_md()` — render the ranked list to `CONCEPTS.md` in the
     TRW selection format, including `pairs-with` so multi-hook combos are
     visible at selection time.

Driver (run from a Workflow script), sketch:

    import propose_concepts as PC
    words = json.load(open(transcript))["words"]
    wins = PC.make_windows(words, win=210, overlap=40)
    # fan out: one agent per window, each returns {"hooks":[...]} per HOOK_SCHEMA
    results = await parallel([lambda w=w: agent(PC.window_prompt(w), schema=PC.HOOK_SCHEMA)
                              for w in wins])
    concepts = PC.merge_concepts([h for r in results if r for h in r["hooks"]])
    PC.write_concepts_md(concepts, "edit/CONCEPTS.md")

Then send CONCEPTS.md to the user; build only what they pick.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path


def hms(t: float) -> str:
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
    return f"{h}:{m:02d}:{s:02d}"


def _toks(s: str):
    return re.sub(r"[^a-z0-9']", " ", (s or "").lower()).split()


# ---------------------------------------------------------------------------
# 1. Windows — overlapping so a hook near a boundary is fully inside one window.
# ---------------------------------------------------------------------------

def make_windows(words, win=210.0, overlap=40.0):
    """Slice the word stream into overlapping [start,end] windows of ~`win`
    seconds. Each window carries a compact timestamped transcript so an analyst
    can quote a hook line verbatim and give its real timestamp.

    Returns a list of dicts: {"idx","start","end","transcript"}.
    """
    ws = [w for w in words if w.get("type") == "word" and w.get("start") is not None]
    if not ws:
        return []
    t0 = ws[0]["start"]
    t_end = ws[-1]["end"]
    step = max(1.0, win - overlap)
    windows = []
    idx = 0
    s = t0
    while s < t_end:
        e = s + win
        seg = [w for w in ws if w["start"] >= s and w["start"] < e]
        if seg:
            windows.append({
                "idx": idx,
                "start": round(seg[0]["start"], 2),
                "end": round(seg[-1]["end"], 2),
                "transcript": _timestamped_text(seg),
            })
            idx += 1
        s += step
    return windows


def _timestamped_text(seg, line_gap=2.0):
    """Render words as `[H:MM:SS] text ...` lines, breaking on speech gaps so the
    analyst can see natural sentence/turn boundaries and cite timestamps."""
    lines = []
    cur = []
    line_start = seg[0]["start"]
    prev = seg[0]["end"]
    for w in seg:
        if w["start"] - prev > line_gap and cur:
            lines.append(f"[{hms(line_start)}] " + " ".join(cur))
            cur = []
            line_start = w["start"]
        cur.append((w.get("text") or "").strip())
        prev = w["end"]
    if cur:
        lines.append(f"[{hms(line_start)}] " + " ".join(cur))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. Analyst prompt + output schema (used by the Workflow fan-out).
# ---------------------------------------------------------------------------

HOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "hooks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hook": {"type": "string",
                             "description": "The verbatim opening line, exactly as spoken."},
                    "timestamp": {"type": "string",
                                  "description": "H:MM:SS where the hook line begins."},
                    "start_s": {"type": "number",
                                "description": "The hook's start time in seconds."},
                    "story": {"type": "string",
                              "description": "One line: the single point this hook opens into."},
                    "suggested_len_s": {"type": "integer",
                                        "description": "Target finished length, 15-45."},
                    "virality": {"type": "integer",
                                 "description": "1-100 potential; be discriminating."},
                    "rationale": {"type": "string",
                                  "description": "Why it hooks (curiosity gap, contrarian, stakes)."},
                    "pairs_with": {"type": "string",
                                   "description": "Verbatim hook of a nearby line this chains with (hook1->hook2), or empty."},
                },
                "required": ["hook", "timestamp", "start_s", "story",
                             "suggested_len_s", "virality", "rationale"],
            },
        }
    },
    "required": ["hooks"],
}


def window_prompt(window: dict) -> str:
    return f"""You are an elite short-form editor mining a podcast transcript for TRW
(The Real World) social clips. Below is a ~{int(window['end'] - window['start'])}s
window of ONE long interview, timestamped.

Find EVERY line that could OPEN a viral vertical clip — a hook. A hook is a
punchy, quotable, curiosity-gap or contrarian opening line that makes a scroller
stop. Be generous: surface every candidate, not just the best one. For each hook,
identify the ONE point it develops (the story that would follow it) and how long
the finished clip should be (15-45s).

A hook in TRW style:
- lands in the first line (something bold, contrarian, or opening a curiosity gap),
- opens into ONE clear point that pays off,
- ends on a beat that LANDS (a button / mic-drop), never mid-tangent.

Also note when a hook naturally CHAINS with another nearby line: hook1 -> point A
-> hook2 -> point B, where point B complements A. If so, put the second hook's
verbatim text in `pairs_with` (these become one chained video).

Quote hook lines VERBATIM and give the real [H:MM:SS] you see in the text. Score
`virality` 1-100 and be discriminating — most lines are not hooks.

WINDOW [{hms(window['start'])} - {hms(window['end'])}]:
{window['transcript']}
"""


# ---------------------------------------------------------------------------
# 3. Merge / dedup across overlapping windows.
# ---------------------------------------------------------------------------

def _same_hook(a, b, thresh=0.72):
    ta, tb = _toks(a["hook"]), _toks(b["hook"])
    if not ta or not tb:
        return False
    close_time = abs(a.get("start_s", 0) - b.get("start_s", 0)) < 25.0
    ratio = SequenceMatcher(None, ta, tb, autojunk=False).ratio()
    return ratio >= thresh and close_time


def merge_concepts(hooks):
    """Dedup hooks found in more than one overlapping window (keep the
    higher-virality copy), then sort by virality descending."""
    kept = []
    for h in hooks:
        if not h.get("hook"):
            continue
        dup = next((k for k in kept if _same_hook(h, k)), None)
        if dup is None:
            kept.append(dict(h))
        elif h.get("virality", 0) > dup.get("virality", 0):
            kept[kept.index(dup)] = dict(h)
    kept.sort(key=lambda x: x.get("virality", 0), reverse=True)
    return kept


# ---------------------------------------------------------------------------
# 4. Render CONCEPTS.md (the selection sheet sent to the user).
# ---------------------------------------------------------------------------

def _pairs_index(concepts):
    """Map each concept index -> the 1-based number of the concept it pairs with
    (matched by fuzzy hook text), so CONCEPTS.md can show `pairs-with #N`."""
    out = {}
    for i, c in enumerate(concepts):
        pw = (c.get("pairs_with") or "").strip()
        if not pw:
            continue
        pwt = _toks(pw)
        best, bj = 0.0, None
        for j, other in enumerate(concepts):
            if j == i:
                continue
            r = SequenceMatcher(None, pwt, _toks(other["hook"]), autojunk=False).ratio()
            if r > best:
                best, bj = r, j
        if bj is not None and best >= 0.6:
            out[i] = bj + 1
    return out


def write_concepts_md(concepts, out_path, title="TRW clip concepts"):
    """Write the ranked selection sheet. Format per entry:

    `#N  [H:MM:SS]  "hook line"  — story — ~Ns — (pairs-with #M)`
    """
    pairs = _pairs_index(concepts)
    lines = [
        f"# {title}",
        "",
        f"{len(concepts)} hooks found, ranked by virality potential. "
        "Reply with the numbers to build "
        '(e.g. "3, 7, 12+13 combined" — combined = one chained video).',
        "",
    ]
    for i, c in enumerate(concepts):
        n = i + 1
        ts = c.get("timestamp") or hms(c.get("start_s", 0))
        hook = (c.get("hook") or "").strip().strip('"')
        story = (c.get("story") or "").strip()
        length = c.get("suggested_len_s", 25)
        vir = c.get("virality", 0)
        pw = f"  — (pairs-with #{pairs[i]})" if i in pairs else ""
        lines.append(f'#{n}  [{ts}]  ({vir})  "{hook}"')
        lines.append(f"      — {story} — ~{length}s{pw}")
        if c.get("rationale"):
            lines.append(f"      · {c['rationale'].strip()}")
        lines.append("")
    Path(out_path).write_text("\n".join(lines))
    print(f"wrote {out_path}: {len(concepts)} concepts")
    return out_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build analyst windows from a transcript "
                                             "(the fan-out itself runs in a Workflow).")
    ap.add_argument("transcript", type=Path)
    ap.add_argument("--win", type=float, default=210.0)
    ap.add_argument("--overlap", type=float, default=40.0)
    args = ap.parse_args()
    words = json.loads(args.transcript.read_text())["words"]
    wins = make_windows(words, win=args.win, overlap=args.overlap)
    print(f"{len(wins)} windows from {args.transcript.name}")
    for w in wins[:2]:
        print(f"\n--- window {w['idx']} [{hms(w['start'])}-{hms(w['end'])}] ---")
        print(w["transcript"][:400], "...")
