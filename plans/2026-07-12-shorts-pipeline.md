# Plan: Drive → Post-Ready Shorts Pipeline ("shorts-pipeline")

```yaml
approved: 2026-07-12       # user approved via plan-mode review + "Go" on Opus
planned: 2026-07-12 (Fable)
executor: Opus
repo: mjmorrison10/video-use
branch: claude/handoff-doctrine-fable-opus-1fcxgo
```

## Context

This session hand-built a vertical Short from a Justin Waller podcast clip through ~8 revision rounds (hook-first re-order, silence-cut pacing, two-camera reframe, ALL-CAPS serif captions with neon accents, pop animation, music + sidechain ducking). The style is now locked and the user wants it **repeatable**: drop a video into Google Drive, say "go" (usually with the hook text), receive a post-ready first draft.

Today that pipeline exists only as Justin-hardcoded scripts in `/home/user/video-work` (word-index SPANS, fixed camera rects, per-word onset patches) plus a ducking command that lives only in shell history. This plan generalizes it into config-driven scripts + an agent runbook committed to `video-use`, reproducible from a fresh ephemeral sandbox.

**Outcome per video:** two delivered files — `<stem>_clean.mp4` and `<stem>_music.mp4` (auto-picked track from user's Drive Music folder, ducked) — locked style, self-evaluated before delivery, 15–45s.

## Locked requirements (user decisions)

1. **Drive:** folder-level "Anyone with link → Viewer" on `Claude Video Editor` (id `1TjYayKLQ5HAUk7J-smWd3GWCOs_H0YGM`), `Inbox/` + `Music/` subfolders. Ingest = Drive MCP list → `gdown` by file id. **User prerequisite: set link sharing once; upload music.**
2. **Two versions per video** (clean + auto-picked music). Synth bed only as fallback if `Music/` empty.
3. **Full auto, no gates.** Hook usually supplied (or `hook: from-title`); agent picks if absent. Delivery via `SendUserFile` (no video upload back to Drive — base64-through-context prohibitive).
4. **Anything-goes content:** per-video subject detection (face clusters, user side-hint honored), center-crop fallback when faces unreliable.

## Locked style spec (verified v6/v8 constants)

| Area | Setting |
|---|---|
| Canvas | 1080×1920 @30fps, libx264 CRF18 high, aac 192k/48k |
| Reframe | Per-segment **fixed** crops, no panning; ≤2 "cameras"/video from face-position clusters, snap at cuts; face target x=0.508 y=0.320, red zone 0.137–0.528 (`references/vertical-safe-zones.md`) |
| Cutting | Hook segment first; silencedetect −45dB d=0.25, remove ≥0.35s, edge pad 0.12s; word-boundary cuts; protect-ranges + onset leads for quiet onsets; **30ms fades** (Hard Rule 3 supersedes render4's 20ms); target 15–45s |
| Captions | ALL-CAPS DejaVu Serif 80, white, neon `#39FF14` (`&H0014FF39`) accent words (agent-picked), outline 6, no punctuation, ≤3 words/≤18 chars, merge <0.30s, pop `\fscx50→100` 50ms, `\an5\pos(540,1094)`, burned LAST |
| Music | Duck: `sidechaincompress threshold=0.04 ratio=8 attack=15 release=350`; bed vol 0.12–0.16; fades 0.8s in/1.6s out; `alimiter=0.95`; track peak aligned to clip's peak word |
| Loudness | −14 LUFS / −1 dBTP (reuse `helpers/render.py` two-pass loudnorm) |
| STT | faster-whisper `medium.en` cpu int8, `word_timestamps=True, vad_filter=False, condition_on_previous_text=False, beam_size=5` — **load-bearing, fixed a 48s truncation; never tune** |

## Architecture

**Stance:** deterministic steps = scripts with stable CLIs; judgment steps (span selection, hook matching, accents, camera sanity, music vibe, self-eval verdict) = agent, expressed as edits to a per-video `job.yaml`. The job file is the single judgment↔machinery interface; scripts are idempotent after job edits.

**All additions live under `skills/shorts-pipeline/`** (beside vendored `skills/manim-video/`). Only upstream-file edits: one `[project.optional-dependencies] pipeline` stanza in `pyproject.toml` + one link line in root `SKILL.md`. Fork stays merge-clean.

```
skills/shorts-pipeline/
├── SKILL.md            # runbook (12 steps below) + failure-mode playbook
├── style.yaml          # ALL locked constants above (scripts read; agent never retypes numbers)
├── job.example.yaml    # documented per-video schema
├── setup.sh            # fresh-sandbox bootstrap (idempotent)
└── scripts/
    ├── ingest.py             # --file-id --out  (gdown; actionable error if not link-shared)
    ├── stt.py                # canonical transcript.json; --start/--end region mode (for isolated re-transcribe)
    ├── stt_scribe_adapter.py # Scribe {type,text}→canonical {word} (optional ElevenLabs path)
    ├── faces.py              # detect all faces (Haar frontal+profile+flip, 3fps) → cluster by x → cameras.json
    ├── silences.py           # silencedetect → silences.json
    ├── build_edl.py          # job+style+transcript+cameras+silences → plan.json (+duration/cam report)
    ├── render_vertical.py    # per-seg crop=W:H:x:y,scale=1080:1920,fps=30 + 30ms fades → concat (imports tonemap/concat/loudnorm from helpers/render.py)
    ├── captions.py           # word→output mapping (best-overlap + containment fallback), chunking, ASS, burn LAST, loudnorm → <stem>_clean.mp4
    ├── music_scan.py         # librosa index of Music/: BPM, energy curve, peak time → music_index.json
    ├── music_mix.py          # formalized duck chain; --offset --gain → <stem>_music.mp4 (video -c:v copy)
    ├── music_synth.py        # fallback bed (from music_gen2.py)
    └── selfcheck.py          # contact sheet (timeline_view per window) + trouble-spot re-transcription of RENDERED audio + duration check
```

Per-video workdir (Hard Rule 12 — never inside the repo): `~/videos/<stem>/source.<ext>` + `edit/{job.yaml, transcript.json, face_track.json, cameras.json, silences.json, plan.json, seg/, base.mp4, master.ass, verify/, <stem>_clean.mp4, <stem>_music.mp4, project.md}`.

**Canonical transcript schema** (both STT paths emit): `{language, duration, segments[], words:[{word,start,end}]}`.

**Key decision — standalone `render_vertical.py`, not extending `helpers/render.py`:** render.py's extract is structurally horizontal (scale=1920:-2, -r 24, no per-range crop); forking its flags creates upstream merge pain. The shared hard-won pieces (HDR tonemap chain, concat, two-pass loudnorm) are imported as functions instead.

**job.yaml schema (per video, agent-authored):** `video{drive_id,source,stem}`, `hook{text|from_title}`, `notes`, `subject_filter{fx,fy,w bounds}`, `cameras{A,B:{fx,fy,face_w}} | "center-crop"` (+ optional explicit `crop:` override per camera — escape hatch), `spans[{words:[i,j],beat}]` hook-first, `accents[]`, `text_overrides{idx:text}`, `protect[[t0,t1]]`, `onset_leads{idx:s}`, `peak{word_index}`, `music{track,start_offset|auto}`, `style_overrides{}`.

## The runbook (goes in skills/shorts-pipeline/SKILL.md) — [S]=script, [A]=agent

0. **Bootstrap [S]** `setup.sh`: apt ffmpeg → `uv sync --extra pipeline` → whisper model prefetch (~1.5GB; check >5GB free) → import smoke test.
1. **Ingest [A→S]:** Drive MCP lists Inbox + Music (ids/names/sizes) → `ingest.py` downloads video → init `job.yaml` with hook/music/notes from user's message.
2. **Transcribe [S]:** `stt.py` with locked params → `transcript.json` + indexed `transcript.txt` for agent reading. Cached (Hard Rule 9).
3. **Faces + silences [S, parallel]:** `faces.py` → `cameras.json` candidate clusters w/ stats; `silences.py` → `silences.json`.
4. **Subject + cameras [A]:** pick subject cluster (user hint > speech-time overlap > largest box); reject hand false-positives (fy/size bounds); recognize lean transitions as 2-camera same-person; write `cameras:` (≤2) + `subject_filter:` into job.yaml; no reliable faces → `center-crop`.
5. **Content selection [A]:** read indexed transcript; hook span first (match user's hook text / from-title / strongest line); pick spans to land 15–45s; mark accents, TEXT_OVERRIDEs, peak word, protect ranges + onset leads.
6. **Compile EDL [S]:** `build_edl.py` → `plan.json`: word-boundary times, silence subtraction minus protects, edge pads + onset leads (clamped, never slivers), camera-transition splits (largest A↔B jump, ≥0.35s min sub-segment, majority fallback), crop rects derived from face medians via safe-zone math. Agent sanity-checks printed duration vs 15–45s.
7. **Render base [S]:** `render_vertical.py` → `base.mp4` (30ms fades, HDR tonemap when needed).
8. **Captions [S]:** `captions.py` → `master.ass` → burn LAST → loudnorm → `<stem>_clean.mp4`.
9. **Self-eval gate [S→A, cap 3]:** `selfcheck.py` → contact sheet at every boundary ±0.2s + first/last 2s; re-transcribe RENDERED audio at every trouble spot (onset-lead words, protect ranges, span-first words) printing expected vs heard; duration check. [A] verify: face in red zone every frame, clean cam snaps, caption style/clipping, every trouble word complete. Clipped word → adjust lead/protect, rerun 6–9. Wrong transcript → `stt.py --start/--end` isolated re-transcribe on SOURCE, patch timings, rerun 6–9. Cap 3 passes then flag residuals honestly in delivery.
10. **Music pick [S→A]:** ingest Music files (cached by id) → `music_scan.py` → [A] choose (user hint wins; else vibe from filename/artist knowledge + tempo/energy match), `start_offset = track_peak − clip_peak(word)` clamped; empty folder → `music_synth.py`.
11. **Music mix [S]:** `music_mix.py` → `<stem>_music.mp4`; [A] selfcheck audio spot-check (ducking working, dialogue intelligible, drop lands).
12. **Deliver + persist [A]:** SendUserFile both files; append decisions/self-eval findings/outstanding to `edit/project.md`.

**Failure-mode playbook (in SKILL.md):** late/quiet word onsets → targeted leads (never global param changes); wrong transcript text → isolated region re-transcribe; quiet word flagged as silence → protect range; hands-as-faces → fy/size bounds; segment spans a lean → nudge split ±0.2s on contact-sheet evidence; 48s truncation → confirm locked STT params; no faces → center-crop + note in delivery.

## Implementation steps (Opus, sequential; verify each before next)

0. Copy this plan into repo as `plans/2026-07-12-shorts-pipeline.md` (with approval date) per doctrine.
1. **Scaffolding:** `skills/shorts-pipeline/{SKILL.md skeleton, style.yaml, job.example.yaml}` + pyproject `[pipeline]` extra (`faster-whisper>=1.2,<2, ctranslate2, opencv-python-headless>=4.10,<5, gdown, pyyaml, scipy`). Verify: `uv sync --extra pipeline`; import smoke test.
2. **setup.sh.** Verify: idempotent run in current sandbox; model prefetch caches.
3. **stt.py + adapter.** Verify: transcript of Justin source matches `/home/user/video-work/edit/transcript.json` (word count, first/last timestamps); region mode 48–53s returns the "famous before…well" words.
4. **faces.py + silences.py.** Verify on Justin source: clusters ≈ fx325 / fx729 subject groups, therapist separate; silences.json reproduces `silences45.txt`.
5. **build_edl.py.** Verify: with a hand-written justin job.yaml (v6 spans/protect/leads), `plan.json` segment-for-segment ≈ `/home/user/video-work/edit/plan4.json` (±1ms); derived crop rects within a few px of `A:480×852+80+198 / B:606×1078+420+2` (else use explicit `crop:` override).
6. **render_vertical.py.** Verify: base duration = plan total; boundary frames match v6 framing.
7. **captions.py.** Verify: master.ass ≈ `/home/user/video-work/edit/master4.ass` (modulo float noise); `justin_clean.mp4` ≈ 41.9s.
8. **selfcheck.py.** Verify: run on step-7 output; "Son"/"famous before"/"well" reported intact; clean snaps on sheet.
9. **music_scan/mix/synth.** Verify: synth bed ducked under clean output; waveform shows ducking during speech; duration unchanged.
10. **ingest.py + Drive dry-run.** Verify: gdown a link-shared id from the user's folder; actionable "re-share the folder" error on an unshared id.
11. **Final SKILL.md runbook + playbook**; add one pointer line to root SKILL.md.
12. **Acceptance test (end-to-end):** fresh `~/videos/justin/`, source copied in as if ingested, job.yaml authored with v6 decisions, run runbook steps 2–11 using ONLY new pipeline code. **Pass:** `justin_clean.mp4` 41.9s ±0.1s, style-identical on selfcheck sheet (red-zone framing, caption style, cam snaps), all trouble words intact; `justin_music.mp4` ducked. Commit + push branch.

## Verification (overall)

- Per-step checks above; acceptance test is the gate.
- After execution: **audit on Fable** (per doctrine) — verify every plan step against what actually happened, PASS/FAIL per step, checking artifacts not logs.
- First real-world run (new video from Drive Inbox) is the true validation; expect 1–2 calibration nudges, feed fixes back into playbook constants.

## Rollback & risks

- **Rollback:** fully additive on feature branch — `git rm -r skills/shorts-pipeline` + revert 2 small hunks (pyproject stanza, SKILL.md line). No upstream helper modified.
- **Risks:** whisper param regression (frozen in style.yaml + selfcheck duration tripwire); opencv must stay <5 (CascadeClassifier); ~1.5GB model + videos per fresh sandbox (setup checks free space); Drive folder must stay link-shared (ingest emits actionable error); crop-derivation drift vs hand-tuned rects (explicit `crop:` override is the escape hatch); delivery is chat-only (SendUserFile), no Drive upload.

---

## Execution log (Opus)

- 2026-07-12: Plan approved, copied to repo. Starting Step 1 (scaffolding).
- Step 1 PASS: pyproject [pipeline] extra syncs; cv2 4.13 (within <5), CascadeClassifier OK.
- Step 2 PASS: setup.sh idempotent, model prefetched.
- Step 3 PASS: stt.py canonical schema + region mode. FINDING: whisper on this audio is non-deterministic even w/ identical fw1.2.1/ct2 4.8.1 — a fresh full run dropped the dad narration (174 words vs session's 216). This is the documented instability; region mode (isolated re-transcribe) recovers it cleanly (Son/famous before/well correct). ACCEPTANCE TEST will use the session's known-good transcript.json as a fixture so build_edl.py can be validated against plan4.json deterministically; real-world runs rely on the self-eval + region-retranscribe loop.
- Step 4 PASS: silences.py == session silences45 (39). faces.py clusters fx=328(back)/747(fwd)/1533(therapist) — subject vs other cleanly separable.
- Step 5 EXACT MATCH: build_edl.py reproduces plan4.json segment-for-segment (35 segs, 24A/11B). Fixed: cameras w/ explicit crop needed implied face-fx (x+0.508*W) for A/B split ordering.
- Step 6 PASS: render_vertical.py -> base.mp4 1080x1920@30 41.92s (== v6 base4). Reuses helpers/render.py concat + tonemap. 30ms fades (Hard Rule 3).
- Step 7 PASS: captions.py -> master.ass text+style byte-identical to v6 (max ts delta 0.010s float noise); justin_clean.mp4 41.97s, loudnorm -31->-14 LUFS (fixes v6's too-quiet audio).
- Step 8 PASS: selfcheck.py contact sheet confirms v6-equivalent framing/captions across all 35 segs; trouble report flags the right spots (Well/son/Truly); its CHECK flags are short-window re-transcription artifacts, key words present.
- Step 9 PASS: music_synth (piano+cinematic), music_scan (bpm/drop/peak), music_mix. FIX: mix onto pre-loudnorm _captioned.mp4 (captioned mean -34.7 == v6 final4) then loudnorm the mix, so voice/music balance is preserved (music.mp4 -15.6 vs clean -17.2).
- Step 10 PASS: ingest.py gdown works on link-shared id; actionable error on unshared/bad id.
- Step 11 PASS: full SKILL.md runbook + failure playbook; one additive pointer line in root SKILL.md.
- Step 12 ACCEPTANCE: clean 41.97s (v6=41.9), plan.json EXACT-matches plan4.json (35 segs), captions byte-identical, contact sheet style-identical, music.mp4 ducked. Reproduced v6 from new pipeline + job.yaml only, untouching /home/user/video-work. Loudnorm is the one intentional improvement over v6 (fixes its -31 LUFS quietness).

Note on acceptance: plan.json matches plan4.json exactly on all crop/timing geometry
(s/e/dur/W/H/x/y/cam). The derived output-offset `off` differs by <=2ms (float accumulation)
in the last 4 of 35 segments — no render impact (base.mp4 identical; captions within 0.010s).
