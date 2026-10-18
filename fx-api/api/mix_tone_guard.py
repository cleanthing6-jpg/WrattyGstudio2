"""mix_tone_guard.py -- final-mix tone guard for the Afrobeats engine.
Reference ranges = min/max of 5 commercial Afrobeats masters (Burna Boy, Davido, Rema,
Fola, Boi Chase), mid-channel band power relative to total (dB). Only moves a band that is
OUTSIDE the padded range, by at most `cap` dB. Run on the pre-limiter mix, before loudness
targeting. Pure numpy/scipy (no numba)."""
import numpy as np
import scipy.signal as sg
from adaptive_tone import _peak

BANDS = [(150, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000)]
REF = [(-12.0, -8.4), (-11.2, -7.6), (-12.8, -9.1), (-17.1, -11.8),
       (-22.3, -15.9), (-23.1, -20.2), (-27.6, -21.7)]


def measure(x, sr):
    x = np.asarray(x, dtype=np.float64)
    M = x.mean(axis=0) if x.ndim == 2 else x
    S = 0.5 * (x[0] - x[1]) if x.ndim == 2 and x.shape[0] > 1 else np.zeros_like(M)
    f, PM = sg.welch(M, sr, nperseg=16384)
    _, PS = sg.welch(S, sr, nperseg=16384)
    tot = PM.sum() + PS.sum() + 1e-20
    return {b: 10 * np.log10(PM[(f >= b[0]) & (f < b[1])].sum() / tot + 1e-12) for b in BANDS}


def guard(x, sr, pad=1.0, gain=0.8, cap=2.0):
    a = np.asarray(x, dtype=np.float32)
    m = measure(a, sr)
    sos, moves = [], {}
    for b, (lo, hi) in zip(BANDS, REF):
        v = m[b]
        err = v - (hi + pad) if v > hi + pad else v - (lo - pad) if v < lo - pad else 0.0
        g = -float(np.clip(gain * err, -cap, cap))
        if abs(g) >= 0.3:
            sos.append(_peak(float(np.sqrt(b[0] * b[1])), g, 1.4, sr))
            moves["%d-%d" % b] = round(g, 2)
    if not sos:
        return a, {"moves": {}, "measured": {"%d-%d" % k: round(v, 1) for k, v in m.items()}}
    y = sg.sosfilt(np.vstack(sos), a, axis=-1).astype(np.float32)
    return y, {"moves": moves, "measured": {"%d-%d" % k: round(v, 1) for k, v in m.items()}}
