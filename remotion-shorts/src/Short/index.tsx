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
  grade?: string;
}> = ({ src, trimBefore, trimAfter, muted, boxTop, boxW, boxH, rect, fit, bg, grade }) => {
  const iwForW = boxW / rect.w;
  const iwForH = boxH / (rect.h / SRC_AR);
  const IW = fit === "cover" ? Math.max(iwForW, iwForH) : Math.min(iwForW, iwForH);
  const IH = IW / SRC_AR;
  // The rect's rendered size in box px. For CONTAIN it fits inside the box, so
  // the visible "window" must be exactly the rect (bg shows around it) — else the
  // source pixels ADJACENT to the rect leak into the letterbox. For COVER the
  // window is the whole box and the overflow is clipped.
  const rW = rect.w * IW;
  const rH = rect.h * IH;
  const winW = fit === "cover" ? boxW : Math.min(rW, boxW);
  const winH = fit === "cover" ? boxH : Math.min(rH, boxH);
  const winLeft = (boxW - winW) / 2;
  const winTop = (boxH - winH) / 2;
  // Position the video inside the window: center the rect (cover) or align the
  // rect's top-left to the window (contain).
  const vx = fit === "cover" ? winW / 2 - (rect.x + rect.w / 2) * IW : -rect.x * IW;
  const vy = fit === "cover" ? winH / 2 - (rect.y + rect.h / 2) * IH : -rect.y * IH;
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
      <div
        style={{
          position: "absolute",
          top: winTop,
          left: winLeft,
          width: winW,
          height: winH,
          overflow: "hidden",
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
            transform: `translate(${vx}px, ${vy}px)`,
            maxWidth: "none",
            filter: grade,
          }}
        />
      </div>
    </div>
  );
};

// Crossfade length (frames) between consecutive segments.
const FADE = 7;

type BRollT = { src: string; startSec: number; kenburns: number };

// Full-frame B-ROLL: an external clip cover-cropped to fill 9:16, with a slow
// Ken-Burns push so it never feels like a frozen still. Muted — narration audio
// comes from the separate audio track in <Short>.
const BRoll: React.FC<{
  broll: BRollT;
  fps: number;
  xfLead: number;
  durFrames: number;
  grade?: string;
}> = ({ broll, fps, xfLead, durFrames, grade }) => {
  const frame = useCurrentFrame();
  const endScale = broll.kenburns ?? 1.08;
  const scale = interpolate(frame, [0, Math.max(1, durFrames)], [1, endScale], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const startFrame = Math.max(0, Math.round((broll.startSec || 0) * fps) - xfLead);
  return (
    <AbsoluteFill style={{ backgroundColor: "black", overflow: "hidden" }}>
      <OffthreadVideo
        src={staticFile(broll.src)}
        trimBefore={startFrame}
        muted
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: "50% 50%",
          transform: `scale(${scale})`,
          filter: grade,
        }}
      />
    </AbsoluteFill>
  );
};

