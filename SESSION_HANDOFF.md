# Session handoff — short-form video pipeline

Hand this to a fresh session. It says which repos to attach, what exists, and
what to read first.

---

## Repos to attach

**`video-use` + `agency-agents` + `Claude-test`. Do NOT attach `remotion` — it is
not needed.**

**`mjmorrison10/video-use` is the project.** Everything we build lives here:

| | |
|---|---|
| `CLAUDE.md` (root) | **the house style — read it first, it is the authority** |
| `remotion-shorts/src/` | the Remotion composition (React → MP4) |
| `remotion-shorts/scripts/` | the whole toolchain — transcription, cutting, face tracking, caption building, Premiere export, finishing |
| `remotion-shorts/jobs/` | cut-specs and job JSON (the edits themselves) |
| `remotion-shorts/HANDOFF.md` | pipeline playbook: architecture and end-to-end flow |

### On the other repos

- **`mjmorrison10/remotion` — do not attach it.** Yes, we render with Remotion,
  but that is the published **npm package**, pulled in by
  `remotion-shorts/package.json`. This repo is a fork of Remotion's own *source*
  (remotion-dev). We have never edited it and nothing in the pipeline reads from
  it. You would only want it to fix a bug in the framework itself or contribute
  upstream. Its `CLAUDE.md`/`AGENTS.md` describe contributing to Remotion and are
  irrelevant here — worse, a session that reads them may think they are the
  project's instructions.
- **`mjmorrison10/agency-agents`** — persona library used for creative briefs
  (e.g. `marketing/marketing-content-creator.md` wrote the voiceover). Invoke a
  persona as a general-purpose subagent.
- **`mjmorrison10/Claude-test`** — the plan→approve→execute→audit workflow
  doctrine. General working style, not video style.

**Attaching `video-use` is not optional.** Without it there is no pipeline and no
`CLAUDE.md`, and the caption rules below will be broken again on the first video.

---

## Installed skills

`.claude/skills/` carries the 14 [Superpowers](https://github.com/obra/superpowers)
skills, vendored into this repo so they travel with it. They cover software
development process — brainstorming, systematic debugging, writing/executing
plans, TDD, code review, git worktrees.

Vendored **without** the plugin's SessionStart hook. The official
`/plugin install superpowers` injects `using-superpowers` into every session
wrapped in `<EXTREMELY_IMPORTANT>` ("you do not have a choice", "not
negotiable"), which competes with `CLAUDE.md` for priority. As repo skills they
are available on demand via the Skill tool instead. If you want the full
behaviour, install the plugin properly — but read the note in `CLAUDE.md` about
precedence first.

## Read order for a new session

1. `video-use/CLAUDE.md` — the locked house style
2. `video-use/remotion-shorts/HANDOFF.md` — how the pipeline fits together
3. This file — current state

---

## The non-negotiables (full detail in CLAUDE.md)

- **Captions NEVER contain punctuation.** This has had to be repeated across many
  sessions. The cause was structural — `strip_punct()` lived inside one builder,
  so every new builder re-implemented captions without it. All caption text now
  comes from `scripts/caption_text.py`. **Never hand-write a caption token, and
  never add a builder that emits its own.**
- Accent colour **`#13FFFF`**, captions **48px**, uppercase, centered.
- **Title** = two lines held ~2.5s *under* the caption line: white setup, accent
  question. Not an end card.
- **No CTA end card** unless asked. End on the speaker.
- Every boundary word keeps its full decay (`MIN_TAIL` in `snap_silence.py`).
- Dialogue-forward audio; the music bed must not swell over speech.
- Finish every render with `scripts/finish.py` (HDR grade + −14 LUFS).

---

## Current state

**Delivered:** "Stand Up For Tate" — 9:16, 57.8s. Voiceover bookends around a
face-tracked lecture cut. Job: `jobs/standup_tate.json`.

The client's own hand-finished version is the visual reference for the house
style; everything in `CLAUDE.md` was measured off it.

**Open:**
1. **B-roll swap.** The two voiceover bookends use a stand-in cut from
   `public/jk_charges_src.mp4` (Andrew Tate seated, graded down). The client is
   supplying his own footage — replace `public/standup_ph_intro.mp4` /
   `standup_ph_close.mp4` and re-render. Nothing else changes.
2. **Beat tightness.** Our cut runs 57.8s where the client's runs 50.6s. The
   rules are encoded (0.1–0.3s gaps, drop lead-ins) but could go tighter if he
   wants a closer match to his length.

---

## Environment notes (save a lot of rediscovery)

- **Python:** the system interpreter has no numpy/opencv. Use `/tmp/ttsenv/bin/python`
  for anything touching `snap_silence.py`, `face_track.py`, or faster-whisper.
  Recreate with `uv pip install --python <venv> numpy opencv-python-headless faster-whisper edge-tts`.
- **edge-tts through the proxy** fails TLS on its pinned CA store. Fix by appending
  `/root/.ccr/ca-bundle.crt` to the venv's `certifi` bundle. Pass
  `boundary="WordBoundary"` (not the default) to get word timings, and trim the
  silence edge pads off each chunk.
- **Media is ephemeral and NOT committed** — `/home/user/videos/<proj>/`. Current
  project is `newvid/` (source, proxies, transcript, cut-specs, VO stems).
  Only code and cut-specs live in git.
- **Renders take ~9–12 min** for a 60s 1080×1920 clip. Run them in the background.
  Never run two `finish.py` passes on the same output file — they race and
  corrupt it.
- **Face tracking** needs `yunet.onnx` + `sface.onnx` (currently only in
  `/home/user/videos/jackkneel/`). `--mode largest` for single-subject scenes,
  `--mode recognize` when several faces compete for frame.
- **Whisper mis-times words in both directions** — it dates some words earlier
  than spoken. `snap_silence.py` handles this; don't trust raw word times for cut
  boundaries.

---

## Branch

Work has been on `claude/remotion-short-form-editing-21b25q`. If its PR has
merged, branch fresh from the default branch rather than stacking on it.
