---
name: podcast-reels-trw
description: THE REAL WORLD (TRW) social-account variant of the podcast-reels pipeline. Turn a long podcast/interview into vertical 9:16 reels via a CONCEPTS-FIRST workflow (transcribe -> propose every hook found, ranked -> user selects -> build). Same core style as podcast-reels (per-shot 9:16 crop, serif cyan pop captions, filler + dead-space removal, zoom-punch transitions, story-arc music) with TRW-specific rules: the first line of every video MUST be a hook, hooks can be chained (hook1->pointA->hook2->pointB), and TurboScribe timestamps are treated as ~6min search windows, not locations.
---

# Podcast Reels — TRW

> **SCOPE — THE REAL WORLD (TRW) ACCOUNTS ONLY.** This is the LOCKED TRW editing
> style. The general/client variant lives at `../podcast-reels/`. They are
> similar but intentionally diverge (the TRW rules below make this version
> better for TRW). **Never merge changes between the two variants without
> explicit approval.** Preserve this style going forward no matter what.

Convert one long interview into many viral vertical TRW clips. This inherits the
full podcast-reels pipeline (below) and adds the TRW-specific workflow and rules.
Reference tools live in `tools/` next to this file.

## Turnkey — no per-episode code edits

The tools are **episode-agnostic**. Nothing is hardcoded to a project; every path,
source name, and clip list resolves through `tools/project.py`. To start a NEW
episode you do NOT edit any `.py` file — you just point the tools at the project:

1. Make a project dir with the video in it (and optional `music/`):
   ```
   <project>/  <Episode>.mp4   music/…(optional)
   ```
2. Tell the tools which project — pick ONE:
   - run the tools from inside `<project>/` (auto-detects the lone `.mp4`), **or**
   - `export PODCAST_PROJECT_DIR=/path/to/project` (and `PODCAST_SRC=<stem>` if
     the dir has more than one mp4), **or**
   - drop a `project.json` in the dir: `{"source":"<Episode>.mp4"}`.
