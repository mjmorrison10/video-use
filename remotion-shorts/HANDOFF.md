# Shorts Pipeline — Handoff / Playbook

How we turn one long podcast into a batch of hyper-engaging **9:16 single-point
short-form clips**, end to end. Hand this file to a fresh session to reproduce the
whole process for a new client.

- **Repo:** `mjmorrison10/video-use`, folder `remotion-shorts/`.
- **Renderer:** [Remotion](https://remotion.dev) 4.0.489 (React → MP4). Replaces the
  old ffmpeg/ASS burn — captions, animation, and layout are React.
- **Ephemeral media** (NOT committed) lives in `/home/user/videos/<proj>/`
  (`source.mov`, `proxy.mp4`, `audio.wav`, `edit/`, `music/`, `out/`). Only code +
  cut-specs are committed.

---

## House style (the locked "brand" look)

**`/CLAUDE.md` at the repo root is the authority — read it first.** It is kept in
sync with the client's own finished cuts. The summary below is orientation only;
where the two disagree, CLAUDE.md wins.

| | |
|---|---|
| Format | 9:16, **1080×1920**, 30fps |
| Font | **Big Shoulders Bold** (`public/BigShoulders-Bold.ttf`), ALL-CAPS, centered. Fallback `theboldfont.ttf`. |
| Captions | **2–3 words per page**, phrase-level breaks, **NEVER any punctuation**, screen-centered, heavy black stroke, `fontSize` 48 |
| Power words | key words render **`#13FFFF`** with a glow and stay lit; everything else white. Light the spine of the argument only. |
| Title | two lines held ~2.5s **under the caption line** — white setup, accent question |
| Ending | **no CTA card** unless asked; end on the speaker |
| Music | one track per clip, low bed that does **not** swell over dialogue |
| Audio | **dialogue-forward**, loudness-normalized to **−14 LUFS** |
| Framing | `cover` crop, face-tracked; `letterbox` for B-roll bookends |
| Cut | **15–45s**, **hook first**, one single point, 0.1–0.3s between beats, every word given its full decay |

Caption text is produced in exactly one place — `scripts/caption_text.py`. Never
hand-build a caption token. Change the look in `DEFAULT_STYLE`
(`scripts/build_props.py`) plus the matching zod defaults in
`src/Short/schema.ts` and `src/Root.tsx` — all three together.

Every render is finished with `scripts/finish.py` (house grade + loudness).

---

## Architecture: DATA (Python) → RENDER (React)

```
Drive .mov ──gdown──▶ source.mov
   │ ffmpeg
   ├─▶ proxy.mp4  (1080p H.264, symlinked/hardlinked into public/)   ← video for render
   └─▶ audio.wav  (16 kHz mono)  ──transcribe_whisper.py──▶ edit/transcript.json
                                                                  (word-level)
                              │
        agency agents author a CUT-SPEC per clip  (jobs/<clip>.cutspec.json)
                              │  + music agent → music_map.json
        build_props.py CUTSPEC + transcript ──▶ jobs/<clip>.json  (Remotion props)
                              │
        render_all.sh:  remotion render ──▶ ffmpeg loudnorm ──▶ out/<clip>.mp4
```

---

## Environment setup (fresh container)

```bash
# tools
apt-get update -qq && apt-get install -y ffmpeg      # ffmpeg + ffprobe
uv tool install gdown                                # Drive downloads
# node deps
cd remotion-shorts && npm install
```
- **Chromium:** Remotion auto-downloads its own `chrome-headless-shell` (works).
  Do **NOT** pass the full Playwright Chromium at `/opt/pw-browsers/chromium-*/…`
  — it dropped old-headless mode and the render fails. If you must pin one, use
  `--browser-executable=/opt/pw-browsers/chromium_headless_shell-*/chrome-linux/headless_shell`.
- **Whisper** runs via `uv run --with faster-whisper` (no install needed, no API key).
- **Disk:** the raw source is huge (this episode was a 7.2 GB 4K .mov). Make the
  proxy, then **delete the raw** to reclaim space.

---

## Step-by-step

### 1. Ingest
```bash
mkdir -p /home/user/videos/<proj>/{edit,music,out}
gdown "https://drive.google.com/uc?id=<FILE_ID>" -O /home/user/videos/<proj>/source.mov
ffprobe -v error -show_entries stream=width,height,codec_name -show_entries format=duration source.mov
```

### 2. Proxy + audio, then reclaim disk
```bash
ffmpeg -y -i source.mov -vn -ac 1 -ar 16000 -c:a pcm_s16le audio.wav          # STT audio
ffmpeg -y -i source.mov -vf scale=1920:1080 -c:v libx264 -preset faster -crf 19 \
       -c:a aac -b:a 192k -movflags +faststart proxy.mp4
rm source.mov                                                                  # free the raw
# make proxy + music reachable to Remotion staticFile():
ln public/... # HARDLINK proxy.mp4 + each track into remotion-shorts/public/ (symlinks can break the static server)
```

### 3. Transcribe (local Whisper, chunked)
```bash
uv run --with faster-whisper python scripts/transcribe_whisper.py \
    /home/user/videos/<proj>/audio.wav -o /home/user/videos/<proj>/edit/transcript.json \
    --model medium.en --chunk 180
```
Emits a flat word list `{text,start,end,type,speaker_id}`. **Sanity-check word
density** — Whisper truncates on this content, so the chunked pass is important.
Build a readable `edit/timed.txt` (phrase lines prefixed `[start–end]`) for the
editorial agents (group words, break on >0.6s gaps / sentence punctuation).

### 4. Editorial — the agency agents author each clip (see "Agents" below)
Each clip = one `jobs/<clip>.cutspec.json`. **Locate quotes by CONTENT**, not by any
stated timestamp (TurboScribe/RECALL timestamps are ±minutes). Cut to the word.

### 5. Music — the music agent assigns a distinct track per clip
Enumerate the Drive music library, download a curated candidate set, and have the
music-supervisor agent write `jobs/music_map.json` (one distinct `src` per clip +
`volLow/volHigh/climaxSec`). Then inject each clip's music into its cut-spec.

### 6. Build props
```bash
python scripts/build_props.py jobs/<clip>.cutspec.json \
    /home/user/videos/<proj>/edit/transcript.json -o jobs/<clip>.json
```
Computes output-time caption pages (2–3 words, sentence-aware), applies
`captionReplace`/`captionGroups`, merges `DEFAULT_STYLE`.

### 7. Render + loudness-normalize
```bash
./render_all.sh          # remotion render each → ffmpeg loudnorm=I=-13:TP=-1.0:LRA=11
```

### 8. Verify + deliver
`ffprobe` each (1080×1920, 15–45s, audio present); extract a frame to eyeball the
hook/captions; measure loudness. Write the client-facing `<Podcast> Clips.md`
(simple cards: title, video/length, spoken hook, music, one blockquote
transcription — see `Emergency Meeting 149 Clips.md`).

---

## Cut-spec format (`jobs/<clip>.cutspec.json`)

```jsonc
{
  "videoSrc": "proxy.mp4",
  "fps": 30,
  "segments": [                                   // play in listed order (reorder for impact)
    {"inSec": 158.51, "outSec": 166.63, "beat": "HOOK", "framing": "cover"},
    {"inSec": 227.12, "outSec": 227.45, "beat": "REINFORCE", "framing": "cover", "mute": true}
  ],
  "captionReplace": {"hoe": "wife"},              // fix mis-transcription / censor a caption word
  "captionGroups":  [2,3,3,2, ...],               // OPTIONAL exact words-per-line (else auto 2–3)
  "style": {"powerWords": ["consciousness","future","time","100"]},   // rest inherits DEFAULT_STYLE
  "hook":  {"text": "GUT FEELINGS ARE TIME TRAVEL", "untilSec": 2.5},
  "music": {"src": "interstellar.mp3", "volLow": 0.03, "volHigh": 0.06, "climaxSec": 18, "startSec": 0}
}
```
- **Word-level cutting:** each span is a source in/out at word boundaries. To drop a
  filler word mid-sentence, split into two spans that skip it.
- **`mute: true`** drops that span's audio (used to censor a word while the video
  keeps playing under the music).
