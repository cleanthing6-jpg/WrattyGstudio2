"""Music theory layer: tuning-reference estimation, key/scale detection, allowed-note sets."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scipy import signal
from . import dsp

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALES = {
    "major":            [0, 2, 4, 5, 7, 9, 11],
    "minor":            [0, 2, 3, 5, 7, 8, 10],
    "harmonic_minor":   [0, 2, 3, 5, 7, 8, 11],
    "dorian":           [0, 2, 3, 5, 7, 9, 10],
    "mixolydian":       [0, 2, 4, 5, 7, 9, 10],
    "major_pentatonic": [0, 2, 4, 7, 9],
    "minor_pentatonic": [0, 3, 5, 7, 10],
    "blues":            [0, 3, 5, 6, 7, 10],
    "chromatic":        list(range(12)),
}

KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

def scale_mask(key: int, scale: str | list[int]) -> np.ndarray:
    iv = SCALES[scale] if isinstance(scale, str) else list(scale)
    m = np.zeros(12, bool)
    for i in iv:
        m[(key + i) % 12] = True
    return m

def scale_weights(key: int, mode: str) -> np.ndarray:
    prof = KK_MAJOR if mode in ("major", "major_pentatonic", "mixolydian") else KK_MINOR
    w = np.roll(prof, key)
    return w / w.max()

def estimate_tuning_cents(x: np.ndarray, sr: int, fmin=80.0, fmax=2500.0) -> tuple[float, float]:
    n_fft = 8192
    f, t, Z = signal.stft(x, sr, nperseg=n_fft, noverlap=n_fft * 3 // 4, boundary=None, padded=False)
    mag = np.abs(Z)
    sel = (f >= fmin) & (f <= fmax)
    fs, M = f[sel], mag[sel]
    lm = np.log(M + 1e-9)
    pk = (M[1:-1] > M[:-2]) & (M[1:-1] >= M[2:]) & (M[1:-1] > 6.0 * np.median(M, axis=0)[None, :])
    kk, tt = np.nonzero(pk)
    kk = kk + 1
    a, b, c = lm[kk - 1, tt], lm[kk, tt], lm[kk + 1, tt]
    den = a - 2 * b + c
    off = np.where(np.abs(den) > 1e-9, 0.5 * (a - c) / den, 0.0)
    freq = fs[kk] + np.clip(off, -0.5, 0.5) * (fs[1] - fs[0])
    w = M[kk, tt]
    cents = (1200 * np.log2(freq / 440.0)) % 100.0
    ang = cents / 100.0 * 2 * np.pi
    z = np.sum(w * np.exp(1j * ang)) / (np.sum(w) + 1e-12)
    off_c = np.angle(z) / (2 * np.pi) * 100.0
    return float(off_c), float(np.abs(z))

def chroma_from_audio(x: np.ndarray, sr: int, tuning_cents: float = 0.0, fmin=50.0, fmax=2500.0,
                      harmonic_only: bool = True) -> np.ndarray:
    from scipy.ndimage import median_filter
    n_fft = 4096
    f, t, Z = signal.stft(x, sr, nperseg=n_fft, noverlap=n_fft * 3 // 4, boundary=None, padded=False)
    mag = np.abs(Z)
    if harmonic_only:
        H = median_filter(mag, size=(1, 17))
        P = median_filter(mag, size=(17, 1))
        mag = mag * (H ** 2 / (H ** 2 + P ** 2 + 1e-12))
    sel = (f >= fmin) & (f <= fmax)
    fs, M = f[sel], mag[sel]
    lm = np.log(M + 1e-9)
    pk = (M[1:-1] > M[:-2]) & (M[1:-1] >= M[2:]) & (M[1:-1] > 4.0 * np.median(M, axis=0)[None, :])
    kk, tt = np.nonzero(pk); kk += 1
    a, b, c = lm[kk - 1, tt], lm[kk, tt], lm[kk + 1, tt]
    den = a - 2 * b + c
    off = np.where(np.abs(den) > 1e-9, 0.5 * (a - c) / den, 0.0)
    freq = fs[kk] + np.clip(off, -0.5, 0.5) * (fs[1] - fs[0])
    w = M[kk, tt] ** 0.5
    w = w / (np.sqrt(M.sum(axis=0))[tt] + 1e-9)
    w = w * (1.0 + 1.5 * (freq < 200))
    pos = (12 * np.log2(freq / 440.0) - tuning_cents / 100.0 + 9) % 12
    lo = np.floor(pos).astype(int) % 12
    frac = pos - np.floor(pos)
    ch = np.zeros(12)
    np.add.at(ch, lo, w * (1 - frac)); np.add.at(ch, (lo + 1) % 12, w * frac)
    return ch / (ch.sum() + 1e-12)

def pitchclass_hist_from_f0(f0: np.ndarray, weights: np.ndarray | None = None, tuning_cents: float = 0.0) -> np.ndarray:
    v = f0 > 0
    midi = 69 + 12 * np.log2(f0[v] / 440.0) - tuning_cents / 100.0
    w = np.ones(v.sum()) if weights is None else weights[v]
    pos = midi % 12
    lo = np.floor(pos).astype(int) % 12
    frac = pos - np.floor(pos)
    h = np.zeros(12)
    np.add.at(h, lo, w * (1 - frac)); np.add.at(h, (lo + 1) % 12, w * frac)
    return h / (h.sum() + 1e-12)

@dataclass
class KeyEstimate:
    key: int
    mode: str
    score: float
    margin: float
    chroma: np.ndarray = field(repr=False, default=None)

    @property
    def name(self):
        return f"{NOTE_NAMES[self.key]} {self.mode}"

def detect_key(chroma: np.ndarray) -> KeyEstimate:
    scores = []
    for k in range(12):
        for mode, prof in (("major", KK_MAJOR), ("minor", KK_MINOR)):
            r = np.corrcoef(chroma, np.roll(prof, k))[0, 1]
            scores.append((r, k, mode))
    scores.sort(reverse=True)
    best = scores[0]
    rel = (best[1] + (9 if best[2] == "major" else 3)) % 12
    runner = next(s for s in scores[1:] if not (s[1] == rel and s[2] != best[2]))
    return KeyEstimate(best[1], best[2], float(best[0]), float(best[0] - runner[0]), chroma)

def adaptive_allowed(key: int, mode: str, vocal_hist: np.ndarray | None, base_scale: str | None = None,
                     chromatic_thresh: float = 0.07, genre_blue: bool = True) -> np.ndarray:
    mask = scale_mask(key, base_scale or mode)
    if vocal_hist is not None and genre_blue:
        extra = (~mask) & (vocal_hist >= chromatic_thresh)
        mask = mask | extra
    return mask
