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
import { loadFont, PowerFont } from "../load-font";
import { CaptionPage } from "./CaptionPage";
import { HookOverlay } from "./HookOverlay";
import type { ShortProps } from "./schema";

loadFont();

const ctaFontFamily = `${PowerFont}, "FontFallback", serif`;

// Fast punch-in zoom on the speaker at each keyword moment (e.g. every "bang").
const ZoomLayer: React.FC<{
  zooms: ShortProps["zooms"];
  fps: number;
  children: React.ReactNode;
}> = ({ zooms, fps, children }) => {
  const frame = useCurrentFrame();
  let scale = 1;
  for (const z of zooms ?? []) {
    const start = z.atSec * fps;
    const peak = start + Math.max(1, Math.round(fps * 0.07));
    const end = start + Math.max(2, Math.round(z.durSec * fps));
    if (frame >= start && frame <= end) {
      const s =
        frame <= peak
          ? interpolate(frame, [start, peak], [1, z.scale], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
          : interpolate(frame, [peak, end], [z.scale, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
      scale = Math.max(scale, s);
    }
  }
  return (
    <AbsoluteFill style={{ transform: `scale(${scale})`, transformOrigin: "50% 40%" }}>
      {children}
    </AbsoluteFill>
  );
};

const CTACard: React.FC<{ cta: NonNullable<ShortProps["cta"]>; style: ShortProps["style"] }> = ({ cta, style }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: "black", justifyContent: "center", alignItems: "center", padding: "0 80px", opacity }}>
      <div style={{ fontFamily: ctaFontFamily, color: style.accentColor, textAlign: "center", fontSize: 86, textTransform: "uppercase", WebkitTextStroke: "3px black", paintOrder: "stroke", textShadow: `0 0 20px ${style.accentColor}, 0 0 44px ${style.accentColor}`, lineHeight: 1.12 }}>
        {cta.text}
      </div>
      {cta.sub ? (
        <div style={{ fontFamily: ctaFontFamily, color: "white", fontSize: 46, marginTop: 34, textAlign: "center", opacity: 0.9 }}>{cta.sub}</div>
      ) : null}
    </AbsoluteFill>
  );
};

const Segment: React.FC<{
  videoSrc: string;
  inSec: number;
  outSec: number;
  framing: string;
  cropX: number;
  mute: boolean;
  fps: number;
}> = ({ videoSrc, inSec, outSec, framing, cropX, mute, fps }) => {
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
        style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: `${cropX * 100}% 50%` }}
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
  zooms,
  cta,
}) => {
  const { fps, durationInFrames } = useVideoConfig();
  const contentEnd = ranges.reduce((acc, r) => Math.max(acc, r.offsetSec + (r.outSec - r.inSec)), 0);

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
      <ZoomLayer zooms={zooms} fps={fps}>
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
                cropX={r.cropX ?? 0.5}
                mute={r.mute}
                fps={fps}
              />
            </Sequence>
          );
        })}
      </ZoomLayer>

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

      {cta ? (
        <Sequence from={Math.round(contentEnd * fps)} durationInFrames={Math.max(1, Math.round(cta.durSec * fps))} name="cta">
          <CTACard cta={cta} style={style} />
        </Sequence>
      ) : null}

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
