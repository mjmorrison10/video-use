import { z } from "zod";

// One segment of source footage placed on the output timeline.
export const rangeSchema = z.object({
  inSec: z.number(), // start in the (proxy) source timeline, seconds
  outSec: z.number(), // end in the source timeline, seconds
  offsetSec: z.number(), // where this segment starts on the OUTPUT timeline
  framing: z.enum(["cover", "blur-contain"]).default("cover"),
  cropX: z.number().default(0.5), // horizontal crop bias for cover (0=left, .5=center, 1=right)
  cropXEnd: z.number().nullable().default(null), // if set, pan crop from cropX -> cropXEnd
  cropPanSec: z.number().nullable().default(null), // seconds to complete the pan, then hold (default: whole segment)
  mute: z.boolean().default(false), // drop this segment's audio (censor)
  beat: z.string().optional(), // HOOK / POINT / etc (informational)
});

// A caption "page" = one on-screen line of 2-3 words, output-timed (ms).
export const captionTokenSchema = z.object({ text: z.string() });
export const captionPageSchema = z.object({
  startMs: z.number(),
  endMs: z.number(),
  tokens: z.array(captionTokenSchema),
});

export const musicSchema = z
  .object({
    src: z.string(), // filename in public/
    startSec: z.number().default(0), // trim into the track
    volLow: z.number().default(0.06),
    volHigh: z.number().default(0.12),
    climaxSec: z.number().nullable().default(null),
  })
  .nullable();

export const styleSchema = z.object({
  highlightColor: z.string().default("#00E5FF"), // legacy karaoke color (unused in center mode)
  accentColor: z.string().default("#00E5FF"), // yellow for power words + hook
  textColor: z.string().default("white"),
  strokeColor: z.string().default("black"),
  fontSize: z.number().default(58),
  captionPosition: z.enum(["center", "bottom"]).default("center"),
  captionBottom: z.number().default(430), // px from bottom when captionPosition="bottom"
  uppercase: z.boolean().default(true),
  // Words rendered in accentColor (and kept lit). Lowercased, punctuation-insensitive.
  powerWords: z.array(z.string()).default([]),
});

export const hookSchema = z
  .object({
    text: z.string(),
    untilSec: z.number().default(2.5),
  })
  .nullable();

// A brief B-roll cutaway overlaid on the speaker at a keyword moment. Output-timed.
// The speaker's audio keeps playing underneath (broll is muted); captions stay on top.
export const brollSchema = z.object({
  src: z.string(), // filename in public/
  atSec: z.number(), // output-timeline start (seconds)
  durSec: z.number().default(1.8), // how long the cutaway holds
  trimBefore: z.number().default(0), // trim into the b-roll source (seconds)
  framing: z.enum(["cover", "blur-contain"]).default("cover"),
  label: z.string().optional(), // the keyword it matched (informational)
});

// A fast punch-in zoom at a keyword moment (e.g. each "bang"), output-timed.
export const zoomSchema = z.object({
  atSec: z.number(), // output-timeline moment to punch in
  durSec: z.number().default(0.45), // total in+out duration of the punch
  scale: z.number().default(1.18), // peak zoom
});

// A cumulative "staircase" zoom step — each step snaps to `scale` and HOLDS until
// the next step (e.g. +10% on every "bang"). Applied on top of the video layer.
export const zoomStepSchema = z.object({
  atSec: z.number(),
  scale: z.number(), // absolute target scale from this step onward
});

// A call-to-action end card appended after the content (black screen + text).
export const ctaSchema = z
  .object({
    text: z.string(),
    durSec: z.number().default(2),
    // Where the card starts on the OUTPUT timeline. Default (null) = straight
    // after the last footage range, which is wrong whenever something else
    // closes the video (a voiceover bookend, a held beat) — set it explicitly then.
    atSec: z.number().nullable().default(null),
    sub: z.string().optional(), // optional smaller line under the main text
    // Further lines under `sub`, e.g. a payoff line then the actual ask. The
    // LAST entry renders in accentColor because it is the thing being asked for.
    lines: z.array(z.string()).default([]),
  })
  .nullable();

// A narration stem laid over the timeline (VO bookends). The speaker's own
// audio is muted on those ranges, so this carries the section entirely.
export const voiceoverSchema = z.object({
  src: z.string(),        // filename in public/
  atSec: z.number(),      // output-timeline start
  volume: z.number().default(1),
});

export const shortSchema = z.object({
  videoSrc: z.string(), // filename in public/ (proxy)
  fps: z.number().default(30),
  ranges: z.array(rangeSchema),
  captionPages: z.array(captionPageSchema),
  music: musicSchema.default(null),
  style: styleSchema.default({}),
  hook: hookSchema.default(null),
  broll: z.array(brollSchema).default([]),
  zooms: z.array(zoomSchema).default([]),
  zoomSteps: z.array(zoomStepSchema).default([]),
  cta: ctaSchema.default(null),
  voiceovers: z.array(voiceoverSchema).default([]),
});

export type ShortProps = z.infer<typeof shortSchema>;
export type Range = z.infer<typeof rangeSchema>;
export type CaptionPageT = z.infer<typeof captionPageSchema>;