3. `project.py` then derives everything: `edit/`, `edit/transcripts/<stem>.json`,
   `edit/out/`, `edit/work/`, the `music/` dir, and the video-use `helpers/` dir
   (found from the skill's own location — no absolute path).

Per-episode **clip inputs** (the RECALL / TurboScribe list) live in data, not code:
`<project>/edit/clips.json` — `[{"id","center","quote","drifted"?}]` (`center`
may be `"H:MM:SS"`; `drifted:true` = locate globally). See
`samples/clips.example.json`. The CONCEPTS-FIRST flow below doesn't even need it —
it mines hooks straight from the transcript.

Sanity-check resolution any time with `python tools/project.py`.

## TRW workflow — STAGED, APPROVE-BEFORE-SPEND (the standard operating order)

Do NOT jump straight to rendering. Rendering and music are the expensive steps,
so nothing gets rendered until the user has approved the CUT, and no music is
added until the user has approved the VERTICAL. Stage the work and get a green
light at each gate:

1. **Transcribe** the full episode (`transcribe_chunks.py`, resumable, cached).
2. **CUT — propose clips as TEXT first (cheap).** Decide what each good clip IS:
   run story selection (analyst-per-clip, below) over the RECALL list AND/OR the
   `propose_concepts.py` hook mining, then present each proposed clip to the user
   as text — no rendering yet:
   `#N  [H:MM:SS]  "hook line"  → story it tells → ends on "<landing line>"  ~Ns`
   Each proposed clip is a complete story (opens on a hook, one point, lands).
   Send the list; the user approves/kills/tweaks per clip.
3. **APPROVAL GATE 1 (the cut).** Only for APPROVED clips do you build the EDL +
   render the 9:16 vertical (per-shot crop, serif cyan pop captions, filler +
   dead-space removal, zoom-punch). Show the rendered verticals.
4. **APPROVAL GATE 2 (the vertical).** Once a vertical is approved, **add music**
   (tone-matched bed, steady low level, runs the FULL length of the clip).
5. **Adjustments** at any stage — re-cut, re-frame, swap the track, trim levels.

Token discipline: text before pixels, one vertical before music. Never batch-render
the whole episode on spec.

`propose_concepts.py` (fan-out hook miner → ranked `CONCEPTS.md`) is still the tool
when the user wants EVERYTHING found rather than a curated RECALL list — use it to
generate the stage-2 text, then present the same way.

## TRW rules (absolutes)

- **THE FIRST LINE OF EVERY VIDEO MUST BE A HOOK. This is absolute.** A hook may
  also appear mid-video, but the opening line is always a hook. The EDL builder
  validates this (`edl_build.assert_first_line_is_hook`) — reject/rebuild any
  clip whose first kept words are not the chosen hook line.
- **Hooks can be chained into one video.** When two hooks are back-to-back on the
  same overall topic:
  `hook1 -> point A -> hook2 -> point B`, where point B complements point A or
  hook1. This becomes one video (both hooks are real hooks; the first is the
  opening line, the second lands mid-video as a re-hook before the payoff).
  When the user selects a combined concept (e.g. "12+13"), the per-clip analyst
  gets BOTH hooks' contexts and returns two spans + the seam so B pays off A.
- **TurboScribe timestamps = window START, not location.** TurboScribe emits
  hooks in large segments (e.g. 11:30–18:16, ~6 min), so five different hooks can
  all read "11:30". Treat a given timestamp `t` as "somewhere in `[t, t+7min]`"
  and locate by CONTENT: `locate_quotes.locate_global` first, or windowed search
  seeded at `[t, t+420s]`. Never trust the raw timestamp as the cut point.

## TRW tool reference (the additions beyond the shared pipeline)

Three tools carry the TRW-specific rules. All live in `tools/` next to this file.

- **`propose_concepts.py`** — the CONCEPTS-FIRST miner.
  - `make_windows(words, win=210, overlap=40)` → overlapping timestamped
    transcript windows (one per analyst agent). Overlap so a boundary hook is
    fully inside one window.
  - `window_prompt(window)` / `HOOK_SCHEMA` — the exact analyst instruction +
    forced structured output (verbatim hook, timestamp, the point it opens,
    `virality` 1-100, `pairs_with`).
  - `merge_concepts(hooks)` — dedups a hook found in two overlapping windows
    (keeps the higher-virality copy), sorts by virality.
  - `write_concepts_md(concepts, "edit/CONCEPTS.md")` — renders the selection
    sheet: `#N [H:MM:SS] (virality) "hook" — story — ~Ns — (pairs-with #M)`.
  - Driver = a Workflow fan-out: `parallel(one agent per window)` →
    `merge_concepts` → `write_concepts_md`. Send the file, build only what the
    user picks. (Full sketch in the module docstring.)

- **`locate_quotes.locate_turboscribe(words, t_start, quote, window=420)`** —
  content-first search in `[t_start, t_start+7min]`, falling back to global
  fuzzy match; returns `via: "window"|"global"` so you can see which fired. Use
  this (not raw `locate`) for TurboScribe timestamps.

- **`edl_build.build(clip_id, spans, transcript, hook_line=...)`** — pass
  `hook_line` (the selected verbatim hook) and the build is validated by
  `assert_first_line_is_hook`: it raises unless the clip's first *kept* words
  (after dead-space + filler removal, leading connectives like "and/so/because"
  stripped) ARE the hook. A raise means REBUILD — never ship it. `spans` may be a
  multi-hook sequence — `[(h1s,h1e,'HOOK1'),(aS,aE,'A'),(h2s,h2e,'HOOK2'),(bS,bE,'B')]`
  concatenates into one chained video.

---

# Core pipeline (shared with podcast-reels)

Read this top to bottom for the actual build. It is the exact pipeline that
produced the Justin Waller set.

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
5. **Colour grade — HDR pop.** Every shot gets the `hdr` grade (contrast +
   vibrance + a stronger S-curve + clarity/unsharp) baked in during the crop
   step (before captions, so text stays crisp). Reads as "HDR" on phones without
   crushing the talking head; it also colour-corrects flatness. Set via the EDL
   `grade` field (default `hdr`); `neutral_punch` is the older subtle look.
6. **Captions** — DejaVu Serif Bold, UPPERCASE, centered (Alignment 5). Power
   words in **neon cyan-blue `#00E0FF`** with the SAME black outline as white
   words (no glow). Each line **pops** (scale 50%→100% in 25ms) except a clip's
   first line. A new caption starts at every **sentence** (.!?). Fillers
   (um/uh/mm-hmm) are dropped from captions.
7. **Fillers + dead-space cut** from audio+video (word-boundary micro-cuts with
   30ms fades so there are no pops).
8. **Music bed** — tone-matched track, its best BUILDING section (anywhere in
   the song), normalized to a steady low level (NO sidechain ducking — that
   pumps), and it **runs the ENTIRE length of the clip** (short end-fade only) —
   TRW wants music under the final line too, not silence on the punch.

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
NOTE (TRW): unlike the client baseline, these tools are **turnkey** — no paths or
clip lists are hardcoded. `tools/project.py` resolves the project (see the
"Turnkey" section above); the clip list is `edit/clips.json`, not code. You should
never need to edit a `.py` file to switch episodes.

## Inputs

- The **source video** (download with `gdown` if it's in Drive — set the file to
  "Anyone with the link", then `gdown --fuzzy <url>` or
  `python -c "import gdown; gdown.download(id='FILEID', output='...')"`; the MCP
  Drive tool returns base64 and is useless for >~50MB).
- **RECALL clip concepts**: a numbered list, each `[H:MM:SS] "quote" — title`.
  These timestamps are often WRONG by many minutes — locate by CONTENT, not time
  (see step 3). The quote text may not be verbatim either.

## Pipeline

### 1. Transcribe (word-level, cached) — SHORT WINDOWS, accurate timestamps
Use `faster-whisper` `small.en` with `word_timestamps=True`. **Transcribe in
short overlapping windows, NOT one long pass.** Whisper's word timestamps are
accurate only inside its first internal 30s window; past that they ACCUMULATE
drift (~1.9s off by the 80s mark on a 720s pass). Cutting AND captioning both
read these times, so drift makes clips start early and captions run ahead of the
audio. `transcribe_chunks.py` handles this: it slides a 35s `--window` with a
25s `--stride` commit zone and keeps each word only from a window's accurate
early zone. `vad_filter` is OFF (its silence remap drifts too).
```bash
python tools/transcribe_chunks.py <Source>.mp4 edit/transcripts/<SourceStem>.json --end <dur> --window 35 --stride 25
```
Output schema (the whole pipeline reads this): `{"words":[{"type":"word","text","start","end","speaker_id":null}...]}`.
**Verify** before cutting: extract source audio at a couple of points and
re-transcribe a short window there; the word times must match the full
transcript (short windows are the ground truth). For a bad patch, re-transcribe
that window with **`medium.en`** and splice the words back in.
Residual: words immediately after a pause can still jitter ~0.5–1s (normal
Whisper behavior, not drift) — the cut builder adds a little lead pad so a hook's
first word is never clipped.

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
   NO ducking; music runs the FULL clip length with a short end-fade
   (`mix(..., full_length=True)`, the TRW default). Per-clip trims + `compress` for a loud build
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
- Music runs the **FULL length** of the clip (short end-fade) — TRW wants the bed
  under the final line. (`full_length=False` restores the older cut-before-punch.)
- `faster-whisper` `medium.en` to repair a garbled patch.
- **Transcribe in SHORT windows, never one long pass.** Whisper word timestamps
  drift ~1.9s by 80s into a pass; long chunks silently corrupt BOTH your cut
  points and caption sync. Always verify a rendered clip's audio against its
  captions (transcribe the RENDERED audio) before shipping — it's the only
  ground truth for sync.
