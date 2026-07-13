#!/usr/bin/env bash
# Bootstrap a fresh/ephemeral sandbox for the shorts-pipeline. Idempotent.
# Run from anywhere: bash skills/shorts-pipeline/setup.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"

echo "== shorts-pipeline setup (repo: $REPO) =="

# 1. ffmpeg (hard requirement)
if command -v ffmpeg >/dev/null 2>&1; then
  echo "[ok] ffmpeg present: $(ffmpeg -version | head -1)"
else
  echo "[..] installing ffmpeg"
  (sudo apt-get install -y ffmpeg || apt-get install -y ffmpeg) 2>&1 | tail -2
fi

# 2. disk check before the ~1.5GB model prefetch
AVAIL_GB=$(df -Pg "$HOME" 2>/dev/null | awk 'NR==2{print $4+0}')
[ -z "$AVAIL_GB" ] && AVAIL_GB=$(df -P "$HOME" | awk 'NR==2{print int($4/1048576)}')
echo "[..] free space in \$HOME: ${AVAIL_GB}GB"
if [ "${AVAIL_GB:-0}" -lt 5 ]; then
  echo "[WARN] <5GB free — whisper model (~1.5GB) + working files may not fit. Free space first."
fi

# 3. python deps
echo "[..] uv sync --extra pipeline"
uv sync --extra pipeline 2>&1 | tail -3

# 4. prefetch the whisper model into the HF cache (skips if already cached)
echo "[..] prefetching faster-whisper medium.en (cached after first run)"
uv run --extra pipeline python - <<'PY'
from faster_whisper import WhisperModel
WhisperModel("medium.en", device="cpu", compute_type="int8")
print("[ok] whisper medium.en ready")
PY

# 4b. install the caption font (Montserrat Black) so libass can resolve it for burns
FONT_SRC="$REPO/skills/shorts-pipeline/assets/fonts/Montserrat-Black.ttf"
if [ -f "$FONT_SRC" ]; then
  mkdir -p "$HOME/.fonts"
  cp -f "$FONT_SRC" "$HOME/.fonts/"
  fc-cache -f "$HOME/.fonts" >/dev/null 2>&1 || true
  if fc-list | grep -qi "Montserrat Black"; then
    echo "[ok] caption font installed: Montserrat Black"
  else
    echo "[WARN] Montserrat Black not resolving via fontconfig after install"
  fi
else
  echo "[WARN] caption font asset missing: $FONT_SRC"
fi

# 5. import smoke test
uv run --extra pipeline python - <<'PY'
import cv2, librosa, faster_whisper, gdown, yaml, scipy, numpy, PIL
c = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
assert not c.empty(), "haar cascade failed to load"
print("[ok] imports + CascadeClassifier OK (cv2", cv2.__version__ + ")")
PY

echo "== setup complete =="
