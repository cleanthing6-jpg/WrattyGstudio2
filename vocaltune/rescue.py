"""Phone-recording rescue: rumble/hum removal and low-artifact spectral-gate denoising.
Used (a) on the ANALYSIS copy so pitch tracking is robust, and optionally (b) on the output."""
from __future__ import annotations
import numpy as np
from scipy import signal
from scipy.ndimage import uniform_filter1d, maximum_filter1d
from . import dsp, quality as Q

def remove_hum(x, sr, hum_hz, harmonics=6, q=35.0):
    y = x
    for k in range(1, harmonics + 1):
        f0 = hum_hz * k
        if f0 >= sr / 2 - 100:
            break
        b, a = signal.iirnotch(f0, q, fs=sr)
        y = signal.filtfilt(b, a, y)
    return y

def denoise(x, sr, strength=0.7, nfft=2048, floor_db=-14.0, hp_hz=70.0):
    x = dsp.zero_phase(np.asarray(x, dtype=np.float64), dsp.butter_sos("highpass", hp_hz, sr, 4))
    hop = nfft // 4
    f, t, Z = signal.stft(x, sr, nperseg=nfft, noverlap=nfft - hop, boundary="zeros", padded=True)
    P = np.abs(Z) ** 2
    Ps = uniform_filter1d(P, 5, axis=1)
    N = np.percentile(Ps, 8, axis=1) * 1.8
    N = uniform_filter1d(N, 5)[:, None]
    over = 1.0 + 1.5 * strength
    snr_post = P / (N * over + 1e-18)
    G = np.maximum(1.0 - 1.0 / np.maximum(snr_post, 1e-6), 0.0)
    G = np.sqrt(G)
    gmin = 10 ** ((floor_db * strength) / 20.0)
    G = np.maximum(G, gmin)
    
    out = np.empty_like(G); prev = G[:, 0].copy()
    a_att, a_rel = 0.2, 0.75
    for i in range(G.shape[1]):
        g = G[:, i]
        coef = np.where(g > prev, a_att, a_rel)
        prev = coef * prev + (1 - coef) * g
        out[:, i] = prev
    out = uniform_filter1d(out, 5, axis=0)
    out[f < 400] = np.maximum(out[f < 400], 0.5 + 0.5 * out[f < 400])
    
    _, y = signal.istft(Z * out, sr, nperseg=nfft, noverlap=nfft - hop, boundary=True)
    y = y[: len(x)]
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    return y

def rescue(x, sr, quality: Q.Quality | None = None, strength=0.7):
    y = np.asarray(x, dtype=np.float64)
    q = quality or Q.analyze_quality(y, sr)
    if q.hum_hz:
        y = remove_hum(y, sr, q.hum_hz)
    return denoise(y, sr, strength=strength)
