import { z } from "zod";

// One keyframe of the face-tracking pan: at segment-local output frame `f`,
// place the crop at CSS object-position (px, py) in 0..1 (already cover-adjusted).
export const focusKeyframeSchema = z.object({
  f: z.number(),
  px: z.number(),
  py: z.number(),
});

// A source sub-rectangle in 0..1 fractions (of the 16:9 source frame).
export const rectSchema = z.object({
  x: z.number(),
  y: z.number(),
  w: z.number(),
  h: z.number(),
});

// One segment of source footage placed on the output timeline.
export const rangeSchema = z.object({
  inSec: z.number(), // start in the (proxy) source timeline, seconds
  outSec: z.number(), // end in the source timeline, seconds
  offsetSec: z.number(), // where this segment starts on the OUTPUT timeline
  framing: z.enum(["cover", "blur-contain", "split"]).default("cover"),
  mute: z.boolean().default(false), // drop this segment's audio (censor)
  beat: z.string().optional(), // HOOK / POINT / etc (informational)
  // Face-aware pan track (segment-local frames). Empty = static center crop.
  focus: z.array(focusKeyframeSchema).default([]),
  // Extra zoom on top of cover (1 = none). >1 crops tighter toward the focal
  // point — e.g. to fill the frame on a composed graphic and hide its margins.
  zoom: z.number().default(1),
  // framing="split": person (PIP) crop shown COVER in the top band, info/graphic
  // crop shown CONTAIN in the bottom band. Rects are source-frame fractions.
  pip: rectSchema.optional(),
  info: rectSchema.optional(),
  splitBg: z.string().optional(), // bottom-band background (match the graphic)
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
  highlightColor: z.string().default("#FFD60A"), // legacy karaoke color (unused in center mode)
  accentColor: z.string().default("#FFD60A"), // yellow for power words + hook
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

export const shortSchema = z.object({
  videoSrc: z.string(), // filename in public/ (proxy)
  fps: z.number().default(30),
  ranges: z.array(rangeSchema),
  captionPages: z.array(captionPageSchema),
  music: musicSchema.default(null),
  style: styleSchema.default({}),
  hook: hookSchema.default(null),
});

export type ShortProps = z.infer<typeof shortSchema>;
export type Range = z.infer<typeof rangeSchema>;
export type CaptionPageT = z.infer<typeof captionPageSchema>;
