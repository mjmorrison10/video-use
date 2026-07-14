---
name: podcast-reels
description: Turn a long podcast/interview video + a list of RECALL "clip concepts" (timestamp + quote per moment) into a batch of vertical 9:16 short-form reels. Each reel is a complete story (hook -> one point -> a landing payoff), auto-cropped per camera shot to follow the speaker, with serif pop-in captions, filler + dead-space removed, and a tone-matched music bed that cuts right before the punch. Built and proven on the "Justin Waller vs Therapist" episode.
---

# Podcast Reels

Convert one long interview into many viral vertical clips. This is the exact
pipeline that produced the Justin Waller set — read it top to bottom, then run
the steps. The reference tools live in `tools/` next to this file.

## What the finished clip has (the spec)

1. **Story-driven cut** — opens on the RECALL quote (the hook), develops ONE
   point, and ends on a line that LANDS (a button/mic-drop). Cut BEFORE the
   speakers wander onto a tangent. Never end mid-thought or abruptly.
2. **Length 15–45s** (aim 18–35). A satisfying earlier ending beats padding.
3. **9:16, per-shot auto-crop** — every camera shot gets its own static crop
   anchored on that shot's face, so the speaker stays framed through every cut
   (no lag onto empty background). Face in the "red safe zone", nose ~ (50.8%,
   31.4%) of frame. Adaptive zoom keeps the face a consistent big size.
4. **Zoom-punch transition** at each camera/speaker cut (1.12x → 1.0x over ~4
   frames).
5. **Captions** — DejaVu Serif Bold, UPPERCASE, centered (Alignment 5). Power
   words in **neon cyan-blue `#00E0FF`** with the SAME black outline as white
   words (no glow). Each line **pops** (scale 50%→100% in 25ms) except a clip's
   first line. A new caption starts at every **sentence** (.!?). Fillers
   (um/uh/mm-hmm) are dropped from captions.
6. **Fillers + dead-space cut** from audio+video (word-boundary micro-cuts with
   30ms fades so there are no pops).
7. **Music bed** — tone-matched track, its best BUILDING section (anywhere in
   the song), normalized to a steady low level (NO sidechain ducking — that
   pumps), and it **cuts ~0.6s before the clip's final word** so the punch lands
   clean.

## Setup (once per environment)

```bash
apt-get update -qq && apt-get install -y --no-install-recommends ffmpeg
pip install --break-system-packages faster-whisper opencv-python-headless \
    librosa matplotlib pillow numpy requests gdown
# YuNet face model (git-LFS media URL, NOT the raw github url):
curl -sSL -o tools/yunet.onnx \
  "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
```
Whisper/OpenCV are CPU-only here; that's fine. OpenCV 5 dropped Haar cascades —
we use YuNet (`cv2.FaceDetectorYN`), which also gives face landmarks.

**Working dir layout** (mirror this; the tools assume `edit/` next to the source
mp4, and use `edit/transcripts/`, `edit/out/`, `edit/work/<cid>/`):
```
<project>/
  <Source>.mp4
  music/<Folder>/*.mp3        (optional, for the music step)
  edit/transcripts/  edit/out/  edit/work/  edit/context/
  tools/  (copies of this skill's tools/)
```
NOTE: the reference tools hardcode `/home/user/claude-video-editor` paths and a
project-specific clip list. When starting a new project, update those (search
for `claude-video-editor`, and the `CLIPS`/`CLEAN`/`DRIFTED` lists in
`locate_quotes.py`, `make_context.py`, `batch.py`).

## Inputs

- The **source video** (download with `gdown` if it's in Drive — set the file to
  "Anyone with the link", then `gdown --fuzzy <url>` or
  `python -c "import gdown; gdown.download(id='FILEID', output='...')"`; the MCP
  Drive tool returns base64 and is useless for >~50MB).
- **RECALL clip concepts**: a numbered list, each `[H:MM:SS] "quote" — title`.
  These timestamps are often WRONG by many minutes — locate by CONTENT, not time
  (see step 3). The quote text may not be verbatim either.

## Pipeline

### 1. Transcribe (word-level, cached)
Use `faster-whisper` `small.en` with `word_timestamps=True`, `vad_filter=True`.
Transcribe the WHOLE file in resumable ~12-min chunks so a container restart
doesn't lose it:
```bash
python tools/transcribe_chunks.py <Source>.mp4 edit/transcripts/_full.json --start 0 --end <dur> --chunk 720
cp edit/transcripts/_full.json edit/transcripts/<SourceStem>.json   # canonical name = video stem
```
Output schema (the whole pipeline reads this): `{"words":[{"type":"word","text","start","end","speaker_id":null}...]}`.
For a bad patch, re-transcribe that window with **`medium.en`** (much more
accurate) and splice the words back in (this fixed a garbled caption line).

