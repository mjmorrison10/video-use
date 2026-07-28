#!/bin/bash
# Pipeline for the TRW859 promo: snap -> build_props -> localize(panel crop) -> render -> loudnorm
# Differs from the jackkneel pipeline in one way: the source is a side-by-side
# remote call, so localize pre-crops Chief Little Eagle's panel to 9:16 and the
# React layer just covers an already-vertical source (no face tracking needed —
# his webcam is fixed).
set -e
cd /home/user/video-use/remotion-shorts
c="${1:-trw859_promo}"
TR=/home/user/videos/trw859/edit/transcript_full.json
SRC=/home/user/videos/trw859/interview859.mp4
# content band y=266..813 (548 tall); his face centres on x~1380 => 9:16 crop 308x548
VF="crop=308:548:1226:266,scale=1080:1920:flags=lanczos"

# 1) silence-snap the cut-spec (cwd must hold audio.wav + edit/transcript_full.json)
( cd /home/user/videos/trw859 && uv run --with numpy python /home/user/videos/jackkneel/snap_silence.py \
    /home/user/video-use/remotion-shorts/jobs/$c.cutspec.json \
    /home/user/video-use/remotion-shorts/jobs/$c.snap.cutspec.json 2>&1 \
    | grep -vE "Installed|Prepared|Resolved|Audited|Downloading|Building|Built|^\s*$" )
# 2) build props
python3 scripts/build_props.py jobs/$c.snap.cutspec.json $TR -o jobs/$c.json 2>&1 | grep -iE "props|warn"
# 3) assemble a tiny source from only the used beats, pre-cropped to 9:16
#    (localize would extract one 68-min window since beats span the whole interview)
python3 scripts/assemble_src.py jobs/$c.json $SRC --vf "$VF" 2>&1 | grep assemble
# 4) render + loudnorm
npx remotion render src/index.ts Short out/_raw_$c.mp4 --props=./jobs/$c.json 2>&1 \
  | tr '\r' '\n' | grep -iE "encoded [0-9]+/[0-9]+$|error" | tail -1
ffmpeg -y -v error -i out/_raw_$c.mp4 -af loudnorm=I=-13:TP=-1.0:LRA=11 -c:v copy -c:a aac -b:a 192k out/$c.mp4 \
  && rm -f out/_raw_$c.mp4
echo "DONE $c: $(ffprobe -v error -show_entries format=duration -of csv=p=0 out/$c.mp4)s"