const Segment: React.FC<{
  videoSrc: string;
  inSec: number;
  outSec: number;
  framing: string;
  fps: number;
  focus: Range["focus"];
  zoom: number;
  pip?: Rect;
  info?: Rect;
  splitBg?: string;
  grade?: string;
  crop?: Rect;
  splitTop?: number;
  broll?: BRollT;
  xfLead: number; // frames this segment starts EARLY to overlap the previous one
  durFrames: number; // full sequence length (incl. the lead)
}> = ({ videoSrc, inSec, outSec, framing, fps, focus, zoom, pip, info, splitBg, grade, crop, splitTop, broll, xfLead, durFrames }) => {
  const frame = useCurrentFrame();
  // Crossfade in over the overlap with the previous segment (or a clean open on
  // the first segment). Video is always muted; audio is a separate track.
  const opacity = interpolate(frame, [0, FADE], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const trimBefore = Math.max(0, Math.round(inSec * fps) - xfLead);
  const trimAfter = Math.round(outSec * fps);
  const src = staticFile(videoSrc);
  const objectPosition = usePanPosition(focus);

  let content: React.ReactNode;

  if (broll) {
    content = <BRoll broll={broll} fps={fps} xfLead={xfLead} durFrames={durFrames} grade={grade} />;
  } else if (framing === "split" && pip && info) {
    // Split: person (PIP) COVER in the top band, info/graphic CONTAIN in the bottom.
    const topH = splitTop ? Math.round(splitTop * OUT_H) : SPLIT_TOP_H;
    content = (
      <AbsoluteFill style={{ backgroundColor: splitBg ?? "black" }}>
        <SourceCrop src={src} trimBefore={trimBefore} trimAfter={trimAfter} muted boxTop={0} boxW={OUT_W} boxH={topH} rect={pip} fit="cover" grade={grade} />
        <SourceCrop src={src} trimBefore={trimBefore} trimAfter={trimAfter} muted boxTop={topH} boxW={OUT_W} boxH={OUT_H - topH} rect={info} fit="contain" bg={splitBg ?? "#ffffff"} grade={grade} />
      </AbsoluteFill>
    );
  } else if (framing === "blur-contain") {
    // Legacy path (kept for old job.jsons). New clips use B-roll or cover.
    content = (
      <AbsoluteFill style={{ backgroundColor: "black" }}>
        <AbsoluteFill>
          <OffthreadVideo src={src} trimBefore={trimBefore} trimAfter={trimAfter} muted style={{ width: "100%", height: "100%", objectFit: "cover", filter: "blur(40px) brightness(0.5)", transform: "scale(1.15)" }} />
        </AbsoluteFill>
        {crop ? (
          <SourceCrop src={src} trimBefore={trimBefore} trimAfter={trimAfter} muted boxTop={0} boxW={OUT_W} boxH={OUT_H} rect={crop} fit="contain" bg="transparent" grade={grade} />
        ) : (
          <AbsoluteFill style={{ justifyContent: "center" }}>
            <OffthreadVideo src={src} trimBefore={trimBefore} trimAfter={trimAfter} muted style={{ width: "100%", height: "auto", objectFit: "contain", filter: grade }} />
          </AbsoluteFill>
        )}
      </AbsoluteFill>
    );
  } else if (framing === "cover" && crop) {
    // Cover with an explicit source crop (drop a burned-in caption band, isolate
    // a subject from a composite).
    content = (
      <AbsoluteFill style={{ backgroundColor: "black" }}>
        <SourceCrop src={src} trimBefore={trimBefore} trimAfter={trimAfter} muted boxTop={0} boxW={OUT_W} boxH={OUT_H} rect={crop} fit="cover" grade={grade} />
      </AbsoluteFill>
    );
  } else {
    content = (
      <AbsoluteFill style={{ backgroundColor: "black", overflow: "hidden" }}>
        <OffthreadVideo
          src={src}
          trimBefore={trimBefore}
          trimAfter={trimAfter}
          muted
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition,
            filter: grade,
            ...(zoom && zoom !== 1 ? { transform: `scale(${zoom})`, transformOrigin: objectPosition } : {}),
          }}
        />
      </AbsoluteFill>
    );
  }

  return <AbsoluteFill style={{ opacity }}>{content}</AbsoluteFill>;
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
      {/* VIDEO layer — each segment crossfades into the next (starts FADE frames
          early and fades its opacity in). All video is muted. */}
      {ranges.map((r, i) => {
        const offset = Math.round(r.offsetSec * fps);
        const dur = Math.max(1, Math.round((r.outSec - r.inSec) * fps));
        const xfLead = i > 0 ? FADE : 0;
        return (
          <Sequence key={i} from={offset - xfLead} durationInFrames={dur + xfLead} name={r.beat ?? `seg-${i}`}>
            <Segment
              videoSrc={videoSrc}
              inSec={r.inSec}
              outSec={r.outSec}
              framing={r.framing}
              fps={fps}
              focus={r.focus}
              zoom={r.zoom}
              pip={r.pip}
              info={r.info}
              splitBg={r.splitBg}
              grade={style.grade}
              crop={r.crop}
              splitTop={r.splitTop}
              broll={r.broll}
              xfLead={xfLead}
              durFrames={dur + xfLead}
            />
          </Sequence>
        );
      })}

      {/* AUDIO layer — the creator's narration for each segment, hard-cut (no
          crossfade), independent of the video so B-roll can cover freely. */}
      {ranges.map((r, i) => {
        if (r.mute) return null;
        const offset = Math.round(r.offsetSec * fps);
        const dur = Math.max(1, Math.round((r.outSec - r.inSec) * fps));
        return (
          <Sequence key={`aud-${i}`} from={offset} durationInFrames={dur}>
            <Audio
              src={staticFile(videoSrc)}
              trimBefore={Math.round(r.inSec * fps)}
              trimAfter={Math.round(r.outSec * fps)}
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
