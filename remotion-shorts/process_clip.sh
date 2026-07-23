#!/bin/bash
# Full pipeline for one clip: snap -> build_props -> localize -> render -> loudnorm
set -e
cd /home/user/video-use/remotion-shorts
c="$1"
TR=/home/user/videos/jackkneel/edit/transcript_full.json
SNAP=/home/user/videos/jackkneel/snap_silence.py
# 1) silence-snap the cut-spec
( cd /home/user/videos/jackkneel && uv run --with numpy python "$SNAP" \
    /home/user/video-use/remotion-shorts/jobs/$c.cutspec.json \
    /home/user/video-use/remotion-shorts/jobs/$c.snap.cutspec.json 2>&1 | grep -vE "Installed|Prepared|Resolved|Audited|Downloading|Building|Built|warn|^\s*$" )
# 1b) face-track the speaker -> per-segment cropX / crop-pan
( cd /home/user/videos/jackkneel && uv run --with opencv-python-headless --with numpy python face_track.py \
    /home/user/video-use/remotion-shorts/jobs/$c.snap.cutspec.json \
    /home/user/videos/jackkneel/jackkneel.mp4 2>&1 | grep -vE "Installed|Prepared|Resolved|Audited|Downloading|Building|Built|WARN|^\s*$" )
# 2) build props from snapped spec
python3 scripts/build_props.py jobs/$c.snap.cutspec.json $TR -o jobs/$c.json 2>&1 | grep -iE "props|warn"
# 3) localize source window
python3 scripts/localize.py jobs/$c.json /home/user/videos/jackkneel/jackkneel.mp4 2>&1 | grep localize
# 4) render + loudnorm
npx remotion render src/index.ts Short out/_raw_$c.mp4 --props=./jobs/$c.json 2>&1 | tr '\r' '\n' | grep -iE "encoded [0-9]+/[0-9]+$|error" | tail -1
ffmpeg -y -v error -i out/_raw_$c.mp4 -af loudnorm=I=-13:TP=-1.0:LRA=11 -c:v copy -c:a aac -b:a 192k out/$c.mp4 && rm -f out/_raw_$c.mp4
echo "DONE $c: $(ffprobe -v error -show_entries format=duration -of csv=p=0 out/$c.mp4)s"
