"""Gbedu analysis - numpy-only (Termux friendly: no scipy/librosa)."""
import numpy as np, wave, sys, json

NOTES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
MAJOR = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
MINOR = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])

def load_wav(path):
    with wave.open(path, 'rb') as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dt = {1: np.uint8, 2: np.int16, 4: np.int32}[sw]
    x = np.frombuffer(raw, dtype=dt).astype(np.float32)
    x = (x - 128)/128.0 if sw == 1 else x / (2 ** (8*sw - 1))
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr

def estimate_tempo(x, sr, hop=512, win=1024, bpm_min=60, bpm_max=180):
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    S = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1))
    flux = np.maximum(0, np.diff(S, axis=0)).sum(axis=1)
    flux -= flux.mean()
    ac = np.correlate(flux, flux, 'full')[len(flux)-1:]
    fps = sr / hop
    lo, hi = int(60*fps/bpm_max), int(60*fps/bpm_min)
    lag = lo + int(np.argmax(ac[lo:hi]))
    return 60.0 * fps / lag

def estimate_key(x, sr, win=8192, hop=4096, fmin=65, fmax=2000):
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop]
    S = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1))
    freqs = np.fft.rfftfreq(win, 1/sr)
    m = (freqs >= fmin) & (freqs <= fmax)
    pcs = (np.round(12*np.log2(freqs[m]/440.0)).astype(int) + 9) % 12
    chroma = np.zeros(12)
    for p, col in zip(pcs, S[:, m].T):
        chroma[p] += col.sum()
    if chroma.sum() > 0:
        chroma /= chroma.sum()
    best, sc = None, -2
    for i in range(12):
        for prof, mode in ((MAJOR,'major'), (MINOR,'minor')):
            r = np.corrcoef(chroma, np.roll(prof, i))[0,1]
            if r > sc: sc, best = r, (NOTES[i], mode)
    return best, sc

if __name__ == "__main__":
    x, sr = load_wav(sys.argv[1])
    x = x[:sr*120]                       # first 2 min is plenty
    bpm = estimate_tempo(x, sr)
    (key, mode), conf = estimate_key(x, sr)
    print(json.dumps({
        "bpm": round(bpm),
        "key": f"{key} {mode}",
        "confidence": round(float(conf), 2),
        "prompt": (f"gbedu afrobeats instrumental, {round(bpm)} bpm, "
                   f"key of {key} {mode}, no vocals, no lead melody")
    }, indent=2))
