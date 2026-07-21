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
import type { Range, ShortProps } from "./schema";

loadFont();

// Interpolate the face-tracking pan track at the current segment-local frame.
// Returns a CSS object-position string. Falls back to centered (50% 50%).
const usePanPosition = (focus: Range["focus"]): string => {
  const frame = useCurrentFrame();
  if (!focus || focus.length === 0) return "50% 50%";
  if (focus.length === 1) {
    return `${focus[0].px * 100}% ${focus[0].py * 100}%`;
  }
  const frames = focus.map((k) => k.f);
  const px = interpolate(
    frame,
    frames,
    focus.map((k) => k.px),
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const py = interpolate(
    frame,
    frames,
    focus.map((k) => k.py),
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return `${px * 100}% ${py * 100}%`;
};

// Output canvas + the split bands (person on top, info/graphic on bottom).
const OUT_W = 1080;
const OUT_H = 1920;
const SPLIT_TOP_H = 1040; // person band height
const SRC_AR = 16 / 9;

type Rect = { x: number; y: number; w: number; h: number };

// Map a source sub-rectangle (0..1 fractions of the 16:9 frame) into a box,
// COVER or CONTAIN, without distortion (uniform scale + centering).
const SourceCrop: React.FC<{
  src: string;
  trimBefore: number;
  trimAfter: number;
  muted: boolean;
  boxTop: number;
  boxW: number;
  boxH: number;
  rect: Rect;
  fit: "cover" | "contain";
  bg?: string;
}> = ({ src, trimBefore, trimAfter, muted, boxTop, boxW, boxH, rect, fit, bg }) => {
  const iwForW = boxW / rect.w;
  const iwForH = boxH / (rect.h / SRC_AR);
  const IW = fit === "cover" ? Math.max(iwForW, iwForH) : Math.min(iwForW, iwForH);
  const IH = IW / SRC_AR;
  const tx = boxW / 2 - (rect.x + rect.w / 2) * IW;
  const ty = boxH / 2 - (rect.y + rect.h / 2) * IH;
  return (
    <div
      style={{
        position: "absolute",
        top: boxTop,
        left: 0,
        width: boxW,
        height: boxH,
        overflow: "hidden",
        backgroundColor: bg ?? "black",
      }}
    >
      <OffthreadVideo
        src={src}
        trimBefore={trimBefore}
        trimAfter={trimAfter}
        muted={muted}
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: IW,
          height: IH,
          transform: `translate(${tx}px, ${ty}px)`,
          maxWidth: "none",
        }}
      />
    </div>
  );
};

const Segment: React.FC<{
  videoSrc: string;
  inSec: number;
  outSec: number;
  framing: string;
  mute: boolean;
  fps: number;
  focus: Range["focus"];
  zoom: number;
  pip?: Rect;
  info?: Rect;
  splitBg?: string;
}> = ({ videoSrc, inSec, outSec, framing, mute, fps, focus, zoom, pip, info, splitBg }) => {
  const trimBefore = Math.round(inSec * fps);
  const trimAfter = Math.round(outSec * fps);
  const src = staticFile(videoSrc);
  const objectPosition = usePanPosition(focus);

  // Split: person (PIP) COVER in the top band, info/graphic CONTAIN in the bottom.
  if (framing === "split" && pip && info) {
    return (
      <AbsoluteFill style={{ backgroundColor: splitBg ?? "black" }}>
        <SourceCrop
          src={src}
          trimBefore={trimBefore}
          trimAfter={trimAfter}
          muted={mute}
          boxTop={0}
          boxW={OUT_W}
          boxH={SPLIT_TOP_H}
          rect={pip}
          fit="cover"
        />
        <SourceCrop
          src={src}
          trimBefore={trimBefore}
          trimAfter={trimAfter}
          muted
          boxTop={SPLIT_TOP_H}
          boxW={OUT_W}
          boxH={OUT_H - SPLIT_TOP_H}
          rect={info}
          fit="contain"
          bg={splitBg ?? "#ffffff"}
        />
      </AbsoluteFill>
    );
  }

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
    <AbsoluteFill style={{ backgroundColor: "black", overflow: "hidden" }}>
      <OffthreadVideo
        src={src}
        trimBefore={trimBefore}
        trimAfter={trimAfter}
        muted={mute}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition,
          // Extra zoom toward the focal point (fills the frame on composed shots).
          ...(zoom && zoom !== 1
            ? { transform: `scale(${zoom})`, transformOrigin: objectPosition }
            : {}),
        }}
      />
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
              focus={r.focus}
              zoom={r.zoom}
              pip={r.pip}
              info={r.info}
              splitBg={r.splitBg}
            />
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
