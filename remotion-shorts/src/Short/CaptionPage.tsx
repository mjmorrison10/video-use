import { makeTransform, scale, translateY } from "@remotion/animation-utils";
import { TikTokPage } from "@remotion/captions";
import { fitText } from "@remotion/layout-utils";
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { PowerSerif } from "../load-font";
import type { ShortProps } from "./schema";

const fontFamily = `${PowerSerif}, "SerifFallback", serif`;

const clean = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .trim();

export const CaptionPage: React.FC<{
  readonly page: TikTokPage;
  readonly style: ShortProps["style"];
}> = ({ page, style }) => {
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 6 });

  const textTransform = style.uppercase ? "uppercase" : "none";
  const fitted = fitText({
    fontFamily,
    text: page.text,
    withinWidth: width * 0.86,
    textTransform,
  });
  const fontSize = Math.min(style.fontSize, fitted.fontSize);

  const powerSet = new Set((style.powerWords ?? []).map(clean));

  const container: React.CSSProperties =
    style.captionPosition === "bottom"
      ? {
          justifyContent: "center",
          alignItems: "center",
          top: undefined,
          bottom: style.captionBottom,
          height: 260,
          padding: "0 60px",
          textAlign: "center",
        }
      : {
          justifyContent: "center",
          alignItems: "center",
          padding: "0 60px",
          textAlign: "center",
        };

  return (
    <AbsoluteFill style={container}>
      <div
        style={{
          fontSize,
          color: style.textColor,
          WebkitTextStroke: `16px ${style.strokeColor}`,
          paintOrder: "stroke",
          transform: makeTransform([
            scale(interpolate(enter, [0, 1], [0.9, 1])),
            translateY(interpolate(enter, [0, 1], [30, 0])),
          ]),
          fontFamily,
          textTransform,
          lineHeight: 1.08,
          textShadow: "0 6px 28px rgba(0,0,0,0.55)",
        }}
      >
        {page.tokens.map((t) => {
          const isPower = powerSet.has(clean(t.text));
          return (
            <span
              key={t.fromMs}
              style={{
                display: "inline",
                whiteSpace: "pre",
                color: isPower ? style.accentColor : style.textColor,
              }}
            >
              {t.text}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
