#!/usr/bin/env python3
"""Print words with start/end in a time window, for authoring word-boundary cuts.
Usage: words_in.py START END   (seconds)   [--grep substr]"""
import json, sys
d = json.load(open('/home/user/videos/jackkneel/edit/transcript_full.json'))
ws = d['words']
a, b = float(sys.argv[1]), float(sys.argv[2])
grep = None
if '--grep' in sys.argv:
    grep = sys.argv[sys.argv.index('--grep') + 1].lower()
for w in ws:
    if w['start'] < a or w['start'] >= b:
        continue
    t = w['text'].strip()
    mark = ' <<<' if (grep and grep in t.lower()) else ''
    print(f"{w['start']:8.2f} {w['end']:8.2f}  {t}{mark}")
