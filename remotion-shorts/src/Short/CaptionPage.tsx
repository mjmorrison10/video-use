import { makeTransform, scale, translateY } from "@remotion/animation-utils";
import { fitText } from "@remotion/layout-utils";
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { PowerFont } from "../load-font";
import type { CaptionPageT, ShortProps } from "./schema";

const fontFamily = `${PowerFont}, "FontFallback", sans-serif`;

const clean = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "")
    .trim();

export const CaptionPage: React.FC<{
  readonly page: CaptionPageT;
  readonly style: ShortProps["style"];
}> = ({ page, style }) => {
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 6 });

  const textTransform = style.uppercase ? "uppercase" : "none";
  const text = page.tokens.map((t) => t.text).join("");
  const fitted = fitText({
    fontFamily,
    text,
    withinWidth: width * 0.86,
    textTransform,
  });
  const fontSize = Math.min(style.fontSize, fitted.fontSize);

  const powerSet = new Set((style.powerWords ?? []).map(clean));

  const container: React.CSSProperties =
    style.captionPosition === "bottom"
      ? {
          justifyContent: "flex-end",
          alignItems: "center",
          paddingBottom: style.captionBottom ?? 430,
          paddingLeft: 60,
          paddingRight: 60,
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
          WebkitTextStroke: `12px ${style.strokeColor}`,
          paintOrder: "stroke",
          whiteSpace: "nowrap",
          transform: makeTransform([
            scale(interpolate(enter, [0, 1], [0.9, 1])),
            translateY(interpolate(enter, [0, 1], [26, 0])),
          ]),
          fontFamily,
          textTransform,
          lineHeight: 1.05,
          textShadow: "0 5px 24px rgba(0,0,0,0.55)",
        }}
      >
        {page.tokens.map((t, i) => {
          const isPower = powerSet.has(clean(t.text));
          return (
            <span
              key={i}
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
