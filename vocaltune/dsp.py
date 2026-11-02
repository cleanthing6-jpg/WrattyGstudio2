import numpy as np
from scipy import signal

def to_mono(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return x if x.ndim == 1 else x.mean(axis=1)

def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x.copy()
    from math import gcd
    g = gcd(int(sr_in), int(sr_out))
    return signal.resample_poly(x, int(sr_out) // g, int(sr_in) // g)

def butter_sos(kind: str, cutoff, sr: int, order: int = 4):
    return signal.butter(order, cutoff, btype=kind, fs=sr, output="sos")

def zero_phase(x, sos):
    return signal.sosfiltfilt(sos, x)

def smoothstep(x, lo, hi):
    t = np.clip((np.asarray(x, dtype=np.float64) - lo) / max(hi - lo, 1e-12), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def normalized_smooth(values: np.ndarray, weights: np.ndarray, sigma: float) -> np.ndarray:
    from scipy.ndimage import gaussian_filter1d
    num = gaussian_filter1d(values * weights, sigma, mode="constant")
    den = gaussian_filter1d(weights.astype(np.float64), sigma, mode="constant")
    out = np.where(den > 1e-6, num / np.maximum(den, 1e-12), 0.0)
    return out

def cubic_sample(x: np.ndarray, pos: np.ndarray) -> np.ndarray:
    pos = np.asarray(pos, dtype=np.float64)
    i = np.floor(pos).astype(np.int64)
    f = pos - i
    n = len(x)
    i0 = np.clip(i - 1, 0, n - 1)
    i1 = np.clip(i, 0, n - 1)
    i2 = np.clip(i + 1, 0, n - 1)
    i3 = np.clip(i + 2, 0, n - 1)
    p0, p1, p2, p3 = x[i0], x[i1], x[i2], x[i3]
    return p1 + 0.5 * f * (p2 - p0 + f * (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3 + f * (3.0 * (p1 - p2) + p3 - p0)))

def hz_to_cents(f, ref=440.0):
    f = np.asarray(f, dtype=np.float64)
    return 1200.0 * np.log2(np.maximum(f, 1e-9) / ref)

def cents_to_hz(c, ref=440.0):
    return ref * 2.0 ** (np.asarray(c, dtype=np.float64) / 1200.0)
