#!/bin/bash
# Render each protein clip -> loudnorm -13 LUFS master -> compressed _web (<30MB for delivery).
# No `set -e`: a transient render timeout on one clip must not abort the batch.
cd "$(dirname "$0")"
mkdir -p out
FILTER='Memory reported|Docker memory|differing memory|inadvertently|Using the lower'
for n in "$@"; do
  echo "=== render clip $n ==="
  npx remotion render src/index.ts Short out/_raw_protein_clip$n.mp4 --props=./jobs/protein_clip$n.json 2>&1 | grep -vE "$FILTER" | tail -1
  if [ ! -f out/_raw_protein_clip$n.mp4 ]; then
    echo "clip $n render failed; retrying once..."
    npx remotion render src/index.ts Short out/_raw_protein_clip$n.mp4 --props=./jobs/protein_clip$n.json 2>&1 | grep -vE "$FILTER" | tail -1
  fi
  if [ ! -f out/_raw_protein_clip$n.mp4 ]; then echo "clip $n STILL FAILED, skipping"; continue; fi
  echo "=== loudnorm clip $n ==="
  ffmpeg -y -i out/_raw_protein_clip$n.mp4 -af loudnorm=I=-13:TP=-1.0:LRA=11 \
         -c:v copy -c:a aac -b:a 192k out/protein_clip$n.mp4 2>/dev/null
  echo "=== web compress clip $n ==="
  ffmpeg -y -i out/protein_clip$n.mp4 -c:v libx264 -crf 23 -preset medium -pix_fmt yuv420p \
         -c:a aac -b:a 160k -movflags +faststart out/protein_clip${n}_web.mp4 2>/dev/null
  rm -f out/_raw_protein_clip$n.mp4
  sz=$(du -h out/protein_clip${n}_web.mp4 | cut -f1)
  dur=$(ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 out/protein_clip$n.mp4)
  echo "clip $n done: ${dur}s, web ${sz}"
done
echo "ALL DONE"