- **Censor a slur audibly + in caption:** split the word into its own muted span +
  add it to `captionReplace` (e.g. we muted "hoe" and captioned it "wife").

---

## The agency agents (the editorial brain)

Personas live in the `agency-agents` repo. They are NOT registered subagent types —
invoke by feeding each persona `.md` to a `general-purpose` subagent (or use the
registered `UI Designer` for the font). **Some general-purpose agents occasionally
glitch and return nothing — if a cut-spec doesn't get written, hand-author it from
the transcript.**

| Job | Persona / agent | Output |
|---|---|---|
| Find the single controlling idea | `academic/academic-narratologist.md` | the one point per clip |
| Hook + clip selection + platform | `marketing/marketing-tiktok-strategist.md` | 3-sec hook, structure |
| Word-level cut, pacing, retention | `marketing/marketing-short-video-editing-coach.md` + `marketing/marketing-video-optimization-specialist.md` | the span list |
| Caption/on-screen copy | `marketing/marketing-content-creator.md` | phrasing |
| **Music** per clip | general-purpose "music supervisor" over the library | `music_map.json` |
| **Font** for the brand | registered **UI Designer** | font pick (→ `load-font.ts`) |

Editorial workflow per clip: Narratologist → TikTok Strategist → Editing Coach +
Optimization → (Content Creator). One clip = one focused agent works best; give it
the transcript + `timed.txt` + the exact cut-spec format + content anchors.
**Structure target:** `Hook A → Point A → Hook B → reinforce`. Avoid racial slurs;
general profanity is fine unless the client says otherwise.

