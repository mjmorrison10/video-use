import { z } from "zod";

// One segment of source footage placed on the output timeline.
export const rangeSchema = z.object({
  inSec: z.number(), // start in the (proxy) source timeline, seconds
  outSec: z.number(), // end in the source timeline, seconds
  offsetSec: z.number(), // where this segment starts on the OUTPUT timeline
  framing: z.enum(["cover", "blur-contain"]).default("cover"),
  beat: z.string().optional(), // HOOK / POINT / etc (informational)
});

// A word-level caption, already re-timed to the OUTPUT timeline (ms).
export const captionSchema = z.object({
  text: z.string(),
  startMs: z.number(),
  endMs: z.number(),
  timestampMs: z.number().nullable().optional(),
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
  highlightColor: z.string().default("#FFD60A"),
  textColor: z.string().default("white"),
  strokeColor: z.string().default("black"),
  fontSize: z.number().default(110),
  captionBottom: z.number().default(430), // px from bottom (TikTok safe-zone)
  uppercase: z.boolean().default(true),
  combineWithinMs: z.number().default(900), // words per caption page window
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
  captions: z.array(captionSchema),
  music: musicSchema.default(null),
  style: styleSchema.default({}),
  hook: hookSchema.default(null),
});

export type ShortProps = z.infer<typeof shortSchema>;
export type Range = z.infer<typeof rangeSchema>;
