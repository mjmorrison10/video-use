import { continueRender, delayRender, staticFile } from "remotion";

// Heavy display serif for centered "power" captions + hook headline.
export const PowerSerif = `PowerSerif`;
export const SerifFallback = `SerifFallback`;

let loaded = false;

export const loadFont = async (): Promise<void> => {
  if (loaded) {
    return Promise.resolve();
  }
  loaded = true;

  const waitForFont = delayRender();

  const young = new FontFace(
    PowerSerif,
    `url('${staticFile("YoungSerif-Regular.ttf")}') format('truetype')`,
  );
  const lora = new FontFace(
    SerifFallback,
    `url('${staticFile("Lora-Bold.ttf")}') format('truetype')`,
    { weight: "700" },
  );

  await Promise.all([young.load(), lora.load()]);
  document.fonts.add(young);
  document.fonts.add(lora);

  continueRender(waitForFont);
};
