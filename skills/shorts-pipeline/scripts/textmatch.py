"""Hook-locating + accent-picking — the judgment-support helpers used by the concepts-first
workflow and the clip builder. Vendored into the repo (previously lived in the ephemeral
/home/user/video-work) so a fresh clone reproduces identical results.

- tight_match(words, quote): align a (possibly paraphrased) hook quote against transcript word
  tokens with difflib and return the tight [start,end] word span. Chains matching blocks that
  are contiguous IN THE TRANSCRIPT (gap_b <= max_gap_b), grown from the largest block; quote-side
  gaps are NOT gated (hook quotes are lightly paraphrased). This is what stops a phrase that
  repeats elsewhere from dragging the span far past the real quote.
- pick_accents(text): choose caption power-words (yellow), filtering stop/filler/contractions.
"""
import re, difflib

def norm1(t):
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()

def tight_match(words, quote, max_gap_b=14):
    wtok = [norm1(w["word"]) for w in words]
    qtok = [t for t in norm1(quote).split(" ") if t]
    sm = difflib.SequenceMatcher(a=qtok, b=wtok, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size > 0]
    if not blocks:
        return None
    blocks.sort(key=lambda b: b.b)
    anchor_i = max(range(len(blocks)), key=lambda i: blocks[i].size)
    chain = [blocks[anchor_i]]
    i = anchor_i - 1
    while i >= 0:
        gap_b = chain[0].b - (blocks[i].b + blocks[i].size)
        if gap_b > max_gap_b or blocks[i].a >= chain[0].a:
            break
        chain.insert(0, blocks[i]); i -= 1
    i = anchor_i + 1
    while i < len(blocks):
        gap_b = blocks[i].b - (chain[-1].b + chain[-1].size)
        if gap_b > max_gap_b or blocks[i].a <= chain[-1].a:
            break
        chain.append(blocks[i]); i += 1
    start = chain[0].b
    end = chain[-1].b + chain[-1].size - 1
    matched = sum(b.size for b in chain)
    return start, end, matched, len(qtok)

STOP = set("""a an the and or but so if is are was were be been being to of in on at for with as by
from this that these those it its it's i i'm im you your you're youre we we're were re he he's she
she's they they're theyre not no do does did doing done just like right yeah okay ok well because
me my mine our us them their there here what who how when where why which than then now get got
going go know think believe feel really actually literally kind sort thing things stuff um uh huh
hey right somebody someone something sometimes probably currently example always still every still
amount number watch lower still yknow gonna wanna gotta little bit lot much many more most also even
maybe basically honestly obviously totally pretty quite rather said says saying tell telling told
came come coming look looking looked make making made take taking took give giving gave put putting
around back down over under again ever never able""".split())

CURSE = {"fucking", "fuck", "shit", "bullshit", "ass", "damn", "hell"}

def pick_accents(text, n=6):
    toks = re.findall(r"[A-Za-z']+", text)
    seen, cands = set(), []
    for t in toks:
        tl = t.lower().strip("'")
        if "'" in t or tl in STOP or len(tl) < 4 or tl in seen or tl in ("about", "getting", "cause", "because"):
            continue
        seen.add(tl)
        weight = len(tl) + (5 if tl in CURSE else 0)
        cands.append((weight, t.upper().strip("'")))
    cands.sort(key=lambda x: -x[0])
    return [c[1] for c in cands[:n]]
