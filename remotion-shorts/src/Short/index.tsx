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
  zoomSteps: ShortProps["zoomSteps"];
  fps: number;
  children: React.ReactNode;
}> = ({ zooms, zoomSteps, fps, children }) => {
  const frame = useCurrentFrame();
  let scale = 1;
  // punch-in/out zooms
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
  // cumulative staircase zoom: snap to the active step's scale and hold
  const steps = (zoomSteps ?? []).slice().sort((a, b) => a.atSec - b.atSec);
  let active = -1;
  for (let i = 0; i < steps.length; i++) if (frame >= steps[i].atSec * fps) active = i;
  if (active >= 0) {
    const t = steps[active].atSec * fps;
    const prev = active > 0 ? steps[active - 1].scale : 1;
    const ease = interpolate(frame, [t, t + Math.round(fps * 0.09)], [prev, steps[active].scale], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    scale = Math.max(scale, ease);
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
      {(cta.lines ?? []).map((line, i, arr) => {
        const isAsk = i === arr.length - 1; // the ask gets the accent + glow
        return (
          <div
            key={i}
            style={{
              fontFamily: ctaFontFamily,
              color: isAsk ? style.accentColor : "white",
              fontSize: isAsk ? 48 : 44,
              marginTop: i === 0 ? 40 : 18,
              textAlign: "center",
              opacity: isAsk ? 1 : 0.92,
              textShadow: isAsk
                ? `0 0 16px ${style.accentColor}, 0 0 38px ${style.accentColor}`
                : undefined,
            }}
          >
            {line}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const Segment: React.FC<{
  videoSrc: string;
  inSec: number;
  outSec: number;
  framing: string;
  cropX: number;
  cropXEnd: number | null;
  cropPanSec: number | null;
  durFrames: number;
  mute: boolean;
  fps: number;
}> = ({ videoSrc, inSec, outSec, framing, cropX, cropXEnd, cropPanSec, durFrames, mute, fps }) => {
  const trimBefore = Math.round(inSec * fps);
  const trimAfter = Math.round(outSec * fps);
  const src = staticFile(videoSrc);
  const segFrame = useCurrentFrame();
  const cx =
    cropXEnd == null
      ? cropX
      : interpolate(segFrame, [0, Math.max(1, cropPanSec != null ? Math.round(cropPanSec * fps) : durFrames)], [cropX, cropXEnd], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

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
        style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: `${cx * 100}% 50%` }}
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
  zoomSteps,
  cta,
  voiceovers,
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
      <ZoomLayer zooms={zooms} zoomSteps={zoomSteps} fps={fps}>
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
                cropXEnd={r.cropXEnd ?? null}
                cropPanSec={r.cropPanSec ?? null}
                durFrames={dur}
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
        // The end card fades in, so a caption still on screen shows THROUGH it
        // for the length of the fade. Captions stop where the card starts.
        const ctaStartFrame = cta
          ? Math.round((cta.atSec ?? contentEnd) * fps)
          : Number.POSITIVE_INFINITY;
        const next = captionPages[index + 1] ?? null;
        const startFrame = (page.startMs / 1000) * fps;
        // Hold each page a beat past its own words so captions don't flicker in
        // the micro-gaps of continuous speech — but no further. Running all the
        // way to the next page keeps a caption on screen across real silence,
        // so the last line of a section bleeds over whatever follows it.
        const holdFrame = (page.endMs / 1000) * fps + fps * 0.35;
        const endFrame = Math.min(
          next ? Math.min((next.startMs / 1000) * fps, holdFrame) : holdFrame,
          ctaStartFrame,
        );
        if (endFrame <= startFrame) return null;
        const dur = Math.max(1, endFrame - startFrame);
        return (
          <Sequence key={`cap-${index}`} from={startFrame} durationInFrames={dur}>
            <CaptionPage page={page} style={style} />
          </Sequence>
        );
      })}

      {hook ? <HookOverlay hook={hook} style={style} fps={fps} /> : null}

      {cta ? (
        <Sequence from={Math.round((cta.atSec ?? contentEnd) * fps)} durationInFrames={Math.max(1, Math.round(cta.durSec * fps))} name="cta">
          <CTACard cta={cta} style={style} />
        </Sequence>
      ) : null}

      {(voiceovers ?? []).map((v, i) => (
        <Sequence key={`vo-${i}`} from={Math.round(v.atSec * fps)} name={`vo:${v.src}`}>
          <Audio src={staticFile(v.src)} volume={v.volume ?? 1} />
        </Sequence>
      ))}

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
