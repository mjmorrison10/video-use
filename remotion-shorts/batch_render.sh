#!/bin/bash
# Render a list of jk2_* clips sequentially via process_clip.sh, logging results.
cd /home/user/video-use/remotion-shorts
LOG=/tmp/pipe19.log
: > "$LOG"
for c in "$@"; do
  echo ">>> $c $(date +%T)" | tee -a "$LOG"
  if bash process_clip.sh "$c" >>"$LOG" 2>&1; then
    tail -1 "$LOG"
  else
    echo "FAILED $c" | tee -a "$LOG"
  fi
done
echo "=== ALL DONE ===" | tee -a "$LOG"
grep -E "^DONE|^FAILED" "$LOG"
