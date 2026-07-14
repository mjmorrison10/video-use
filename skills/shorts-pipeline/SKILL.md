# shorts-pipeline — Drive → post-ready vertical Short

> **Scope: CLIENT work only.** TRW / personal social accounts use `skills/podcast-reels-trw/`
> (a separate Claude session, branch `…-g6d8pz`). The two styles are similar by design but must
> not cross-contaminate — do not merge style changes between the client and TRW variants without
> explicit approval. Per-client brand (font, accent colour, framing, music level) lives in
> `clients/<name>.yaml` (loaded as `job.style_overrides`); `clients/default.yaml` is the locked
> baseline. **Standard order: ingest → transcribe → propose clips as text (`scripts/propose_clips.py`)
> → user picks → build picks → selfcheck → deliver clean → music on request.** Two absolutes:
> the first line of every video **must** be a hook, and TurboScribe hook timestamps are
> *search-window hints* (segment starts up to ~6 min), so locate every hook by content.

Turns a horizontal talking-head video (dropped in a link-shared Google Drive folder) into a
post-ready 9:16 Short in a locked style: hook-first, dead-air cut, per-segment fixed-camera
reframe (no panning, face in the red zone), ALL-CAPS serif captions with neon accents + pop
animation, and two deliverables per video — clean + auto-picked music (sidechain-ducked).

**Claude is the operator.** Deterministic steps are scripts (`scripts/*.py`); judgment steps
(span selection, hook matching, accent words, camera sanity, music vibe, self-eval verdict) are
agent decisions expressed as edits to a per-video `edit/job.yaml`. Scripts are idempotent after a
job edit — re-run to apply.

- Locked constants: `style.yaml` (never retype numbers into scripts/prompts).
- Per-video contract: `job.yaml` (schema + docs: `job.example.yaml`).
- Framing math + safe zones: `../../references/vertical-safe-zones.md`.
- Outputs live in `<workdir>/edit/`, never inside this repo (SKILL Hard Rule 12).

Run scripts from the repo root as:
`uv run --extra pipeline python skills/shorts-pipeline/scripts/<x>.py ...`
Bootstrap a cold sandbox first with `bash skills/shorts-pipeline/setup.sh`.

## Turnkey per-project flow (no code edits — all inputs are data/config)

Every script is parameterized: the project comes in through arguments and config, never a
hardcoded name/path. A new episode = drop a video + write two small JSON files + pick a client
profile. A fresh clone reproduces results with nothing from outside the repo.

1. **Ingest** `ingest.py --file-id <id> --out ~/videos/<proj>/source.mp4` (or drop the file there).
2. **Transcribe** `stt.py ~/videos/<proj>/source.mp4` → `edit/transcript.json` (locked params).
3. **Hooks file** — write `~/videos/<proj>/hooks.json`: `[{"idx","ts","quote","slug"}]`
   (client-supplied hooks; `ts` = TurboScribe segment-start hint, matching is content-first).
4. **Propose** `propose_clips.py edit/transcript.json hooks.json -o proposals_draft.md`
   → Claude hand-curates → send to client → **wait for picks**.
5. **Jobs file** — Claude authors `~/videos/<proj>/jobs.json` from the picks:
   `{"source","client","clips":[{"stem","hook_text","spans":[[a,b],...],"accents":[...],"peak_word"}]}`.
   `client` selects `clients/<client>.yaml` (font/accent/framing/music); multi-hook clips list
   multiple span groups in order; the builder REJECTS any clip whose first span doesn't open with
   `hook_text` (first-line-is-a-hook absolute).
6. **Build** `build_clips.py jobs.json [--only <stem>...]` → per-clip `edit/<stem>_clean.mp4`.
7. **QA** `selfcheck.py <clean.mp4> <job.yaml>` → contact sheet; **Deliver** clean mp4s.
8. **Music (on request)** `music_arc.py <captioned.mp4> <track> --offset O --climax T` (levels from
   the client profile) → full-length story-arc bed cresting at the clip's climax.

Per-client brand lives only in `clients/<name>.yaml` (loaded as `job.style_overrides`); adding a
client = copy `clients/default.yaml`. Judgment (which spans/accents/climax, curation of proposals)
is Claude's; everything the scripts do is mechanical and identical run-to-run.

Canonical transcript schema (both STT paths emit): `{language, duration, segments[],
words:[{word,start,end}]}` — `words` is the flat list `job.yaml:spans` indexes into.

---

## Runbook   ([S] = run a script · [A] = agent judgment)

Let `V=/home/user/videos/<stem>`, `E=$V/edit`.

**0. Bootstrap [S]** — on a fresh sandbox: `bash skills/shorts-pipeline/setup.sh`.

**1. Ingest [A→S]** — [A] Use the Drive MCP (`search_files`/`list_recent_files` on the working
folder) to find the newest video in `Inbox/` and list `Music/`; note file ids/names/sizes. [S]
`ingest.py --file-id <id> --out $V/source.<ext>`. Create `$E/job.yaml` from `job.example.yaml`;
fill `video.*`, the user's `hook.text` (or `hook.from_title: true`), `music`, `notes`.

**2. Transcribe [S]** — `stt.py $V/source.<ext>` → `$E/transcript.json` (+ indexed `.txt`).
Cached. **Never change the STT params** (they fixed a 48s truncation).

**3. Faces + silences [S]** — `faces.py $V/source.<ext> --fps 3` → `face_track.json` +
`cameras.json`; `silences.py $V/source.<ext>` → `silences.json`.

