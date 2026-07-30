"""The ONE place caption display text is produced.

House rule (see /CLAUDE.md): captions NEVER contain punctuation. The rule kept
being lost because each new builder re-implemented token emission and only
build_props.py stripped; now every builder imports these helpers, so the rule
cannot drift again.

Kept characters: apostrophes (DON'T), $ and % (money reads as money), and
asterisked action captions (*NODS YES*) which pass through untouched.
"""
import re

# Punctuation stripped from caption DISPLAY text. Grouping logic may still look
# at the original words to find sentence ends — strip at emission, not before.
_PUNCT_RE = re.compile(r"[.,!?;:\"“”‘’—…()\[\]]")

_ACTION_RE = re.compile(r"^\*.+\*$")


def strip_punct(text: str) -> str:
    """Strip punctuation but PRESERVE surrounding whitespace — transcript words
    carry their own leading space, which is the renderer's token separator."""
    core = text.strip()
    if _ACTION_RE.match(core):       # *NODS YES* — action captions keep their asterisks
        return text
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return lead + _PUNCT_RE.sub("", core) + trail


def clean(s: str) -> str:
    """Lowercased alphanumeric key for word matching (power words, replacements)."""
    return re.sub(r"[^a-z0-9]", "", s.lower()).strip()


def tokens_for_page(texts):
    """Emit caption tokens under the renderer's contract: CaptionPage renders each
    token with whiteSpace:"pre" and supplies no separators, so every token after
    the first carries a leading space. Display text is punctuation-stripped here
    — the single choke point for the house rule."""
    out = []
    for i, t in enumerate(str(x).strip() for x in texts):
        t = strip_punct(t)
        if not t:
            continue
        out.append({"text": t if not out else " " + t})
    return out
