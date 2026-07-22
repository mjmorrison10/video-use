import { fitText } from "@remotion/layout-utils";
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { PowerFont } from "../load-font";
import type { ShortProps } from "./schema";

const fontFamily = `${PowerFont}, "FontFallback", serif`;

// A big centered hook headline burned over the first `untilSec` seconds,
// fading out at the end. Reinforces the spoken hook for silent autoplay.
export const HookOverlay: React.FC<{
  readonly hook: NonNullable<ShortProps["hook"]>;
  readonly style: ShortProps["style"];
  readonly fps: number;
}> = ({ hook, style }) => {
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();
  const untilFrame = hook.untilSec * fps;

  if (frame > untilFrame) return null;

  const opacity = interpolate(
    frame,
    [0, 6, untilFrame - 8, untilFrame],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const fitted = fitText({
    fontFamily,
    text: hook.text,
    withinWidth: width * 0.86,
    textTransform: "uppercase",
  });
  const fontSize = Math.min(130, fitted.fontSize);

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-start",
        alignItems: "center",
        paddingTop: 260,
        opacity,
      }}
    >
      <div
        style={{
          fontSize,
          color: style.accentColor,
          WebkitTextStroke: `18px ${style.strokeColor}`,
          paintOrder: "stroke",
          fontFamily,
          textTransform: "uppercase",
          textAlign: "center",
          padding: "0 40px",
          lineHeight: 1.02,
          textShadow: `0 0 10px ${style.accentColor}, 0 0 26px ${style.accentColor}, 0 6px 28px rgba(0,0,0,0.55)`,
        }}
      >
        {hook.text}
      </div>
    </AbsoluteFill>
  );
};
