#!/bin/bash
# Render each clip, then loudness-normalize to ~-13 LUFS (loud on phone speakers).
set -e
for n in 1 2 3 4 5 6 7 8 9 10; do
  echo "=== render clip $n ==="
  npx remotion render src/index.ts Short out/_raw_clip$n.mp4 --props=./jobs/em149_clip$n.json 2>&1 | tail -1
  echo "=== loudnorm clip $n ==="
  ffmpeg -y -i out/_raw_clip$n.mp4 -af loudnorm=I=-13:TP=-1.0:LRA=11 -c:v copy -c:a aac -b:a 192k out/em149_clip$n.mp4 2>/dev/null
  rm -f out/_raw_clip$n.mp4
done
echo "ALL DONE"
