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
import { TheBoldFont } from "../load-font";
import type { ShortProps } from "./schema";

const fontFamily = TheBoldFont;

export const CaptionPage: React.FC<{
  readonly page: TikTokPage;
  readonly style: ShortProps["style"];
}> = ({ page, style }) => {
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();
  const timeInMs = (frame / fps) * 1000;

  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 5 });

  const textTransform = style.uppercase ? "uppercase" : "none";
  const fitted = fitText({
    fontFamily,
    text: page.text,
    withinWidth: width * 0.9,
    textTransform,
  });
  const fontSize = Math.min(style.fontSize, fitted.fontSize);

  const container: React.CSSProperties = {
    justifyContent: "center",
    alignItems: "center",
    top: undefined,
    bottom: style.captionBottom,
    height: 220,
    padding: "0 40px",
    textAlign: "center",
  };

  return (
    <AbsoluteFill style={container}>
      <div
        style={{
          fontSize,
          color: style.textColor,
          WebkitTextStroke: `18px ${style.strokeColor}`,
          paintOrder: "stroke",
          transform: makeTransform([
            scale(interpolate(enter, [0, 1], [0.85, 1])),
            translateY(interpolate(enter, [0, 1], [40, 0])),
          ]),
          fontFamily,
          textTransform,
          lineHeight: 1.05,
        }}
      >
        {page.tokens.map((t) => {
          const s = t.fromMs - page.startMs;
          const e = t.toMs - page.startMs;
          const active = s <= timeInMs && e > timeInMs;
          return (
            <span
              key={t.fromMs}
              style={{
                display: "inline",
                whiteSpace: "pre",
                color: active ? style.highlightColor : style.textColor,
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
