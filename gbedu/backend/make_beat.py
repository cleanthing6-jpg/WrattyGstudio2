"""Gbedu beat engine v2 - afrobeats patterns (log drum, chords). numpy only."""
import numpy as np, wave, os, sys, json
from analyze_np import load_wav, estimate_tempo, estimate_key

NOTES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
KIT = {}

def note_freq(name, oct):
    midi = 12*(oct+1) + NOTES.index(name)
    return 440.0 * 2**((midi-69)/12)

def freq_at(root, oct, semis):
    ni, oadd = divmod(NOTES.index(root) + semis, 12)
    return note_freq(NOTES[ni], oct + oadd)

def load_kit(d="samples/kit", sr=22050):
    for name in ("kick","clap","shaker","rim"):
        p = os.path.join(d, name + ".wav")
        if os.path.exists(p):
            x, s0 = load_wav(p)
            if s0 != sr:
                idx = np.linspace(0, len(x)-1, int(len(x)*sr/s0)).astype(int)
                x = x[idx]
            KIT[name] = x.astype(np.float32)

def make(bpm, key, mode="minor", bars=8, sr=22050, out="beat.wav"):
    load_kit()
    spb, step = 60.0/bpm, 60.0/bpm/4
    prog = [0,8,3,10] if mode=="minor" else [0,7,9,5]
    tri  = [0,3,7]    if mode=="minor" else [0,4,7]
    total = int(bars*16*step*sr) + sr
    mix = np.zeros(total, np.float32)

    def T(d): return np.arange(int(sr*d))/sr
    def add(sig, st, g=1.0):
        i = int(st*step*sr); j = min(i+len(sig), total)
        if i < total: mix[i:j] += sig[:j-i]*g

    def kick():
        t=T(0.28); f=110*np.exp(-t/0.025)+42
        return np.sin(2*np.pi*np.cumsum(f)/sr)*np.exp(-t/0.09)
    def log(f):
        t=T(0.28); fp=f*(1+3*np.exp(-t/0.02)); ph=2*np.pi*np.cumsum(fp)/sr
        return (np.sin(ph)+0.3*np.sin(2*ph))*np.exp(-t/0.16)*np.clip(t/0.002,0,1)
    def clap():
        rng=np.random.default_rng(0); n=int(sr*0.18); t=T(0.18)
        return (rng.standard_normal(n)*0.8+0.4*np.sin(2*np.pi*190*t))*np.exp(-t/0.05)
    def shaker():
        rng=np.random.default_rng(1); n=int(sr*0.05); t=T(0.05)
        return np.diff(np.concatenate([[0], rng.standard_normal(n)]))*np.exp(-t/0.012)
    def rim():
        t=T(0.08); return np.sin(2*np.pi*1200*t)*np.exp(-t/0.01)
    def stab(fs, d):
        t=T(d); s=sum(np.sin(2*np.pi*f*t) for f in fs)
        return s/len(fs)*np.exp(-t/0.25)

    K, C, SH, R = KIT.get("kick", kick()), KIT.get("clap", clap()), \
                  KIT.get("shaker", shaker()), KIT.get("rim", rim())
    for bar in range(bars):
        b = bar*16
        ci = prog[bar % len(prog)]
        root = freq_at(key, 2, ci)
        for st in (0,6,10):            add(K, b+st, 0.95)
        for st in (3,7,11,14):         add(log(root), b+st, 0.70)   # log drum
        for st in (4,12):              add(C, b+st, 0.50)
        for st in range(16):           add(SH, b+st, 0.30 if st%2 else 0.18)
        fs = [freq_at(key,3,ci+t) for t in tri]
        for st in (2,8,14):            add(stab(fs, step*1.5), b+st, 0.22)
        for st in (7,15):              add(R, b+st, 0.20)
    mix /= max(1e-6, float(np.max(np.abs(mix))))
    with wave.open(out,"wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((mix*0.9*32767).astype('<i2').tobytes())
    return out

if __name__ == "__main__":
    x, sr = load_wav(sys.argv[1]); x = x[:sr*120]
    bpm = round(estimate_tempo(x, sr)); (key, mode), _ = estimate_key(x, sr)
    out = sys.argv[2] if len(sys.argv) > 2 else "beat.wav"
    make(bpm, key, mode, out=out)
    print(json.dumps({"vocal_bpm": bpm, "vocal_key": f"{key} {mode}", "beat": out}))
