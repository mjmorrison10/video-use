# CLAUDE.md — short-form video house style

**Read this before touching anything in `remotion-shorts/`.** These are the
client's standing rules, learned from him re-cutting our output by hand. They are
not defaults to reconsider per project — they are the brand. If a request
conflicts with one, follow the request and say which rule you are breaking.

Ground truth is the client's own finished cut of "Stand Up For Tate". When in
doubt, match it.

**This repo is the whole project.** Videos are rendered with Remotion, but that
is the published npm package (see `remotion-shorts/package.json`) — the separate
`mjmorrison10/remotion` repo is a fork of Remotion's own source, is not part of
this pipeline, and should not be attached. Its `CLAUDE.md`/`AGENTS.md` are about
contributing to the Remotion framework, not about making these videos; do not
follow them here. `agency-agents` (creative-brief personas) and `Claude-test`
(workflow doctrine) are the useful companions.

See `SESSION_HANDOFF.md` for current state and environment setup.

---

## Captions

**1. Captions NEVER contain punctuation.** No periods, commas, question marks,
colons, dashes, ellipses, quotes, brackets. This rule has had to be repeated
across many sessions — that is a code problem, not a memory problem, and the fix
is structural: **every builder emits caption text through
`remotion-shorts/scripts/caption_text.py`.** Never write `{"text": word}` into a
`captionPage` by hand, and never add a new builder that re-implements token
emission. There is no opt-out flag.

- Kept: apostrophes (`DON'T`), `$`, `%`.
- One exception: **action captions** in asterisks — `*NODS YES*` — pass through
  untouched. Use them for reaction shots where nobody speaks.

**2. Style:** uppercase, serif, centered on screen, `fontSize: 48`, white with a
heavy black stroke. 2–4 words per page, phrase-level breaks (break where a person
breathes, not at a word count).

**3. Power words** render in the accent color, lit and glowing. Light only the
spine of the argument — money, the turn, the payoff. Lighting every noun destroys
the scarcity that makes a glow mean anything.

**4. A caption never outlives its own words.** Hold ~0.35s past the last word,
then clear. Running a page until the next page starts leaves it parked on screen
through every deliberate pause.

## Color

**Accent / power words / title / glow: `#13FFFF`.** Not `#00E5FF`, not yellow.
Set in `src/Short/schema.ts`, `src/Root.tsx`, and `DEFAULT_STYLE` in
`scripts/build_props.py` — change all three together.

## Title

The video's title is **two lines held over the opening ~2.5s, positioned UNDER
the caption line** so the two read as one block:

- line 1: white setup — `IS THIS THE`
- line 2: accent color with glow — `AMERICA YOU WANT?`

That is how titles display. It is not an end card and not a full-screen hook.
Use the `title` prop (`{lines, untilSec, fontSize}`).

## Endings

**No black CTA end card unless the client explicitly asks for one.** End on the
speaker, with the final caption held to the last frame. A card kills the loop and
wastes the last second of retention.

## Cutting

- **Every boundary word must fully decay.** A word does not end at its last loud
  sample. `snap_silence.py` enforces a `MIN_TAIL` of 0.15s. Clipped word endings
  are the single most common thing the client has had to hand-fix.
- **Tight gaps between beats: 0.1–0.3s.** Not 0.5–0.8s.
- **Drop conversational lead-ins** — "Tell me,", "So look,", "You know what". Start
  on the substance.
- Hook first. One complete message: beginning, middle, slam-dunk end.
- **Verify by re-transcribing the assembled cut** with large-v3 and diffing
  against the intended script. That is the only real proof no word got clipped.

## Audio

- **Dialogue-forward.** Speech ~−13 dB mean in the body of the video; the music
  bed sits well under it and does NOT swell over speech.
- If a video opens with narration over B-roll, the client likes that section's
  balance as-is — **push dialogue up after the intro, not during it.**
- Source dialogue is often far quieter than narration. Measure both in LUFS and
  match them **before** mixing; do not fix it with music gain.
- Final: `loudnorm=I=-14:TP=-1.0:LRA=11`.
- Verify the mix by transcribing it. If Whisper loses words to the music, so will
  a viewer. Run a no-music control — Whisper flips decode modes and a single bad
  run is not evidence.

## Look

- **HDR-style grade on the final encode**: expand contrast, crush blacks slightly,
  lift highlights. Reference measurements: shadows p5 ≈ 26 (not 63), highlights
  p95 ≈ 207 (not 186).
- 9:16, 1080×1920, 30fps.
- **B-roll bookends are letterboxed** — a centered ~78%-height band over black,
  not a full-bleed crop (`framing: "letterbox"`).
- Speaker framing is face-tracked and centered (`face_track.py --mode largest`
  for single-subject scenes, `--mode recognize` when several faces compete).
- Crop burnt-in subtitles off the source before anything else, or they collide
  with ours.

## Pipeline

`remotion-shorts/HANDOFF.md` documents the end-to-end flow. Media is ephemeral
under `/home/user/videos/<proj>/`; only code and cut-specs are committed.
