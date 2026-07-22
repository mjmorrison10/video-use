import { continueRender, delayRender, staticFile } from "remotion";

// Young Serif — heavy display serif for center-screen, all-caps, heavy-stroke
// short-form captions + the hook headline. Lora Bold as serif fallback.
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
    `url('${staticFile("YoungSerif-Regular.ttf")}') format('truetype')`,
    { weight: "400" },
  );
  const fallback = new FontFace(
    FontFallback,
    `url('${staticFile("Lora-Bold.ttf")}') format('truetype')`,
    { weight: "700" },
  );

  await Promise.all([primary.load(), fallback.load()]);
  document.fonts.add(primary);
  document.fonts.add(fallback);

  continueRender(waitForFont);
};
