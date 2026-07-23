#!/usr/bin/env python3
"""Generate Round-3 cutspecs from compact segment specs.

Each segment is (time_hint_seconds, "phrase to include verbatim"). The resolver
finds the contiguous run of transcript words whose cleaned tokens match the
phrase nearest the time hint, and returns exact (first.start, last.end) as the
segment in/out. snap_silence.py then lands the boundary in the silence gap.

Loop videos: put the HOOK segment(s) first, then the story, ending right before
the hook line in the source so end-watchers loop seamlessly.
"""
import json, re, sys
from pathlib import Path

TR = json.load(open('/home/user/videos/jackkneel/edit/transcript_full.json'))
WORDS = [w for w in TR['words'] if w.get('start') is not None]
JOBS = Path('/home/user/video-use/remotion-shorts/jobs')


def clean(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


CTOK = [clean(w['text']) for w in WORDS]


def _match_run(anchor, lo, hi):
    """Find start index in [lo,hi) where the anchor token-run matches (<=1 miss)."""
    m = len(anchor)
    best, bestmiss = None, 99
    for i in range(lo, min(hi, len(WORDS) - m + 1)):
        if CTOK[i] != anchor[0]:
            continue
        miss = sum(1 for k in range(m) if CTOK[i + k] != anchor[k])
        if miss <= 1 and miss < bestmiss:
            best, bestmiss = i, miss
            if miss == 0:
                break
    return best


def resolve(hint, phrase):
    """Anchor on the first & last few words so mid-phrase whisper glitches
    (stray inserted/dropped words) don't break alignment."""
    toks = [clean(t) for t in phrase.split() if clean(t)]
    n = len(toks)
    k = min(4, n)
    head, tail = toks[:k], toks[-k:]
    # start: nearest head-run to the hint
    cand = [i for i in range(len(WORDS) - k + 1)
            if CTOK[i] == head[0] and sum(1 for j in range(k) if CTOK[i + j] != head[j]) <= 1]
    if not cand:
        raise SystemExit(f"NO HEAD near {hint}: {phrase!r}")
    start = min(cand, key=lambda i: abs(WORDS[i]['start'] - hint))
    # end: tail-run whose start index is closest to the expected end (start+n-k)
    win_hi = start + max(2 * n + 25, 40)
    expected = start + n - k
    tmatch = [i for i in range(start, min(win_hi, len(WORDS) - k + 1))
              if CTOK[i] == tail[0] and sum(1 for j in range(k) if CTOK[i + j] != tail[j]) <= 1]
    if not tmatch:
        raise SystemExit(f"NO TAIL near {hint}: {phrase!r}")
    endpos = min(tmatch, key=lambda i: abs(i - expected)) + k - 1
    a = WORDS[start]['start']
    b = WORDS[endpos]['end']
    # end just INSIDE the last matched word so build_props never pulls in the
    # next (often a whisper-phantom) word; start a hair early (snap refines).
    return round(a - 0.03, 3), round(b - 0.02, 3)


def build(segs):
    out = []
    for hint, phrase, beat in segs:
        a, b = resolve(hint, phrase)
        out.append({"inSec": a, "outSec": b, "beat": beat, "framing": "cover"})
    return out


def emit(name, segs, power, hook, music, extra=None):
    spec = {
        "videoSrc": "jk_proxy.mp4",
        "fps": 30,
        "segments": build(segs),
        "style": {"powerWords": power},
        "hook": {"text": hook, "untilSec": 2.5},
        "music": music,
    }
    if extra:
        spec.update(extra)
    p = JOBS / f"{name}.cutspec.json"
    p.write_text(json.dumps(spec, ensure_ascii=False, indent=1))
    dur = sum(s['outSec'] - s['inSec'] for s in spec['segments'])
    print(f"{name:20s} {len(spec['segments']):2d} segs  ~{dur:5.1f}s  -> {p.name}")


# music presets
M_EPIC = {"src": "zack_hemsey_the_way.mp3", "volLow": 0.10, "volHigh": 0.20, "climaxSec": None, "startSec": 0}
M_DARK = {"src": "dark_knight_imagine_fire.mp3", "volLow": 0.11, "volHigh": 0.22, "climaxSec": None, "startSec": 0}
M_TENS = {"src": "tension_compilation.mp3", "volLow": 0.10, "volHigh": 0.20, "climaxSec": None, "startSec": 0}
M_INTER = {"src": "interstellar.mp3", "volLow": 0.10, "volHigh": 0.19, "climaxSec": None, "startSec": 0}
M_SNEAK = {"src": "sneaky.mp3", "volLow": 0.11, "volHigh": 0.20, "climaxSec": None, "startSec": 0}
M_METRO = {"src": "metro_superhero.mp3", "volLow": 0.10, "volHigh": 0.20, "climaxSec": None, "startSec": 0}
M_MAG7 = {"src": "magnificent_seven.mp3", "volLow": 0.10, "volHigh": 0.20, "climaxSec": None, "startSec": 0}

SPECS = {}

# ============ V1 jk2_sueher — LOOP (clips 3+1 merged) ============
SPECS['jk2_sueher'] = dict(
    segs=[
        (4647.1, "Sue her. Why not?", "HOOK"),
        (4650.6, "It's the first thing we do", "HOOK"),
        (4621.1, "No Romanian courts, an American court", "POINT"),
        (4624.7, "It's not perfect, but it's the best chance we got", "POINT"),
        (4626.7, "So we got the lawsuit against girl A in Florida", "POINT"),
        (4633.5, "She lied. She knows she lied", "PAYOFF"),
        (4636.3, "The Romanian state is corrupt", "PAYOFF"),
        (4638.0, "They stole my fucking stuff", "PAYOFF"),
        (4639.5, "They destroyed my fucking business", "PAYOFF"),
        (4641.0, "They destroyed my mental health", "PAYOFF"),
        (4642.4, "They put me in a fucking cell", "PAYOFF"),
        (4643.8, "They've ruined my reputation", "PAYOFF"),
        (4645.2, "They kept me from my fucking kids", "PAYOFF"),
    ],
    power=["sue", "lied", "corrupt", "american", "court", "florida", "reputation", "kids", "destroyed", "cell"],
    hook="SUE HER. WHY NOT?",
    music=M_EPIC,
)

# ============ V4 jk2_attackdog — LOOP ============
SPECS['jk2_attackdog'] = dict(
    segs=[
        (6172.5, "Romania have always just been the attack dog", "HOOK"),
        (6176.2, "They're not the handler", "HOOK"),
        (6124.3, "Because all of this began", "POINT"),
        (6127.2, "from the UK", "POINT"),
        (6128.4, "The UK Foreign Office, when they deleted me from everything and wiped my phone, wrote to the Romanians and said I was an unchecked source of influence", "POINT"),
        (6137.6, "which started the prosecutor entering requests for warrants on the exact same day to get me arrested", "POINT"),
        (6143.7, "I get arrested. I go to jail", "POINT"),
        (6145.6, "They're slandering me on the BBC", "POINT"),
        (6147.6, "But because of my affiliates, I have a larger voice than them", "POINT"),
        (6150.5, "I get out of jail and start doing podcasts and telling the truth", "POINT"),
        (6153.2, "Their narrative is falling apart", "POINT"),
        (6160.7, "The UK panics and says, extradite, get him, get him", "POINT"),
        (6164.0, "and send an extradition warrant, which has failed", "PAYOFF"),
        (6167.1, "But I'm back in my house", "PAYOFF"),
    ],
    power=["uk", "britain", "handler", "romania", "extradite", "arrested", "jail", "bbc", "failed", "influence"],
    hook="ROMANIA WAS JUST THE ATTACK DOG",
    music=M_TENS,
)

# ============ V9 jk2_notasurprise — LOOP ============
SPECS['jk2_notasurprise'] = dict(
    segs=[
        (1170.7, "It's not a surprise. It's not a surprise", "HOOK"),
        (1132.7, "Now, for anyone watching this, the media does not tell you what has happened", "POINT"),
        (1137.5, "The media's primary objective is to prepare you for what is about to happen", "POINT"),
        (1143.0, "They need to condition your mind so that when they do something, you're ready for it", "POINT"),
        (1152.0, "If the media constantly reports about how dangerous it is, how a lockdown might need to happen", "POINT"),
        (1160.0, "Over weeks, your mind softens to the idea", "POINT"),
        (1166.3, "So when the lockdown comes, there's no revolution", "PAYOFF"),
    ],
    power=["media", "surprise", "condition", "mind", "lockdown", "revolution", "prepare", "dangerous"],
    hook="IT'S NOT A SURPRISE",
    music=M_DARK,
)

# ============ V3 jk2_land7m — clip 9 standalone (the shakedown) ============
SPECS['jk2_land7m'] = dict(
    segs=[
        (2389.0, "It's not even near a road. There's no electricity", "HOOK"),
        (2369.0, "A man comes to my house, a Romanian guy", "POINT"),
        (2371.5, "I need to talk to you", "POINT"),
        (2377.0, "And he said, you need to buy some land", "POINT"),
        (2384.0, "He gets out this map and he goes, there's some land here. It's seven million", "POINT"),
        (2393.0, "This is two hours by dirt bike to reach this land", "POINT"),
        (2409.0, "And I said, well, I don't have time. I don't want it", "POINT"),
        (2412.0, "He said, you're going to need the friends", "POINT"),
        (2422.0, "There's a lot of conversation about you in Romania in the power structures right now", "POINT"),
        (2432.0, "And my stupid ass, even though I knew it was a shakedown", "PAYOFF"),
    ],
    power=["million", "land", "electricity", "shakedown", "friends", "romania", "power", "map"],
    hook="BUY THIS LAND. $7 MILLION.",
    music=M_SNEAK,
)

# ============ V5 jk2_protocol — clip 5, first raid ============
SPECS['jk2_protocol'] = dict(
    segs=[
        (833.0, "They said it's protocol in Romania in case he's proven to be proceeds of crime", "HOOK"),
        (844.0, "It's a crime, there's not even a girl in this house. Who have I kidnapped?", "HOOK"),
        (830.0, "I explained why they had to do that", "POINT"),
        (851.0, "we're just responding to the American embassy. We don't know what's going on", "POINT"),
        (858.0, "We're just the muscle", "POINT"),
        (863.0, "You have to go talk to the detective", "POINT"),
        (883.0, "after searching our entire house for five or six hours, the media is now outside", "POINT"),
        (893.0, "Media is outside saying human trafficking, investigation, all this stuff", "PAYOFF"),
        (897.0, "They start to slander our name with all this garbage", "PAYOFF"),
    ],
    power=["protocol", "crime", "kidnapped", "muscle", "trafficking", "slander", "media", "embassy"],
    hook="“WHO HAVE I KIDNAPPED?”",
    music=M_TENS,
)

# ============ V6 jk2_crazygirls — clip 14 (separate) ============
SPECS['jk2_crazygirls'] = dict(
    segs=[
        (912.0, "this crap happens. Maybe in Romania it's not a big thing, but in America this happens all the time", "HOOK"),
        (894.0, "the prosecutor says, why did this girl say there was girls kidnapped in your house", "POINT"),
        (900.0, "and I said, brother, I haven't got a fucking clue. I only said hello to her twice", "POINT"),
        (906.0, "the prosecutor goes, well Tristan should have bought her a hand bag, and laughed", "POINT"),
        (909.0, "and then I laughed, and we all laughed", "POINT"),
        (918.0, "These girls are nuts. They just make stuff up", "PAYOFF"),
        (933.0, "You've been to the house. There's no one in the house", "PAYOFF"),
        (936.0, "We have CCTV in our house. You can take the cameras and see her walking in and out the house by her own", "PAYOFF"),
    ],
    power=["america", "crazy", "nuts", "prosecutor", "kidnapped", "cctv", "handbag", "laughed"],
    hook="“THESE GIRLS ARE NUTS”",
    music=M_SNEAK,
)

# ============ V7 jk2_notclosed — clip 6 ============
SPECS['jk2_notclosed'] = dict(
    segs=[
        (1000.5, "It's like July now. Why is that case not closed?", "HOOK"),
        (996.0, "they raided our house in April", "POINT"),
        (1002.0, "He goes, this is Romania. Everything takes forever. It's a slow system", "POINT"),
        (1017.0, "this is so open and shut. What could they possibly be doing?", "POINT"),
        (1027.0, "yeah, it's Romania. They probably have to go through all the hours", "POINT"),
        (1032.0, "It's going to take a while. Don't sweat it", "POINT"),
        (1035.0, "I had this bad feeling", "PAYOFF"),
        (1039.0, "But what can you do, right? I haven't done anything wrong", "PAYOFF"),
    ],
    power=["july", "closed", "case", "romania", "feeling", "april", "raided"],
    hook="WHY IS THE CASE NOT CLOSED?",
    music=M_TENS,
)

# ============ V8 jk2_sevenaccounts — clip 7 ============
SPECS['jk2_sevenaccounts'] = dict(
    segs=[
        (1069.0, "I start moving from fringe internet celebrity to mainstream celebrity", "HOOK"),
        (1074.0, "I start getting bigger and bigger and bigger", "POINT"),
        (1077.0, "my Instagram had a hundred thousand followers. By this point, I'm up to like two or three million", "POINT"),
        (1088.0, "My girlfriend comes in and goes, have you seen this?", "POINT"),
        (1093.0, "it's a picture of me. And there's some blurb underneath it about how I'm toxically masculine", "POINT"),
        (1101.0, "I'm a misogynist, a racist, and a homophobe", "POINT"),
        (1110.0, "And it's on an NGO page for a charity protecting the rights of gays", "POINT"),
        (1108.1, "the same picture with the same blurb explaining that I'm the worst man in the world", "POINT"),
        (1113.4, "Copy and paste, exact one, on an NGO about wildlife protection", "POINT"),
        (1127.8, "I find like seven different accounts, random accounts for random charities and NGOs posting that I'm the worst person in the world", "PAYOFF"),
    ],
    power=["instagram", "million", "misogynist", "racist", "ngo", "seven", "copy", "worst", "charity"],
    hook="SUDDENLY I WAS THE WORST MAN ALIVE",
    music=M_DARK,
)

# ============ V10 jk2_menprotest — clip 8 ============
SPECS['jk2_menprotest'] = dict(
    segs=[
        (1899.0, "When men get together, it's not called a protest. It's called a revolution", "HOOK"),
        (1861.0, "you know what happens when women are powerful? Nothing", "POINT"),
        (1867.0, "if a hundred thousand women march through this town and protest, it's inconvenient", "POINT"),
        (1873.0, "If a hundred thousand men march through this town, everything burns and the entire government changes", "POINT"),
        (1881.0, "Men can fight. Men are armies", "POINT"),
        (1906.0, "Women don't do revolutions. They can't", "POINT"),
        (1909.0, "So they deliberately empower women to subjugate men", "POINT"),
        (1913.0, "That's why masculinity has been under such attack", "POINT"),
        (1917.0, "And I came along and was the most Googled man in the world promoting masculinity", "PAYOFF"),
        (1936.0, "And that was considered so dangerous, I ended up on a terror watch list", "PAYOFF"),
        (1942.0, "And the country that put me on a terror watch list, do you want to guess? U. S. Incorrect, sir. England", "PAYOFF"),
    ],
    power=["men", "revolution", "protest", "women", "masculinity", "armies", "terror", "england", "subjugate"],
    hook="MEN DON'T PROTEST. THEY REVOLT.",
    music=M_MAG7,
)

# ============ V11 jk2_hybridstate — clip 10 ============
SPECS['jk2_hybridstate'] = dict(
    segs=[
        (3908.0, "That's not a lie. Look it up. Romania is considered a hybrid state", "HOOK"),
        (3888.0, "I'm really excited for the American embassy to turn up", "POINT"),
        (3896.0, "I walk in there. I'm like, guys, thank fuck. Real humans. You're an American. I'm an American", "POINT"),
        (3903.0, "This is bullshit. U. S. Constitution", "POINT"),
        (3905.0, "and they're like, yeah, the American government considers Romania to be a real legal system", "POINT"),
        (3913.0, "This is a setup in a corrupt dump. We all know it's corrupt", "POINT"),
        (3916.0, "On the corruption index, we're at the same level as Zambia", "POINT"),
        (3938.0, "he goes, Andrew, I like you", "POINT"),
        (3943.0, "I think you need to prepare for quite a long stay", "PAYOFF"),
        (3956.0, "there's nothing really the American government's prepared to do for you", "PAYOFF"),
        (3966.0, "So here's a leaflet", "PAYOFF"),
    ],
    power=["hybrid", "zambia", "corrupt", "american", "embassy", "constitution", "leaflet", "setup"],
    hook="ROMANIA IS A HYBRID STATE",
    music=M_TENS,
)

# ============ V12 jk2_killme — clip 11 ============
SPECS['jk2_killme'] = dict(
    segs=[
        (7910.0, "You have to kill me", "HOOK"),
        (7841.0, "just go away and all of this will go away", "POINT"),
        (7847.0, "If you go away for a year, no one's going to care about the case when it gets dropped", "POINT"),
        (7854.0, "I was like, no, you started this. You started this", "POINT"),
        (7858.0, "I had a fucking Shopify school", "POINT"),
        (7860.0, "You started this because I got too big. I was saying the right thing", "POINT"),
        (7866.0, "I was helping young men make money, helping them resist enslavement", "POINT"),
        (7876.0, "You started this fucking fight. We're going to see it through to the fucking end", "POINT"),
        (7896.0, "you've taken the one thing from me that can make me fucking happy", "POINT"),
        (7906.0, "I'm not gonna kill myself. You have to kill me. You want me dead, then you have to fucking do it", "POINT"),
        (7920.0, "and that's why I decided to fight them, not because I'm brave, and not because I believed I could win", "PAYOFF"),
        (7930.0, "but because I was just ready to fucking lose", "PAYOFF"),
    ],
    power=["kill", "fight", "started", "war", "lose", "money", "men", "dead", "brave"],
    hook="“YOU HAVE TO KILL ME”",
    music=M_EPIC,
    extra={"cta": {"text": "COMMENT “FIGHT”", "sub": "for part 2 of the story", "durSec": 2}},
)

# ============ V13 jk2_billion — clip 12 ============
SPECS['jk2_billion'] = dict(
    segs=[
        (8318.0, "They're not that rich, bro. It's a poor country and it's a corrupt shithole", "HOOK"),
        (8280.0, "If the Romanian state don't find me guilty, they owe me a billion dollars", "POINT"),
        (8286.0, "They destroyed my school. They destroyed the image of the most Googled man on the planet", "POINT"),
        (8294.0, "They've unfairly imprisoned me three times. I spent three years locked in my house", "POINT"),
        (8291.0, "I didn't see my kids. My mom had a heart attack", "POINT"),
        (8322.0, "They owe me a billion dollars. Are the Romanians going to let me go so they have to pay me a billion dollars?", "POINT"),
        (8332.0, "No. Why the fuck would Romania let me off?", "POINT"),
        (8336.0, "They'll just find me guilty. It saves a billion", "PAYOFF"),
        (8348.0, "It's got the same judicial fucking integrity as Zambia", "PAYOFF"),
    ],
    power=["billion", "corrupt", "shithole", "guilty", "zambia", "romania", "imprisoned", "dollars"],
    hook="THEY OWE HIM A BILLION DOLLARS",
    music=M_TENS,
)

# ============ V14 jk2_rigged — clip 13 ============
SPECS['jk2_rigged'] = dict(
    segs=[
        (9214.0, "AFD in Germany, it's rigged. They let AFD win a little bit, but not properly", "HOOK"),
        (9155.0, "He wins the presidential election by a landslide", "POINT"),
        (9162.0, "And the next day, the constitutional court cancels the election, says it was corrupted by Russian interference", "POINT"),
        (9174.0, "The prosecutor which sent him to jail is the same prosecutor as me", "POINT"),
        (9192.0, "only three countries in history have undone an election", "POINT"),
        (9203.0, "That's how corrupt this shithole is", "POINT"),
        (9224.0, "Every European country rigs its elections", "POINT"),
        (9231.0, "Marine Le Pen in France, she caught a criminal case just before she could win", "POINT"),
        (9250.0, "The Romanians fucked up their rigging. So they had to redo the whole election", "PAYOFF"),
    ],
    power=["rigged", "election", "afd", "corrupt", "prosecutor", "russian", "vote", "france"],
    hook="EVERY ELECTION IS RIGGED",
    music=M_DARK,
)

# ============ V15 jk2_password — clip 15 ============
SPECS['jk2_password'] = dict(
    segs=[
        (8155.2, "your case will be dropped and you will not go to jail in Romania", "HOOK"),
        (8140.2, "here's what's going to happen. You're going to be given immunity in Romania for anything that's found on that phone", "POINT"),
        (8146.1, "Your current case is going to be dropped. You're going to be quiet on the internet", "POINT"),
        (8159.5, "But for the next year, while your case is nice and quiet, you get to live in Romania", "POINT"),
        (8168.8, "And then when no one talks about it, we'll drop your Romanian case", "POINT"),
        (8182.1, "And I took the papers and I was like, I forgot", "POINT"),
        (8191.4, "I forgot what? I forgot my password. Sorry. Can't give it to you. I don't remember", "PAYOFF"),
        (8197.1, "And the rage on their faces", "PAYOFF"),
    ],
    power=["password", "immunity", "dropped", "jail", "forgot", "romania", "rage", "phone"],
    hook="“YOUR CASE WILL BE DROPPED”",
    music=M_SNEAK,
)

# ============ V16 jk2_hongkong — clip 16 ============
SPECS['jk2_hongkong'] = dict(
    segs=[
        (10033.8, "In fact, that article came out in Hong Kong when they changed the law about raiding people's phones", "HOOK"),
        (10040.5, "and how they could instantly force you to give them the password and you're not allowed to forget it", "POINT"),
        (10024.4, "they could ask people who were non-Hong Kong citizens for their passcode if they're going through an airport", "POINT"),
        (10044.7, "I was on a plane an hour later. I left instantly", "POINT"),
        (10048.7, "because that law was changed for me", "POINT"),
        (10050.9, "because England still has massive influence in Hong Kong", "PAYOFF"),
    ],
    power=["hongkong", "law", "phones", "password", "england", "influence", "plane", "brits"],
    hook="THEY CHANGED A LAW JUST FOR HIM",
    music=M_TENS,
)

# ============ V17 jk2_threelives — clip 18 ============
SPECS['jk2_threelives'] = dict(
    segs=[
        (10390.0, "There's OnlyFans girls all over LA. It's not illegal", "HOOK"),
        (10362.0, "The three lives. First, they try and shut you up", "POINT"),
        (10366.0, "Everyone they silenced before me went away. I got bigger", "POINT"),
        (10373.0, "Second, you try and put them in jail", "POINT"),
        (10377.0, "Third, you kill them", "POINT"),
        (10380.0, "I am lucky that I had the past I had. I'm lucky I had a webcam studio. That's not human trafficking", "POINT"),
        (10393.0, "I'm lucky I had lots of girlfriends. Lucky I slept with a lot of women", "POINT"),
        (10397.0, "Lucky I've made racist jokes", "POINT"),
        (10430.0, "I'm lucky I did these things because killing people is messy", "PAYOFF"),
        (10435.0, "and killing people makes them a hero", "PAYOFF"),
    ],
    power=["lucky", "onlyfans", "kill", "jail", "silence", "hero", "webcam", "three", "lives"],
    hook="THREE LIVES: SILENCE, JAIL, KILL",
    music=M_EPIC,
)

# ============ V18 jk2_herhair — clip 19 ============
SPECS['jk2_herhair'] = dict(
    segs=[
        (2991.0, "We've fucking done this already", "HOOK"),
        (2985.0, "Eventually, the detective says, we're here for human trafficking", "POINT"),
        (2993.0, "if you're here for human trafficking, why is it the girl who was in my bed, you didn't ask if she's okay", "POINT"),
        (3000.0, "You fucking dragged her by her hair out of the bed and forced her onto the ground at gunpoint and asked about my Bugatti", "PAYOFF"),
        (3009.0, "We need to take your assets. But I thought we're here for human trafficking", "POINT"),
        (3015.0, "the girl you find in the house you beat the fuck out of and start asking me about my cars", "POINT"),
        (3022.0, "This time they take the car keys", "PAYOFF"),
        (3035.0, "So they take all the cars", "PAYOFF"),
    ],
    power=["trafficking", "hair", "gunpoint", "bugatti", "assets", "cars", "bed", "money"],
    hook="“WE'VE DONE THIS ALREADY”",
    music=M_TENS,
)

# ============ V19 jk2_euroaweek — clip 20 ============
SPECS['jk2_euroaweek'] = dict(
    segs=[
        (5753.3, "my brother and I got a brand new Porsche GT4 RS, and a McLaren 765 LT in purple delivered to our house", "HOOK"),
        (5765.9, "So we have those cars delivered on our first day and start driving around Bucharest", "POINT"),
        (5769.6, "Alan calls me, decal wants to see you. Like, surprise, surprise", "POINT"),
        (5775.5, "Where are these cars from? I rented them", "POINT"),
        (5780.9, "They're not rented, so they're not mine. fine run the number plates", "POINT"),
        (5787.4, "genius started a rental company in Portugal and bought a bunch of assets under this Portuguese company", "POINT"),
        (5795.6, "he'd rent them to me for a euro a week. What a nice guy", "PAYOFF"),
        (5798.5, "Never met him, don't know his name", "PAYOFF"),
    ],
    power=["porsche", "mclaren", "euro", "portugal", "rented", "genius", "cars", "decot"],
    hook="A EURO A WEEK FOR A MCLAREN",
    music=M_SNEAK,
)

# ============ V2 jk2_shakedown — clip 2, the 8-min arc condensed ============
SPECS['jk2_shakedown'] = dict(
    segs=[
        (2373.1, "Not today. I said, it's important. He's an important man in Romania", "HOOK"),
        (2366.8, "A man comes to my house, a Romanian guy", "POINT"),
        (2412.0, "He said, you're going to need the friends", "POINT"),
        (2423.4, "there's a lot of conversation about you in Romania in the power structures right now", "POINT"),
        (2460.7, "And I said to Tristan, let's get the fuck out of here. Let's just go. He goes, where? I said, Dubai", "POINT"),
        (2527.8, "And I'm saying in all these podcasts, you get three lives", "POINT"),
        (2530.2, "And if they ever try and put me in jail for something I didn't do, I hope everyone at home is smart enough to understand it is a setup", "POINT"),
        (2627.1, "And then one day we get a phone call from Piers Morgan's team", "POINT"),
        (2636.0, "I told you they want us to go to England. They're going to arrest us", "POINT"),
        (2844.5, "So we land at 9 p.m. in Romania, straight off the plane, no problems", "POINT"),
        (2858.4, "And at 4 a.m. that morning is the video the entire world saw when they raided our house again", "PAYOFF"),
        (2874.4, "That's the video everyone saw", "PAYOFF"),
    ],
    power=["dubai", "setup", "england", "arrest", "raided", "trafficking", "romania", "friends", "jail"],
    hook="“HE'S AN IMPORTANT MAN IN ROMANIA”",
    music=M_DARK,
)

if __name__ == '__main__':
    only = sys.argv[1:] if len(sys.argv) > 1 else list(SPECS)
    for name in only:
        s = SPECS[name]
        emit(name, s['segs'], s['power'], s['hook'], s['music'], s.get('extra'))
