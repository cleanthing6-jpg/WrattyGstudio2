#!/usr/bin/env python3
"""Strip sustained singing from a mono reference, keep the hand-hit percussion.
Usage: python strip_vocal.py ref.wav ref_perc.wav   (BIAS: 1.0=mild, 4.0=aggressive)
"""
import sys, wave, numpy as np

IN  = sys.argv[1] if len(sys.argv) > 1 else "ref.wav"
OUT = sys.argv[2] if len(sys.argv) > 2 else "ref_perc.wav"
N, HOP, KT, KF, BIAS = 2048, 512, 31, 31, 4.0

def read_wav(path):
    with wave.open(path, "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    assert sw == 2, "need 16-bit PCM: ffmpeg -i in -ac 1 -ar 44100 -c:a pcm_s16le ref.wav"
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return np.ascontiguousarray(x), sr

def write_wav(path, x, sr):
    y = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(y.tobytes())

def medfilt(S, k, axis):
    """Median filter with edge padding, one row/column at a time (phone-friendly)."""
    p = k // 2
    out = np.empty_like(S)
    if axis == 0:
        for t in range(S.shape[1]):
            c = np.pad(S[:, t], p, mode="edge")
            out[:, t] = np.median(np.lib.stride_tricks.sliding_window_view(c, k), axis=-1)
    else:
        for f in range(S.shape[0]):
            r = np.pad(S[f, :], p, mode="edge")
            out[f, :] = np.median(np.lib.stride_tricks.sliding_window_view(r, k), axis=-1)
    return out

def stft(x):
    win = np.hanning(N).astype(np.float32)
    pad = N
    xp = np.concatenate([np.zeros(pad, np.float32), x, np.zeros(pad + N, np.float32)])
    nf = 1 + (len(xp) - N) // HOP
    idx = np.arange(N)[None, :] + HOP * np.arange(nf)[:, None]
    spec = np.fft.rfft(xp[idx] * win, axis=1)
    return spec.T, win, len(x), pad          # (F, T)

def istft(spec, win, length, pad):
    fr = np.fft.irfft(spec.T, n=N, axis=1)   # (T, N)
    out  = np.zeros(pad + fr.shape[0] * HOP + N, np.float32)
    wsum = np.zeros_like(out)
    w2 = win * win
    for i in range(fr.shape[0]):
        s = pad + i * HOP
        out[s:s+N]  += fr[i] * win
        wsum[s:s+N] += w2
    out = np.divide(out, np.maximum(wsum, 1e-8), where=wsum > 1e-8)
    return out[pad:pad+length].astype(np.float32)

x, sr = read_wav(IN)
assert x.size > N * 2, "clip too short"
print("in : %.2fs  peak=%.3f  rms=%.4f" % (len(x)/sr, float(np.abs(x).max()),
                                           float(np.sqrt((x**2).mean()))))

spec, win, length, pad = stft(x)
S = np.abs(spec)
Harm = medfilt(S, KT, axis=1)     # smooth over TIME  -> sustained tones (voice)
Perc = medfilt(S, KF, axis=0)     # smooth over FREQ  -> transients (hits)
Mp = (Perc**2) / (Perc**2 + BIAS * Harm**2 + 1e-10)

y = istft(spec * Mp, win, length, pad)
write_wav(OUT, y, sr)
print("out: %.2fs  peak=%.3f  rms=%.4f  (bias=%.1f)" % (len(y)/sr, float(np.abs(y).max()),
                                                         float(np.sqrt((y**2).mean())), BIAS))
print("wrote", OUT)
