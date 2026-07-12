"""Fallback synthesized music bed (used only when the user's Music/ folder is empty).
Original, royalty-free. Two styles: 'cinematic' (D-minor, soft drums, builds — the shipped v8)
and 'piano' (Am-F-C-G, no drums — the shipped v7).

Usage: music_synth.py --duration 42 -o edit/music.wav [--style cinematic|piano]
"""
import argparse, numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 48000

def lp(x, f): return signal.lfilter(*signal.butter(4, f / (SR / 2), "low"), x)
def hp(x, f): return signal.lfilter(*signal.butter(4, f / (SR / 2), "high"), x)
def cents(f, c): return f * 2 ** (c / 1200)
def nrm(x): return x / (np.max(np.abs(x)) + 1e-9)

def piano(total):
    BPM, bar = 68, 60 / 68 * 4
    N = int(total * SR); t = np.arange(N) / SR
    def pad(f, dur):
        n = int(dur * SR); tt = np.arange(n) / SR
        s = sum(a * np.sin(2 * np.pi * f * h * tt) for h, a in [(1, 1), (2, .4), (3, .15), (4, .06)])
        s2 = sum(a * np.sin(2 * np.pi * cents(f, 7) * h * tt) for h, a in [(1, 1), (2, .4), (3, .15)])
        s = .6 * s + .4 * s2
        a = int(.5 * SR); r = int(1.2 * SR); e = np.ones(n)
        e[:a] = np.linspace(0, 1, a); e[-r:] = np.linspace(1, 0, r); return s * e
    def pluck(f, dur=1.6):
        n = int(dur * SR); tt = np.arange(n) / SR
        s = sum(a * np.sin(2 * np.pi * f * h * tt) for h, a in [(1, 1), (2, .5), (3, .3), (4.2, .18), (5.4, .08)])
        env = np.exp(-tt / 0.7); at = int(.006 * SR); env[:at] *= np.linspace(0, 1, at); return s * env
    def bass(f, dur):
        n = int(dur * SR); tt = np.arange(n) / SR
        s = np.sin(2 * np.pi * f * tt) + .3 * np.sin(2 * np.pi * 2 * f * tt)
        a = int(.02 * SR); r = int(.3 * SR); e = np.ones(n)
        e[:a] = np.linspace(0, 1, a); e[-r:] = np.linspace(1, 0, r); return s * e
    Am = [220, 261.63, 329.63]; F = [174.61, 220, 261.63]; C = [261.63, 329.63, 392]; G = [196, 246.94, 293.66]
    roots = [110, 87.31, 130.81, 98]; prog = [Am, F, C, G]
    P = np.zeros(N + 2 * SR); PL = np.zeros(N + 2 * SR); B = np.zeros(N + 2 * SR)
    def add(buf, sig, s):
        e = s + len(sig)
        if e < len(buf): buf[s:e] += sig
    for i in range(int(total / bar) + 1):
        ch = prog[i % 4]; root = roots[i % 4]; st = int(i * bar * SR)
        for f in ch: add(P, pad(f, bar + 1.0) / len(ch), st)
        add(B, bass(root, bar + 0.2), st)
        for bt, f in [(0, ch[0]), (1, ch[1]), (2, ch[2]), (3, ch[0] * 2)]:
            add(PL, pluck(f), st + int(bt * (bar / 4) * SR))
    P, PL, B = P[:N], PL[:N], B[:N]
    def ir(dur, seed):
        r = np.random.default_rng(seed); ni = int(dur * SR)
        x = r.standard_normal(ni) * np.exp(-np.arange(ni) / (0.4 * SR)); return lp(x, 3500) / np.max(np.abs(x))
    wL = signal.fftconvolve(PL, ir(1.6, 1))[:N]; wR = signal.fftconvolve(PL, ir(1.75, 2))[:N]
    P, PL, B, wL, wR = map(nrm, [P, PL, B, wL, wR])
    g = np.interp(t, [0, 4, total * .66, total * .9, total], [.5, .5, 1.0, .85, .7])
    L = (.45 * P + .30 * PL + .38 * B + .26 * wL) * g
    R = (.45 * P + .30 * PL + .38 * B + .26 * wR) * g
    return L, R

