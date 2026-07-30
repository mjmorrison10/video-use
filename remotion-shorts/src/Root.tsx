import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import { Short } from "./Short";
import { shortSchema, type ShortProps } from "./Short/schema";

const calcShortMetadata: CalculateMetadataFunction<ShortProps> = ({ props }) => {
  const fps = props.fps ?? 30;
  // The footage ranges are not necessarily the last thing on the timeline —
  // a B-roll bookend or an explicitly placed end card can outlive them, and
  // measuring only the ranges silently truncates whatever comes after.
  const rangesEnd = props.ranges.reduce(
    (acc, r) => Math.max(acc, r.offsetSec + (r.outSec - r.inSec)),
    0,
  );
  const brollEnd = (props.broll ?? []).reduce(
    (acc, b) => Math.max(acc, b.atSec + b.durSec),
    0,
  );
  const ctaEnd = props.cta ? (props.cta.atSec ?? rangesEnd) + props.cta.durSec : 0;
  const totalOut = Math.max(rangesEnd, brollEnd, ctaEnd);
  return {
    fps,
    width: 1080,
    height: 1920,
    durationInFrames: Math.max(1, Math.round(totalOut * fps)),
  };
};

// Minimal placeholder so Studio opens before a real job is loaded.
const defaultProps: ShortProps = {
  videoSrc: "proxy.mp4",
  fps: 30,
  ranges: [
    {
      inSec: 0,
      outSec: 5,
      offsetSec: 0,
      framing: "cover",
      cropX: 0.5,
      cropXEnd: null,
      cropPanSec: null,
      mute: false,
    },
  ],
  captionPages: [],
  music: null,
  style: {
    highlightColor: "#00E5FF",
    accentColor: "#00E5FF",
    textColor: "white",
    strokeColor: "black",
    fontSize: 58,
    captionPosition: "center",
    captionBottom: 430,
    uppercase: true,
    powerWords: [],
  },
  hook: null,
  broll: [],
  zooms: [],
  zoomSteps: [],
  cta: null,
  voiceovers: [],
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Short"
      component={Short}
      schema={shortSchema}
      calculateMetadata={calcShortMetadata}
      defaultProps={defaultProps}
      fps={30}
      width={1080}
      height={1920}
      durationInFrames={150}
    />
  );
};
