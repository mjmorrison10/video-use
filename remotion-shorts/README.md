# remotion-shorts

Remotion-based renderer for hyper-engaging **9:16 (1080×1920)** short-form clips,
used as the RENDER stage of the video-use pipeline (replaces the ffmpeg/ASS burn).

Every clip: **opens with a hook**, carries **one single message**, runs **15–45s
(prefer <40s)**, and is trimmed **word-by-word** (each unnecessary word cut).

## Pipeline (DATA in Python → RENDER in React)

```
source.mov ──ffmpeg──▶ audio.wav ──scripts/transcribe_whisper.py──▶ edit/transcript.json
source.mov ──ffmpeg──▶ proxy.mp4  (1080p, symlinked into public/)
                         │
        editorial (agency agents) authors a CUT-SPEC (chosen word-boundary spans)
                         │
   scripts/build_props.py CUTSPEC transcript ─▶ jobs/<clip>.json  (Remotion props)
                         │
             npx remotion render src/index.ts Short ─▶ out/<clip>.mp4
```

### 1. Transcribe (local, no API key)
```
uv run --with faster-whisper python scripts/transcribe_whisper.py \
    /home/user/videos/em149/audio.wav \
    -o /home/user/videos/em149/edit/transcript.json --model medium.en --chunk 180
```
Chunked word-level pass (handoff gotcha #1: full-file Whisper truncates this
content). Emits a flat word list `{text,start,end,type,speaker_id}`.

### 2. Author a cut-spec
`jobs/<clip>.cutspec.json` — chosen source spans (word-boundary in/out seconds).
To drop a filler word, split its span in two. Example shape:
```json
{
  "videoSrc": "proxy.mp4", "fps": 30,
  "segments": [
    {"inSec": 84.0, "outSec": 90.5, "beat": "HOOK",  "framing": "cover"},
    {"inSec": 91.2, "outSec": 98.0, "beat": "POINT", "framing": "cover"}
  ],
  "music": {"src": "sneaky.mp3", "startSec": 0, "volLow": 0.05, "volHigh": 0.11, "climaxSec": null},
  "style": {"highlightColor": "#FFD60A", "captionBottom": 430, "fontSize": 110, "uppercase": true},
  "hook":  {"text": "GUT FEELINGS ARE TIME TRAVEL", "untilSec": 2.5}
}
```

### 3. Build props (adds output-time captions)
```
python scripts/build_props.py jobs/<clip>.cutspec.json \
    /home/user/videos/em149/edit/transcript.json -o jobs/<clip>.json
```

### 4. Render
```
# proxy + music must be reachable via staticFile → symlink into public/
ln -sf /home/user/videos/em149/proxy.mp4 public/proxy.mp4
mkdir -p public/music && ln -sf /home/user/videos/em149/music/sneaky.mp3 public/sneaky.mp3

npx remotion render src/index.ts Short out/<clip>.mp4 --props=./jobs/<clip>.json
# Chromium: let Remotion use its own auto-downloaded chrome-headless-shell (works
# out of the box). Do NOT pass the full Playwright Chromium
# (/opt/pw-browsers/chromium-1194/chrome-linux/chrome) — it removed old-headless
# mode and the render fails. If you must pin a binary, use the headless shell:
#   --browser-executable=/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell
```

## Composition (`src/Short`)
- `schema.ts` — zod props (ranges, captions, music, style, hook).
- `index.tsx` — maps `ranges[]` → `<Sequence from durationInFrames><OffthreadVideo
  trimBefore trimAfter/></Sequence>`; `cover` crop or `blur-contain` fill; music
  `<Audio>` with a low→high→low volume arc; word-highlight caption pages.
- `CaptionPage.tsx` — `@remotion/captions` pages, active-word highlight, spring-in.
- `HookOverlay.tsx` — big burned hook headline over the opening seconds.

Media lives in `/home/user/videos/<proj>/` (gitignored); only code + job specs are
committed.
