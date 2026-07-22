#!/usr/bin/env python3
"""Re-transcribe each clip's window with large-v3 (max accuracy) and splice the
accurate words into the transcript (replacing turbo words in those time ranges)."""
import json, glob, sys
from pathlib import Path
from faster_whisper import WhisperModel, decode_audio

SR=16000
audio=decode_audio("audio.wav",sampling_rate=SR)
# gather windows from current cutspecs (+/- 4s padding for context/accuracy)
wins=[]
for f in glob.glob("/home/user/video-use/remotion-shorts/jobs/jk_*.cutspec.json"):
    segs=json.load(open(f))["segments"]
    lo=min(s["inSec"] for s in segs)-4; hi=max(s["outSec"] for s in segs)+4
    wins.append([max(0,lo),hi,Path(f).stem])
wins.sort()
# merge overlaps
merged=[]
for w in wins:
    if merged and w[0]<=merged[-1][1]+1:
        merged[-1][1]=max(merged[-1][1],w[1]); merged[-1][2]+=","+w[2]
    else: merged.append(w[:])
print(f"[hd] {len(merged)} merged windows to transcribe",flush=True)
model=WhisperModel("large-v3",device="cpu",compute_type="int8",cpu_threads=4)
new_words=[]
covered=[]
for i,(lo,hi,names) in enumerate(merged):
    a=audio[int(lo*SR):int(hi*SR)]
    segs,_=model.transcribe(a,language="en",word_timestamps=True,beam_size=5,
                            vad_filter=True,condition_on_previous_text=False)
    n=0
    for s in segs:
        for w in (s.words or []):
            ws,we=lo+w.start,lo+w.end
            if ws<lo or ws>=hi: continue
            new_words.append({"text":w.word,"start":round(ws,3),"end":round(we,3),
                              "type":"word","speaker_id":"speaker_0"}); n+=1
    covered.append((lo,hi)); print(f"[hd] {i+1}/{len(merged)} [{lo:.0f}-{hi:.0f}]s {names[:40]} -> {n} words",flush=True)
# splice: drop old words inside covered windows, add new
tr=json.load(open("edit/transcript.json"))
def inwin(t): return any(lo<=t<hi for lo,hi in covered)
kept=[w for w in tr["words"] if not inwin(w["start"])]
allw=sorted(kept+new_words,key=lambda w:w["start"])
tr["words"]=allw
json.dump(tr,open("edit/transcript_hd.json","w"),ensure_ascii=False,indent=1)
print(f"[hd] DONE: spliced {len(new_words)} accurate words -> edit/transcript_hd.json ({len(allw)} total)",flush=True)