### 2. (removed) — clip list comes from RECALL, see step 3.

### 3. Locate each quote in the transcript
Timestamps drift (30+ min in our episode), so use `locate_quotes.locate_global`
(best fuzzy match anywhere) rather than a windowed search. Confirm each with a
match ratio; >0.55 is usable. `locate` (windowed) is fine for clips whose given
timestamp is accurate.

### 4. Story selection (one analyst agent PER clip)
This is what makes them watchable — NOT a time-based extension. For each clip,
build a context window (`make_context.py`: the hook line + a timestamped
transcript of the ~170s that follow) and spawn ONE agent per clip (fan out with
the Workflow tool). Each agent picks `start_ts`, `end_ts`, and the verbatim
`ending_line` so the clip opens on the hook, makes one point, and ends on a beat
that lands — cutting BEFORE the tangent. Prompt them exactly like this:

> You are an elite short-form podcast clip editor... open on the hook, develop
> ONE point, end on a line that LANDS (button/mic-drop), never mid-tangent.
> [Justin] and [therapist] drift a lot — end at the last line that completes the
> hook's point, before the drift. 15–45s (aim 18–35).

Snap the picks to word boundaries with `build_from_picks.py`.

### 5. Build EDLs (dead-space + filler removal)
`edl_build.build(...)` → `keep_intervals` drops silence gaps ≥0.55s AND filler
words (um/uh/mm-hmm/uh-huh...). Each clip EDL is a list of source ranges.

### 6. Render 9:16 per-shot + captions
`render_all.py` renders every `edit/clip_c*.json` in isolated work dirs (parallel
is fine ONLY with isolation — shared intermediates clobber each other). Per clip
`render_crop.py`:
- `reframe.analyze` detects **scene cuts** (frame-diff) and splits the range into
  **shots**; each shot returns a face anchor (bbox center-x + ~nose-height, which
  is stable on turned/profile heads — the nose-TIP landmark drifts) and a face
  size. Active speaker on wide two-shots = accumulated mouth-motion, left-biased
  (main speaker). No-face shots → center + wider crop.
- Each shot is extracted with its OWN static crop (adaptive zoom: `TARGET_FACE`
  600, `S_MIN..S_MAX` 1.9..3.6; wider when face coverage < 0.65), scaled to
  1080×1920, anchor placed at (0.508, 0.314). Shots after the first get the
  **zoom-punch**. Audio is extracted CONTINUOUSLY per range (fades only at range
  edges — never at internal shot cuts, or you get audio dips).
- Captions burned LAST via `ass_captions.py` (the style above). This step also
  loudnorms to -14 LUFS.

### 7. Music (optional but high-impact)
1. `analyze_music.py` → tempo/energy/brightness per track (incremental save;
   NOTE the librosa gotcha: `beat_track()[0]` is an array, wrap with
   `float(np.atleast_1d(...).ravel()[0])`).
2. Match each clip to a track by TONE. Pre-categorized folders help
   (Deep=emotional/cinematic, Energetic=trap/phonk hype, Bugatti=phonk edits).
   Emotional/vulnerable → Deep; aggressive/flex → Energetic/Bugatti;
   motivational → uplifting builds. Keep variety, write `edit/music_map.json`.
3. `music_batch.py` mixes each: `music_segment.find_best_segment` finds a
   RISING window (music can peak anywhere in the song); normalize to
   `TARGET_RMS` 0.04 (per-track, so phonk isn't 10× the piano); STEADY volume,
   NO ducking; music CUTS ~0.6s before the final word (`compute_climax`, drops
   right before the last ~2 words). Per-clip trims + `compress` for a loud build
   spike live in `edit/music_levels.json`.

## Hard-won lessons (do not relearn these)
- **Read the attached repos FIRST.** The client's spec (serif font, "use the
  agents", the framing template) lived in git, not the prompt.
- Locate clips by **content**, never the given timestamp.
- A clip is a **story**, not "hook + next 20 seconds." Use an agent per clip.
- Reframe **per shot**, not per clip — one crop-track per range lags onto empty
  background at cuts. Anchor on the bbox, not the nose-tip.
- Parallel renders MUST use isolated work dirs.
- Music: **no sidechain ducking** (it pumps). Normalize + steady low bed.
- Music ends **right before the punch** (~0.6s), not at the last sentence start.
- `faster-whisper` `medium.en` to repair a garbled patch.
