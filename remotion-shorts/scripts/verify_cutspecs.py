#!/usr/bin/env python3
"""Print the actual transcript text each cutspec segment spans, for QA."""
import json, glob, sys
from pathlib import Path

TR = json.load(open('/home/user/videos/jackkneel/edit/transcript_full.json'))
WORDS = [w for w in TR['words'] if w.get('start') is not None]


def text_in(a, b):
    return " ".join(w['text'].strip() for w in WORDS if a <= w['start'] < b)


names = sys.argv[1:] or [Path(f).name.replace('.cutspec.json', '')
                         for f in sorted(glob.glob('/home/user/video-use/remotion-shorts/jobs/jk2_*.cutspec.json'))
                         if '.snap.' not in f]
for name in names:
    p = Path('/home/user/video-use/remotion-shorts/jobs') / f"{name}.cutspec.json"
    spec = json.load(open(p))
    total = sum(s['outSec'] - s['inSec'] for s in spec['segments'])
    print(f"\n{'='*90}\n{name}   ({len(spec['segments'])} segs, {total:.1f}s)   HOOK: {spec['hook']['text']}")
    for s in spec['segments']:
        beat = s.get('beat', '?')
        txt = text_in(s['inSec'], s['outSec'])
        flag = '' if txt.strip() else '  <<< EMPTY!'
        print(f"  [{s['inSec']:8.2f}-{s['outSec']:8.2f}] {beat:8s} {txt}{flag}")