def cinematic(total):
    BPM, bar = 80, 60 / 80 * 4; beat = bar / 4
    N = int(total * SR); t = np.arange(N) / SR; rng = np.random.default_rng(7)
    def pad(f, dur):
        n = int(dur * SR); tt = np.arange(n) / SR
        s = sum(a * np.sin(2 * np.pi * cents(f, d) * h * tt) for d in (-6, 6) for h, a in [(1, 1), (2, .35), (3, .12)])
        a = int(.6 * SR); r = int(1.3 * SR); e = np.ones(n)
        e[:a] = np.linspace(0, 1, a); e[-r:] = np.linspace(1, 0, r); return s * e
    def arp(f, dur=0.5):
        n = int(dur * SR); tt = np.arange(n) / SR
        saw = signal.sawtooth(2 * np.pi * f * tt) * 0.5 + 0.5 * np.sin(2 * np.pi * f * tt)
        env = np.exp(-tt / 0.18); at = int(.004 * SR); env[:at] *= np.linspace(0, 1, at); return lp(saw * env, 3000)
    def sub(f, dur):
        n = int(dur * SR); tt = np.arange(n) / SR
        s = np.sin(2 * np.pi * f * tt) + .25 * np.sin(2 * np.pi * 2 * f * tt)
        puls = 0.6 + 0.4 * (0.5 + 0.5 * signal.square(2 * np.pi * (1 / beat) * tt, 0.5))
        a = int(.02 * SR); r = int(.3 * SR); e = np.ones(n)
        e[:a] = np.linspace(0, 1, a); e[-r:] = np.linspace(1, 0, r); return lp(s * puls * e, 220)
    def kick():
        n = int(.30 * SR); tt = np.arange(n) / SR
        f = 48 + (120 - 48) * np.exp(-tt / 0.03); ph = 2 * np.pi * np.cumsum(f) / SR
        return np.sin(ph) * np.exp(-tt / 0.11)
    def shaker():
        n = int(.07 * SR); x = rng.standard_normal(n) * np.exp(-np.arange(n) / (0.02 * SR)); return hp(x, 6500) * 0.25
    Dm = [146.83, 174.61, 220]; Bb = [116.54, 146.83, 174.61]; F = [174.61, 220, 261.63]; C = [130.81, 164.81, 196]
    roots = [73.42, 58.27, 87.31, 65.41]; prog = [Dm, Bb, F, C]
    P = np.zeros(N + 2 * SR); A = np.zeros(N + 2 * SR); S = np.zeros(N + 2 * SR); D = np.zeros(N + 2 * SR)
    def add(buf, sig, s):
        e = s + len(sig)
        if e < len(buf): buf[s:e] += sig
    for i in range(int(total / bar) + 2):
        ch = prog[i % 4]; root = roots[i % 4]; st = int(i * bar * SR)
        for f in ch: add(P, pad(f, bar + 1.0) / len(ch), st)
        add(S, sub(root, bar + 0.2), st)
        patt = [ch[0], ch[1], ch[2], ch[1] * 2, ch[2], ch[1], ch[0] * 2, ch[1]]
        for j, f in enumerate(patt): add(A, arp(f), st + int(j * (beat / 2) * SR))
        for kb in (0, 2): add(D, kick(), st + int(kb * beat * SR))
        for sb in range(8): add(D, shaker(), st + int(sb * (beat / 2) * SR))
    P, A, S, D = [b[:N] for b in (P, A, S, D)]; P = lp(P, 1800)
    def ir(dur, seed):
        ni = int(dur * SR); r = np.random.default_rng(seed)
        x = r.standard_normal(ni) * np.exp(-np.arange(ni) / (0.35 * SR)); return lp(x, 3000) / np.max(np.abs(x))
    wL = signal.fftconvolve(A, ir(1.4, 3))[:N]; wR = signal.fftconvolve(A, ir(1.5, 4))[:N]
    P, A, S, D, wL, wR = map(nrm, [P, A, S, D, wL, wR])
    dg = np.interp(t, [0, 6, 16, total * .9, total], [0, .15, .7, .7, .4])
    g = np.interp(t, [0, 4, total * .62, total * .9, total], [.5, .5, 1.0, .85, .7])
    L = (.42 * P + .24 * A + .5 * S + .5 * D * dg + .22 * wL) * g
    R = (.42 * P + .24 * A + .5 * S + .5 * D * dg + .22 * wR) * g
    return L, R

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--style", choices=["cinematic", "piano"], default="cinematic")
    a = ap.parse_args()
    total = a.duration + 0.6
    L, R = (cinematic if a.style == "cinematic" else piano)(total)
    fin = lambda x: lp(np.tanh(x * 1.12), 10000)
    L, R = fin(L), fin(R)
    st = np.stack([L, R], 1); st = st / np.max(np.abs(st)) * 0.75
    wavfile.write(a.out, SR, (st * 32767).astype(np.int16))
    print(f"[done] {a.out} ({a.style}, {total:.1f}s, peak {np.max(np.abs(st)):.2f})")

if __name__ == "__main__":
    main()
