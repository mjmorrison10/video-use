#!/bin/bash
# Full re-render pipeline for snapped cutspecs:
#   detect_faces -> focus.json, build_props -> job.json, render -> loudnorm -> web compress.
# No `set -e`: a transient render timeout on one clip must not abort the batch.
# Usage: ./render_snapped.sh protein_clip1 biz_clip2 ...   (base names)
cd "$(dirname "$0")"
mkdir -p out
FILTER='Memory reported|Docker memory|differing memory|inadvertently|Using the lower|Bundling|Compositions|webpack'

proj_of () { echo "$1" | sed 's/_clip[0-9]*//'; }

for base in "$@"; do
  cs="jobs/$base.cutspec.json"
  [ -f "$cs" ] || { echo "!! $base: no cutspec, skip"; continue; }
  proj=$(proj_of "$base")
  tr="/home/user/videos/$proj/edit/transcript.json"
  proxy=$(python3 -c "import json;print(json.load(open('$cs'))['videoSrc'])")
  echo "=== $base (proj=$proj proxy=$proxy) ==="

  echo "--- face track ---"
  uv run --with 'opencv-python-headless<5' --with numpy python scripts/detect_faces.py \
      "public/$proxy" "$cs" -o "jobs/$base.focus.json" 2>&1 | grep -vE "$FILTER" | tail -1

  echo "--- build props ---"
  uv run python scripts/build_props.py "$cs" "$tr" -o "jobs/$base.json" 2>&1 | grep -vE "$FILTER" | grep -E "\[props\]|warn" | tail -3

  echo "--- render ---"
  rm -f "out/_raw_$base.mp4"
  npx remotion render src/index.ts Short "out/_raw_$base.mp4" --props="./jobs/$base.json" 2>&1 | grep -vE "$FILTER" | tail -1
  if [ ! -f "out/_raw_$base.mp4" ]; then
    echo "   render failed; retry once"
    npx remotion render src/index.ts Short "out/_raw_$base.mp4" --props="./jobs/$base.json" 2>&1 | grep -vE "$FILTER" | tail -1
  fi
  if [ ! -f "out/_raw_$base.mp4" ]; then echo "   $base STILL FAILED, skip"; continue; fi

  echo "--- loudnorm + web compress ---"
  ffmpeg -y -i "out/_raw_$base.mp4" -af loudnorm=I=-13:TP=-1.0:LRA=11 \
         -c:v copy -c:a aac -b:a 192k "out/$base.mp4" 2>/dev/null
  ffmpeg -y -i "out/$base.mp4" -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p \
         -c:a aac -b:a 160k -movflags +faststart "out/${base}_web.mp4" 2>/dev/null
  rm -f "out/_raw_$base.mp4"
  sz=$(du -h "out/${base}_web.mp4" | cut -f1)
  dur=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "out/$base.mp4")
  echo "   $base DONE: ${dur}s, web ${sz}"
done
echo "ALL DONE"
