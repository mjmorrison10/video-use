import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import { Short } from "./Short";
import { shortSchema, type ShortProps } from "./Short/schema";

const calcShortMetadata: CalculateMetadataFunction<ShortProps> = ({ props }) => {
  const fps = props.fps ?? 30;
  const totalOut = props.ranges.reduce(
    (acc, r) => Math.max(acc, r.offsetSec + (r.outSec - r.inSec)),
    0,
  );
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
  ranges: [{ inSec: 0, outSec: 5, offsetSec: 0, framing: "cover", mute: false }],
  captionPages: [],
  music: null,
  style: {
    highlightColor: "#FFD60A",
    accentColor: "#00E5FF",
    textColor: "white",
    strokeColor: "black",
    fontSize: 78,
    captionPosition: "center",
    captionBottom: 430,
    uppercase: true,
    powerWords: [],
  },
  hook: null,
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
