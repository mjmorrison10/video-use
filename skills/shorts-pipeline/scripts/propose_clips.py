"""Concepts-first workflow: match a client's provided hooks against a transcript and emit a
mechanical proposal draft (per hook: content-match %, true position, clip text with the HOOK
marked, follow-through to a natural sentence end, suggested accents, and adjacency/combo
candidates). Claude then hand-curates the draft (concept summaries, flags, best combos) before
sending it to the client for picks — NO rendering until picks come back.

TurboScribe rule: hook timestamps are segment-start hints (up to ~6 min), so matching is
content-first; when a quote matches multiple regions the one inside [ts, ts+window] wins.

Hooks file: JSON list of {"idx","ts","quote","slug"} (ts = "H:MM:SS" or "MM:SS").

Usage: propose_clips.py TRANSCRIPT.json HOOKS.json -o proposals_draft.md [--window 420]
"""
import argparse, json, os, sys, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from textmatch import tight_match, pick_accents  # noqa  (vendored — self-contained)

MIN_FOLLOW_S, MAX_RAW_S = 18, 60

def ts_to_s(ts):
    p = [int(x) for x in ts.split(":")]
    while len(p) < 3:
        p.insert(0, 0)
    return p[0] * 3600 + p[1] * 60 + p[2]

def fmt(t):
    m, s = divmod(int(t), 60); h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}"

def windowed_match(words, quote, ts_s, win):
    """Prefer the match inside [ts, ts+win]; fall back to whole-transcript."""
    idx = [i for i, x in enumerate(words) if ts_s <= x["start"] <= ts_s + win]
    if idx:
        lo, hi = idx[0], idx[-1]
        m = tight_match(words[lo:hi + 1], quote)
        if m and m[2] / m[3] >= 0.6:
            return lo + m[0], lo + m[1], m[2], m[3]
    return tight_match(words, quote)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript"); ap.add_argument("hooks")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--window", type=float, default=420)
    a = ap.parse_args()
    if tight_match is None:
        sys.exit("match_hook.tight_match unavailable — run where /home/user/video-work is present")
    words = json.load(open(a.transcript))["words"]
    hooks = json.load(open(a.hooks))
    rows = []
    for h in hooks:
        m = windowed_match(words, h["quote"], ts_to_s(h["ts"]), a.window)
        if not m:
            rows.append({**h, "err": "NO MATCH"}); continue
        hs, he, mt, tot = m
        t0 = words[hs]["start"]; cont, j = he, he + 1
        while j < len(words):
            cont = j; el = words[j]["end"] - t0; w = words[j]["word"].strip()
            if (el >= MIN_FOLLOW_S and w.endswith((".", "?", "!"))) or el >= MAX_RAW_S:
                break
            j += 1
        hook_txt = " ".join(w["word"].strip() for w in words[hs:he + 1])
        follow = " ".join(w["word"].strip() for w in words[he + 1:cont + 1])
        rows.append({**h, "cov": mt / tot, "t0": t0, "t1": words[cont]["end"],
                     "hook": hook_txt, "follow": follow,
                     "accents": pick_accents(hook_txt + " " + follow)})
    ok = sorted([r for r in rows if not r.get("err")], key=lambda r: r["t0"])
    combos = [(a_["idx"], b_["idx"], b_["t0"] - a_["t1"])
              for a_, b_ in zip(ok, ok[1:]) if -5 <= b_["t0"] - a_["t1"] <= 75]
    out = [f"# Clip proposal draft ({len(ok)}/{len(hooks)} hooks matched)", "",
           "Mechanical draft — hand-curate before sending (concept summaries, flags, best combos).", ""]
    for r in sorted(rows, key=lambda r: r["idx"]):
        out.append(f"## #{r['idx']} — {r['slug']}  ({r['ts']} stated)")
        if r.get("err"):
            out.append("**NOT FOUND** — needs manual search.\n"); continue
        out.append(f"- {r['cov']:.0%} · pos {fmt(r['t0'])} · ~{r['t1']-r['t0']:.0f}s · accents: {', '.join(r['accents'])}")
        out.append(f"\n**HOOK:** {r['hook']}")
        if r["follow"]:
            out.append(f"\n**THEN:** {r['follow']}")
        out.append("")
    if combos:
        out.append("## Combo candidates (adjacent in source)")
        out += [f"- #{a_} → #{b_}  (gap {g:.0f}s)" for a_, b_, g in combos]
    open(a.out, "w").write("\n".join(out))
    print(f"wrote {a.out} ({len(ok)} matched, {len(combos)} combos)")

if __name__ == "__main__":
    main()
