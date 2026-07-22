#!/usr/bin/env python3
"""Inject post-build features into specific clip job JSONs:
  - jk_5amraid: bang-zoom punch-ins on each 'bang' word + CTA end card
  - jk_dubai: vertical Dubai B-roll cutaway on the word 'Dubai'
Run AFTER the base pipeline builds each job.json, then re-render those clips.
"""
import json, re

def words_with_time(d):
    out=[]
    for p in d["captionPages"]:
        for t in p["tokens"]:
            out.append((t["text"], p["startMs"]/1000.0))
    return out

# ---- 5amraid: zooms on every 'bang' + CTA ----
p="jobs/jk_5amraid.json"
d=json.load(open(p))
bang_times=[]
seen=set()
for txt,ts in words_with_time(d):
    if re.sub(r"[^a-z]","",txt.lower())=="bang":
        k=round(ts,2)
        if k not in seen: seen.add(k); bang_times.append(k)
d["zooms"]=[{"atSec":round(t-0.03,2),"durSec":0.4,"scale":1.16} for t in bang_times]
d["cta"]={"text":"COMMENT “AIKIDO”","sub":"for part 2 of the story","durSec":2.0}
json.dump(d,open(p,"w"),ensure_ascii=False,indent=1)
print(f"[5amraid] {len(bang_times)} bang-zooms at {bang_times} + CTA card")

# ---- dubai: vertical Dubai B-roll on 'Dubai' ----
p="jobs/jk_dubai.json"
d=json.load(open(p))
at=None
for txt,ts in words_with_time(d):
    if "dubai" in txt.lower(): at=ts; break
if at is not None:
    d["broll"]=[{"src":"broll_dubai.mp4","atSec":round(at-0.1,2),"durSec":1.9,"trimBefore":0.0,"framing":"cover","label":"Dubai"}]
    json.dump(d,open(p,"w"),ensure_ascii=False,indent=1)
    print(f"[dubai] vertical B-roll at {round(at-0.1,2)}s")
else:
    print("[dubai] 'Dubai' word not found")
