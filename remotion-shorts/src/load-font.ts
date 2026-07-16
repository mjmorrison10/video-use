import { continueRender, delayRender, staticFile } from "remotion";

// Big Shoulders Bold — condensed athletic display for center-screen, all-caps,
// heavy-stroke short-form captions + the hook headline. theboldfont as fallback.
export const PowerFont = `PowerFont`;
export const FontFallback = `FontFallback`;

let loaded = false;

export const loadFont = async (): Promise<void> => {
  if (loaded) {
    return Promise.resolve();
  }
  loaded = true;

  const waitForFont = delayRender();

  const primary = new FontFace(
    PowerFont,
    `url('${staticFile("BigShoulders-Bold.ttf")}') format('truetype')`,
    { weight: "700" },
  );
  const fallback = new FontFace(
    FontFallback,
    `url('${staticFile("theboldfont.ttf")}') format('truetype')`,
  );

  await Promise.all([primary.load(), fallback.load()]);
  document.fonts.add(primary);
  document.fonts.add(fallback);

  continueRender(waitForFont);
};
