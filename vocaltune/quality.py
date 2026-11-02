"""Recording-quality analysis. SNR uses per-frequency-bin minimum statistics (not frame-energy percentiles),
so continuous singing with no silent gaps is not mistaken for 'dynamic range'."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
from scipy import signal

@dataclass
class Quality:
    snr_db: float
    noise_floor_dbfs: float
    bandwidth_hz: float
    clip_ratio: float
    hum_hz: float | None
    peak_dbfs: float
    score: float
    profile: str

    def asdict(self):
        return asdict(self)

def noise_psd(x, sr, nfft=2048):
    f, t, Z = signal.stft(x, sr, nperseg=nfft, noverlap=nfft * 3 // 4, boundary=None, padded=False)
    P = np.abs(Z) ** 2
    from scipy.ndimage import uniform_filter1d
    Ps = uniform_filter1d(P, 5, axis=1)
    floor = np.percentile(Ps, 8, axis=1) * 1.8
    return f, t, P, floor

def analyze_quality(x: np.ndarray, sr: int) -> Quality:
    x = np.asarray(x, dtype=np.float64)
    peak = float(np.max(np.abs(x)) + 1e-12)
    f, t, P, floor = noise_psd(x, sr)
    frame_pow = P.sum(axis=0)
    floor_pow = float(floor.sum())
    thr = np.percentile(frame_pow, 60)
    act = frame_pow >= thr
    sig_pow = float(np.mean(frame_pow[act]))
    snr = 10 * np.log10(max(sig_pow - floor_pow, 1e-12) / (floor_pow + 1e-12))
    snr = float(np.clip(snr, 0, 60))
    nf_dbfs = float(10 * np.log10(floor_pow / (len(f)) + 1e-18))
    
    spec = P[:, act].mean(axis=1)
    cs = np.cumsum(spec) / (spec.sum() + 1e-18)
    bw = float(f[np.searchsorted(cs, 0.95)])
    
    from scipy.ndimage import uniform_filter1d
    ratio = uniform_filter1d(spec, 15) / (uniform_filter1d(floor, 15) + 1e-18)
    df = f[1] - f[0]
    w = max(3, int(1500.0 / df))
    low = ratio < 3.0
    eff = float(f[-1])
    for i in range(int(800.0 / df), len(f) - w):
        if low[i:i + w].all():
            eff = float(f[i]); break
            
    clip = float(np.mean(np.abs(x) > 0.985 * peak)) if peak > 0.9 else 0.0
    hum = None
    fl = floor
    for h in (50.0, 60.0):
        i = np.argmin(np.abs(f - h))
        loc = np.median(fl[max(1, i - 6):i + 7])
        if fl[max(0, i - 1):i + 2].max() > 3.5 * loc and f[i] > 30:
            hum = h
            
    snr_s = np.clip((snr - 10) / 30, 0, 1)
    bw_s = np.clip((eff - 4000) / 8000, 0, 1)
    clip_s = 1 - np.clip(clip * 200, 0, 1)
    score = float(0.55 * snr_s + 0.30 * bw_s + 0.15 * clip_s)
    profile = "studio" if score > 0.78 else "good" if score > 0.58 else "phone" if score > 0.33 else "poor"
    return Quality(snr, nf_dbfs, eff, clip, hum, 20 * np.log10(peak), score, profile)
