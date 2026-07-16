import { Caption, createTikTokStyleCaptions } from "@remotion/captions";
import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useVideoConfig,
} from "remotion";
import { loadFont } from "../load-font";
import { CaptionPage } from "./CaptionPage";
import { HookOverlay } from "./HookOverlay";
import type { ShortProps } from "./schema";

loadFont();

const Segment: React.FC<{
  videoSrc: string;
  inSec: number;
  outSec: number;
  framing: string;
  fps: number;
}> = ({ videoSrc, inSec, outSec, framing, fps }) => {
  const trimBefore = Math.round(inSec * fps);
  const trimAfter = Math.round(outSec * fps);
  const src = staticFile(videoSrc);

  if (framing === "blur-contain") {
    return (
      <AbsoluteFill style={{ backgroundColor: "black" }}>
        <AbsoluteFill>
          <OffthreadVideo
            src={src}
            trimBefore={trimBefore}
            trimAfter={trimAfter}
            muted
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "blur(40px) brightness(0.5)",
              transform: "scale(1.15)",
            }}
          />
        </AbsoluteFill>
        <AbsoluteFill style={{ justifyContent: "center" }}>
          <OffthreadVideo
            src={src}
            trimBefore={trimBefore}
            trimAfter={trimAfter}
            style={{ width: "100%", height: "auto", objectFit: "contain" }}
          />
        </AbsoluteFill>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <OffthreadVideo
        src={src}
        trimBefore={trimBefore}
        trimAfter={trimAfter}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

export const Short: React.FC<ShortProps> = ({
  videoSrc,
  ranges,
  captions,
  music,
  style,
  hook,
}) => {
  const { fps, durationInFrames } = useVideoConfig();

  const captionInput: Caption[] = useMemo(
    () =>
      captions.map((c) => ({
        text: c.text,
        startMs: c.startMs,
        endMs: c.endMs,
        timestampMs: c.timestampMs ?? (c.startMs + c.endMs) / 2,
        confidence: null,
      })),
    [captions],
  );

  const { pages } = useMemo(
    () =>
      createTikTokStyleCaptions({
        captions: captionInput,
        combineTokensWithinMilliseconds: style.combineWithinMs,
      }),
    [captionInput, style.combineWithinMs],
  );

  const musicVolume = (frame: number) => {
    if (!music) return 0;
    const climaxFrame =
      music.climaxSec == null ? durationInFrames / 2 : music.climaxSec * fps;
    return interpolate(
      frame,
      [0, climaxFrame, durationInFrames],
      [music.volLow, music.volHigh, music.volLow],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
    );
  };

  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {ranges.map((r, i) => {
        const from = Math.round(r.offsetSec * fps);
        const dur = Math.max(1, Math.round((r.outSec - r.inSec) * fps));
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={r.beat ?? `seg-${i}`}>
            <Segment
              videoSrc={videoSrc}
              inSec={r.inSec}
              outSec={r.outSec}
              framing={r.framing}
              fps={fps}
            />
          </Sequence>
        );
      })}

      {pages.map((page, index) => {
        const nextPage = pages[index + 1] ?? null;
        const startFrame = (page.startMs / 1000) * fps;
        const endFrame = nextPage
          ? (nextPage.startMs / 1000) * fps
          : startFrame + (style.combineWithinMs / 1000) * fps + fps;
        const dur = Math.max(1, endFrame - startFrame);
        return (
          <Sequence key={`cap-${index}`} from={startFrame} durationInFrames={dur}>
            <CaptionPage page={page} style={style} />
          </Sequence>
        );
      })}

      {hook ? <HookOverlay hook={hook} style={style} fps={fps} /> : null}

      {music ? (
        <Audio
          src={staticFile(music.src)}
          trimBefore={Math.round(music.startSec * fps)}
          volume={musicVolume}
        />
      ) : null}
    </AbsoluteFill>
  );
};
