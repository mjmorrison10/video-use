import React from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
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
  mute: boolean;
  fps: number;
}> = ({ videoSrc, inSec, outSec, framing, mute, fps }) => {
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
            muted={mute}
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
        muted={mute}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};

const Broll: React.FC<{
  src: string;
  trimBefore: number;
  framing: string;
  fps: number;
  durFrames: number;
}> = ({ src, trimBefore, framing, fps, durFrames }) => {
  const frame = useCurrentFrame();
  const fade = Math.round(fps * 0.12);
  const opacity = interpolate(
    frame,
    [0, fade, durFrames - fade, durFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const source = staticFile(src);
  const tb = Math.round(trimBefore * fps);
  return (
    <AbsoluteFill style={{ opacity, backgroundColor: "black" }}>
      {framing === "blur-contain" ? (
        <>
          <OffthreadVideo src={source} trimBefore={tb} muted style={{ width: "100%", height: "100%", objectFit: "cover", filter: "blur(40px) brightness(0.5)", transform: "scale(1.15)" }} />
          <AbsoluteFill style={{ justifyContent: "center" }}>
            <OffthreadVideo src={source} trimBefore={tb} muted style={{ width: "100%", height: "auto", objectFit: "contain" }} />
          </AbsoluteFill>
        </>
      ) : (
        <OffthreadVideo src={source} trimBefore={tb} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      )}
    </AbsoluteFill>
  );
};

export const Short: React.FC<ShortProps> = ({
  videoSrc,
  ranges,
  captionPages,
  music,
  style,
  hook,
  broll,
}) => {
  const { fps, durationInFrames } = useVideoConfig();

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
              mute={r.mute}
              fps={fps}
            />
          </Sequence>
        );
      })}

      {(broll ?? []).map((b, i) => {
        const from = Math.round(b.atSec * fps);
        const durFrames = Math.max(1, Math.round(b.durSec * fps));
        return (
          <Sequence key={`broll-${i}`} from={from} durationInFrames={durFrames} name={`broll:${b.label ?? b.src}`}>
            <Broll src={b.src} trimBefore={b.trimBefore} framing={b.framing} fps={fps} durFrames={durFrames} />
          </Sequence>
        );
      })}

      {captionPages.map((page, index) => {
        const next = captionPages[index + 1] ?? null;
        const startFrame = (page.startMs / 1000) * fps;
        const endFrame = next
          ? (next.startMs / 1000) * fps
          : (page.endMs / 1000) * fps + fps * 0.4;
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
