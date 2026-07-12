"""Convert an ElevenLabs Scribe response (helpers/transcribe.py output) to the pipeline's
canonical transcript schema. Optional path — used only when transcribing via Scribe instead
of local whisper. Scribe words are {type,text,start,end}; we keep type=='word' and rename
text -> word (with a leading space to match whisper's convention).

Usage: stt_scribe_adapter.py SCRIBE.json --out edit/transcript.json
"""
import argparse, json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scribe")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    raw = json.load(open(a.scribe))
    words = raw.get("words", [])
    flat = [{"word": (" " + w["text"].strip()), "start": round(w["start"], 3),
             "end": round(w["end"], 3)}
            for w in words if w.get("type") == "word"]
    dur = max((w["end"] for w in flat), default=0.0)
    payload = {"language": raw.get("language_code", "en"), "duration": round(dur, 3),
               "segments": [{"start": flat[0]["start"] if flat else 0,
                             "end": dur,
                             "text": " ".join(w["word"].strip() for w in flat),
                             "words": flat}],
               "words": flat}
    json.dump(payload, open(a.out, "w"), indent=1)
    print(f"[done] {a.out} ({len(flat)} words)")

if __name__ == "__main__":
    main()