---

## Files

```
remotion-shorts/
├── src/
│   ├── Root.tsx                 # <Composition id="Short"> + calculateMetadata (duration from ranges)
│   ├── load-font.ts             # loads Big Shoulders Bold (+ fallback) via FontFace/delayRender
│   └── Short/
│       ├── index.tsx            # ranges → <Sequence><OffthreadVideo trim/> ; music <Audio> ; captions
│       ├── schema.ts            # zod props (ranges, captionPages, music, style, hook)
│       ├── CaptionPage.tsx      # a 2–3-word page; yellow power words; spring-in; center/bottom
│       └── HookOverlay.tsx      # burned-in hook headline
├── scripts/
│   ├── transcribe_whisper.py    # chunked word-level faster-whisper
│   └── build_props.py           # cut-spec + transcript → Remotion job JSON (DEFAULT_STYLE here)
├── render_all.sh                # render each clip → loudnorm -13 LUFS
├── jobs/                        # <clip>.cutspec.json (authored) + <clip>.json (generated) + music_map.json
└── public/                      # proxy.mp4, *.mp3 (hardlinked), *.ttf fonts
```

---

## Gotchas (these cost real time)

1. **Whisper truncates** on this content → chunked (~180s) word-timestamp passes;
   sanity-check density.
2. **Stated timestamps are ±minutes** (RECALL/TurboScribe) → locate quotes by content.
3. **Held-word "dead space":** Whisper sometimes gives one word a multi-second
   duration (a pause/freeze). If a clip has a beat of nothing, check for a long word
   and re-cut around it.
4. **Chromium:** use Remotion's headless shell; the full Playwright Chromium fails.
5. **public/ assets:** hardlink (not symlink) proxy + music in, or the static server
   may not serve them.
6. **Music must be LOW + voice-forward**, then loudnorm — otherwise music buries the
   speaker. Instrumental beds only (vocals compete with the VO).
7. **Some agents glitch** (0 tool calls, garbled) → hand-author that cut-spec.
8. **Disk:** delete the raw source after the proxy exists.

---

## Reproduce for a NEW client — turnkey

```bash
# 0. setup (once):  apt-get install -y ffmpeg ; uv tool install gdown ; (cd remotion-shorts && npm install)
# 1. ingest + proxy + audio  (Steps 1–2), hardlink proxy into public/
# 2. transcribe               (Step 3)
# 3. agents author cut-specs + music_map, download+hardlink chosen tracks
# 4. python build_props for each clip
# 5. ./render_all.sh
# 6. write "<Podcast> Clips.md" and deliver out/*.mp4
```
If the client names a brand, run the **UI Designer** agent for a brand-fit font and
set brand colors in `DEFAULT_STYLE`; otherwise the generic house style above applies.