**4. Subject + cameras [A]** — read `cameras.json`. Pick the subject cluster(s): user side-hint >
overlap with speech times > largest/most-covered box. Reject non-subjects (a second person = a
far-off cluster with low `t_coverage`; hands-as-faces are already filtered by the fy/size bounds).
**Two sub-clusters of the same person = the 2-camera case** (e.g. leaned-back vs leaned-forward),
not two people. Write to `job.yaml`: `cameras` and `subject_filter` (fx/fy/w bounds that keep the subject, drop
others). Pick `cameras`: **≤2 named cameras** `{fx,fy,face_w}` for a single locked 2-shot (subject
shifts between a few fixed positions); **`follow`** for a MULTI-CAM source (source cuts between
angles) or general content — per-segment crop centered on the dominant/closest face, tracking the
source's own cuts (widen `subject_filter.w`/`fx` so close-up faces aren't filtered); **`center-crop`**
if faces are unreliable.

**5. Content selection [A]** — read `transcript.txt` (indexed words). Choose kept `spans`
(word-index pairs), **HOOK span first** (match `hook.text`, else pick the strongest opener); add
narrative spans to land in `output.target_len_s` (15–45s). Mark `accents` (power words → neon),
`text_overrides` (ASR fixes), `peak.word_index` (for music), and `protect`/`onset_leads` for quiet
onsets (see playbook).

**6. Compile EDL [S]** — `build_edl.py $E/job.yaml` → `plan.json`. It prints total duration + camera
usage; [A] sanity-check against 15–45s and the [WARN] if outside.

**7. Render base [S]** — `render_vertical.py $E/plan.json --source $V/source.<ext> -o $E/base.mp4`.

**8. Captions [S]** — `captions.py $E/job.yaml` → `master.ass`, `<stem>_captioned.mp4`
(pre-loudnorm, kept for music), and `<stem>_clean.mp4` (loudnorm −14 LUFS) = **deliverable A**.

**9. Self-eval gate [S→A · cap 3 passes]** — `selfcheck.py $E/<stem>_clean.mp4 $E/job.yaml` →
`verify/contact.jpg` (one labeled frame per segment) + trouble report (re-transcribes rendered
audio at span-first / onset-lead / protect words). [A] **Look at both.** Verify: face in the red
zone every frame; clean camera snaps (no mid-lean frames); captions present/styled/not clipped by
the right rail; every trouble word audible + complete. Fixes → edit `job.yaml`, re-run from step 6:
- clipped/late word onset → add/raise `onset_leads[idx]`;
- a quiet word cut as silence → add a `protect` range;
- **transcript text wrong** at a spot → `stt.py --start <t-2> --end <t+2>` on the SOURCE, patch
  those word timings into `transcript.json`, add a `text_overrides` entry. (This is how the "famous
  before" bug was fixed — the full-file pass mis-heard it; isolated re-transcription got it right.)
After 3 passes, deliver with residuals flagged honestly.

**10. Music pick [S→A]** — [S] ingest `Music/` files (gdown) then `music_scan.py $V/music` →
`music_index.json`. [A] choose a track (user hint wins; else vibe from filename/artist knowledge +
tempo/energy fit). Set `job.yaml:music = {track, start_offset}` where
`start_offset = track.drop_time − clip_peak_time` (clip peak = output time of `peak.word_index`,
clamp ≥0). Empty `Music/` → `music_synth.py --duration <len> -o $E/music.wav` (fallback bed).

**11. Music mix [S]** — `music_mix.py $E/<stem>_captioned.mp4 <track> -o $E/<stem>_music.mp4
--offset <start_offset>` = **deliverable B** (ducked + loudnorm). Mix onto the **captioned**
(pre-loudnorm) file, not `_clean`, so the tuned voice/music balance is preserved.

**12. Deliver + persist [A]** — `SendUserFile` both `<stem>_clean.mp4` and `<stem>_music.mp4`
(no Drive upload — base64-through-context is prohibitive). Append a section to `$E/project.md`:
spans chosen + why, cameras, accents, music choice + offset, self-eval findings/fixes, outstanding.

---

## Failure-mode playbook

| Symptom | Cause | Fix |
|---|---|---|
| Word onset clipped (the "S" in "Son") | Whisper start ~0.25s late / quiet onset | `onset_leads[idx]` (never global param changes) |
| Caption word wrong (e.g. "for" vs "famous before") | Full-file pass mis-heard it | `stt.py --start/--end` isolated re-transcribe on SOURCE → patch `transcript.json` timings → `text_overrides` |
| A quiet word gets cut out | silencedetect flagged it as silence | add a `protect` range around it |
| A hand/object appears as the subject | detected as a face | tighten `subject_filter` fy/w bounds |
| Segment spans a lean, subject drifts off | one crop can't cover the move | check camera split on `contact.jpg`; the A/B split handles it — nudge `split_fx` or camera medians |
| Whole section missing from transcript | whisper truncation/skip (unstable on hard audio, even same version) | isolated re-transcribe the region and splice into `transcript.json`; confirm STT params unchanged |
| No reliable faces | b-roll / no clear subject | `cameras: center-crop` (centered 9:16 slice), note it in delivery |

## Scripts (all `uv run --extra pipeline python skills/shorts-pipeline/scripts/<x>.py`)

`ingest.py` · `stt.py` (+`stt_scribe_adapter.py`) · `faces.py` · `silences.py` · `build_edl.py` ·
`render_vertical.py` · `captions.py` · `selfcheck.py` · `music_scan.py` · `music_mix.py` ·
`music_synth.py`. Each prints its own usage with `-h`.
