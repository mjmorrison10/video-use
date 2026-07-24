#!/usr/bin/env python3
"""Snap cut-spec boundaries into SILENCE (cut dead space, never a word). Gap-aware:
lands the pad inside a real pause; if a word butts against its neighbor, cuts in the
micro-gap between them (never overshoots into the neighbor). Merges mid-speech splits
so audio stays whole. Optional --plot writes a waveform PNG (green=kept, red line=cut).
"""
import json, sys, wave, numpy as np
WAV="audio.wav"; SR=16000; HOP=160; WIN=400
w=wave.open(WAV,'rb'); A=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768.0
def build_env(a):
    sq=(a*a).astype(np.float64)
    c=np.concatenate(([0.0],np.cumsum(sq)))
    m=(len(a)-WIN)//HOP
    starts=np.arange(m)*HOP
    means=(c[starts+WIN]-c[starts])/WIN
    return np.sqrt(means+1e-12).astype(np.float32)
ENV=build_env(A)
def rms(t): i=int(t*SR/HOP); return float(ENV[max(0,min(len(ENV)-1,i))])
def frames(t0,t1): return range(max(0,int(t0*SR/HOP)), min(len(ENV)-1,int(t1*SR/HOP))+1)

args=[a for a in sys.argv[1:] if not a.startswith('--')]
PLOT='--plot' in sys.argv
INP,OUTP=args[0],args[1]
pad_pre=float(args[2]) if len(args)>2 else 0.06
pad_post=float(args[3]) if len(args)>3 else 0.09
spec=json.load(open(INP))
import os as _os
_TRP=next((p for p in ('edit/transcript_full.json','edit/transcript_hd.json','edit/transcript.json') if _os.path.exists(p)))
tr=json.load(open(_TRP))
words=[w for w in tr['words'] if w.get('start') is not None]
W_s=np.array([w['start'] for w in words]); 
lo=min(s['inSec'] for s in spec['segments']); hi=max(s['outSec'] for s in spec['segments'])
sub=ENV[int(lo*SR/HOP):int(hi*SR/HOP)]
thr=max(float(np.percentile(sub,45))*0.9, float(np.percentile(sub,95))*0.06)
MERGE_GAP=0.9
def speech(t0,t1): return bool(np.any([ENV[j]>thr for j in frames(t0,t1)])) if t1>t0 else False
IDMAP={id(w):i for i,w in enumerate(words)}
def widx(w): return IDMAP[id(w)]
def audible_onset(s0,left):
    for j in frames(max(left,s0-0.22), s0+0.12):
        if ENV[j]>thr: return j*HOP/SR
    return s0
def audible_offset_word(w1,right):
    cap=min(w1['end']+0.20, right)
    last=w1['start']
    for j in frames(w1['start'], cap):
        if ENV[j]>thr: last=j*HOP/SR
    return last
def snap_start(w0):
    # INVARIANT: never cut into w0 — the first word's onset is always preserved.
    i=widx(w0); prev=words[i-1] if i>0 else None
    left=audible_offset_word(prev, prev['end']+0.2) if prev else 0.0
    ons=audible_onset(w0['start'],left)
    start=min(w0['start'], ons)            # true onset (never later than the word start)
    gap=ons-left
    ci=start-pad_pre if gap>=0.12 else start-0.04  # silence: pad in; contiguous: hair before
    return round(max(0.0, ci),3)
def snap_end(w1):
    # INVARIANT: never cut before w1 finishes — the last word always plays in full.
    i=widx(w1); nxt=words[i+1] if i+1<len(words) else None
    right=nxt['start'] if nxt else w1['end']+0.3
    offs=audible_offset_word(w1,right)
    end=max(w1['end'], offs)               # true end of the word's audio
    gapn=(right-offs) if nxt else 0.3
    co=end+pad_post if gapn>=0.12 else end+0.04  # silence: pad into gap; contiguous: hair after
    return round(co,3)

# attach kept words, merge mid-speech splits
segs=[]
for s in spec['segments']:
    kept=[w for w in words if s['inSec']<=w['start']<s['outSec']]
    if kept: segs.append({**s,'w0':kept[0],'w1':kept[-1]})
merged=[segs[0]]
for s in segs[1:]:
    p=merged[-1]
    g=s['w0']['start']-p['w1']['end']
    if 0<=g<MERGE_GAP and (g<0.12 or speech(p['w1']['end'],s['w0']['start'])):
        p['w1']=s['w1']; p['outSec']=s['outSec']; p['_m']=p.get('_m',0)+1
    else: merged.append(s)
print(f"# thr={thr:.4f} segs {len(spec['segments'])}->{len(merged)}")
out=[]
for s in merged:
    ni=snap_start(s['w0']); no=snap_end(s['w1'])
    tag='ok' if rms(ni)<thr*1.3 and rms(no)<thr*1.3 else 'RISK'
    print(f"  [{ni:.2f}-{no:.2f}] {s['w0']['text']!r}..{s['w1']['text']!r} rms_in={rms(ni):.3f} rms_out={rms(no):.3f} {tag}{' merged+'+str(s['_m']) if s.get('_m') else ''}")
    o={"inSec":ni,"outSec":no,"beat":s.get('beat','POINT'),"framing":s.get('framing','cover'),"cropX":s.get('cropX',0.5)}
    if s.get('mute'): o['mute']=True
    out.append(o)
spec['segments']=out
if OUTP!='-': json.dump(spec,open(OUTP,'w'),ensure_ascii=False,indent=1); print("# wrote",OUTP)

if PLOT:
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(18,3.2))
    t=np.arange(int(lo*SR),int(hi*SR))/SR
    ax.plot(t, A[int(lo*SR):int(hi*SR)], lw=0.3, color='#5b8fb0')
    for o in out:
        ax.axvspan(o['inSec'],o['outSec'],color='#2ecc71',alpha=0.22)
        ax.axvline(o['inSec'],color='#e74c3c',lw=1.1); ax.axvline(o['outSec'],color='#e74c3c',lw=1.1)
    ax.axhline(thr,color='#999',lw=0.5,ls='--'); ax.axhline(-thr,color='#999',lw=0.5,ls='--')
    ax.set_xlim(lo,hi); ax.set_ylim(-0.6,0.6); ax.set_title(f"{INP.split('/')[-1]}  — green=kept, red=cut (all cuts land in dead space)")
    ax.set_yticks([]); plt.tight_layout(); png=OUTP.replace('.json','')+'_wave.png' if OUTP!='-' else '/tmp/wave.png'
    png='/home/user/videos/jackkneel/'+INP.split('/')[-1].replace('.cutspec.json','')+'_wave.png'
    plt.savefig(png,dpi=90); print("# plot",png)
