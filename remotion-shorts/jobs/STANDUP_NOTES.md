# Stand Up For Tate — build notes

9:16, 59.15s. VO bookends around the injustice-lecture footage.

## Structure (output timeline)

| from | to | what |
|---|---|---|
| 0.00 | 11.60 | VO INTRO over Tate B-roll |
| 11.60 | 51.06 | lecture core — 14 face-tracked ranges |
| 51.06 | 57.35 | VO CLOSE over Tate B-roll |
| 57.35 | 59.15 | end card |

## The VO

INTRO: "He is an American citizen, held in solitary in Miami, while strangers
online call for his death. Innocent until proven guilty. His name is Andrew Tate."

CLOSE: "You weren't affected. Not yet. Will you stay silent, or stand up for Tate?"

Written by the marketing/content-creator agent against the client's four stated
facts and nothing else — no case details, no claims about anyone's motives, so
there is nothing in the narration a hostile viewer can fact-check and dismiss.
The intro withholds the name until the last beat so "His name is Andrew Tate"
hard-cuts into the professor's "what is your name?" — the edit carries the
argument before the viewer decides whether they want it to.

edge-tts `en-US-ChristopherNeural`, +10% rate (~176 wpm), pitch -5Hz. Synthesized
one phrase at a time and joined with measured silences, because the pause map is
the performance: the 1.0s before the name is the longest silence in the piece.

## Source prep

- burnt-in subtitles occupy y=930-1045 of the 1080-high source. Cropped to
  1920x918 so they cannot collide with our captions. This changes the source
  aspect, which is why the face tracker now reads the proxy's real dimensions.
- dialogue was 13.5 dB below the narration and BELOW the music bed. Proxy audio
  gained +9.8 dB with a limiter; everything now sits at -20 LUFS with the bed
  11 dB under it.

## Verification

The assembled cut was re-transcribed with large-v3 and returned exactly the
intended script, which is the only real proof that no boundary word is clipped:

> You there, second desk. What is your name? My name is Alexis. Alexis, please
> leave my lecture room. I don't understand. I am not going to ask a second
> time. Tell me, was I unfair to your classmate just now? Indeed I was. So, why
> didn't any of you protest? You didn't say anything because you weren't
> affected yourself. If you don't help bring about justice, then one day you too
> may experience injustice. And there will be nobody there to stand before you.

## Open

- B-roll is a stand-in cut from `jk_charges_src.mp4` (Tate seated, graded down),
  pending the client's own footage. Swapping it is a file replace + re-render.
- The agent flagged that "stand up for Tate" reads as fandom rather than
  principle; "...or stand up for him?" keeps the due-process framing. Left as
  the client's phrasing.
