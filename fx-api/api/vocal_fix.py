"""vocal_fix.py -- vocal 'forwardness' guard for the Afrobeats auto-mix.

Problem it solves: the engine pushes vocal presence (raise + beat ducking) until the vocal sits far
above the beat in 500 Hz-4 kHz. Commercial Afrobeats mixes (5 references, measured as acapella
power / (master - acapella), 250 Hz-16 kHz) keep the vocal much closer to the beat there.

Call it on the PROCESSED vocal bus (`core`) and the PROCESSED beat (`ducked`) right before they
are summed.  It only cuts a band when the vocal is over its limit, cuts at most `cap_db` per band,
never changes overall gain, and leaves the vocal alone if the vocal is quiet there already.
Pure numpy/scipy."""
import numpy as np
import scipy.signal as sg
from adaptive_tone import _peak

BANDS = {
    "500-2k": (500, 2000, 10.3),
}

def _band_pow(x, sr, N=8192):
    m = np.asarray(x, dtype=np.float64)
    m = m.mean(axis=0) if m.ndim == 2 else m
    k = len(m) // N
    X = np.abs(np.fft.rfft(m[:k * N].reshape(k, N) * np.hanning(N), axis=1)) ** 2
    f = np.fft.rfftfreq(N, 1.0 / sr)
    return {n: X[:, (f >= lo) & (f < hi)].sum(1) for n, (lo, hi, _) in BANDS.items()}, X.sum(1)

def measure(voc, rest, sr):
    n = min(np.shape(voc)[-1], np.shape(rest)[-1])
    pv, tv = _band_pow(np.asarray(voc)[..., :n], sr)
    pr, _ = _band_pow(np.asarray(rest)[..., :n], sr)
    k = min(len(tv), len(next(iter(pr.values()))))
    e = 10 * np.log10(tv[:k] + 1e-20)
    act = e > (np.percentile(e, 95) - 30.0)
    if act.sum() < 10:
        act = np.ones(k, bool)
    return {b: float(10 * np.log10((pv[b][:k][act].sum() + 1e-20) / (pr[b][:k][act].sum() + 1e-20))) for b in BANDS}

def plan(voc, rest, sr, margin_db=0.5, gain=0.85, cap_db=1.5):
    m = measure(voc, rest, sr)
    cuts = {}
    for b, (lo, hi, lim) in BANDS.items():
        over = m[b] - lim
        if over > margin_db:
            cuts[b] = -float(np.clip(gain * over, 0.0, cap_db))
    return m, cuts

def forward_guard(voc, rest, sr, **kw):
    a = np.asarray(voc, dtype=np.float32)
    m, cuts = plan(a, rest, sr, **kw)
    if not cuts:
        return a, {"measured": {k: round(v, 1) for k, v in m.items()}, "cuts_db": {}}
    sos = [_peak(float(np.sqrt(BANDS[b][0] * BANDS[b][1])), g, 1.0, sr) for b, g in cuts.items()]
    y = sg.sosfilt(np.vstack(sos), a, axis=-1).astype(np.float32)
    m2 = measure(y, rest, sr)
    return y, {"measured": {k: round(v, 1) for k, v in m.items()},
               "cuts_db": {k: round(v, 2) for k, v in cuts.items()},
               "after": {k: round(v, 1) for k, v in m2.items()}}
