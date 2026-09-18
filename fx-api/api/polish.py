"""polish.py - dynamic control AFTER the effects. Pure numpy, no scipy.

Standalone module: nothing in auto.py imports this yet.
Four primitives:
  dynamic_eq   - tracking dynamic EQ (harshness + sibilance), stereo-linked
  two_band_deess - de-esser built on dynamic_eq
  ms_width     - frequency-dependent width (mono bass, wider air)
  duck_wet     - reverb/delay return ducked by the dry vocal
"""
import numpy as np

NFFT = 2048
HOP = 512


def _stft(x, n=NFFT, hop=HOP, chunk=256):
    x = np.asarray(x, dtype=np.float32).ravel()
    if len(x) < n:
        p = np.zeros(n, dtype=np.float32); p[:len(x)] = x; x = p
    nf = 1 + (len(x) - n) // hop
    win = np.hanning(n).astype(np.float32)
    S = np.empty((nf, n // 2 + 1), dtype=np.complex64)
    for i in range(0, nf, chunk):
        j = min(i + chunk, nf)
        idx = np.arange(n)[None, :] + hop * np.arange(i, j)[:, None]
        S[i:j] = np.fft.rfft(x[idx] * win, axis=1)
    return S, win


def _istft(S, win, hop=HOP, length=None):
    n = win.shape[0]
    out = np.zeros(S.shape[0] * hop + n, dtype=np.float32)
    acc = np.zeros_like(out)
    ww = (win * win).astype(np.float32)
    for i in range(0, S.shape[0], 256):
        j = min(i + 256, S.shape[0])
        fr = np.fft.irfft(S[i:j], n, axis=1).astype(np.float32) * win
        for k in range(j - i):
            p = (i + k) * hop
            out[p:p + n] += fr[k]
            acc[p:p + n] += ww
    acc[acc < 1e-8] = 1.0
    y = out / acc
    return y if length is None else y[:length]


def _smooth(x, fast_frames=1.0, slow_frames=8.0):
    """One-pole smoothing. fast when the value drops (more reduction), slow when it rises."""
    f = 1.0 - np.exp(-1.0 / max(1.0, float(fast_frames)))
    s = 1.0 - np.exp(-1.0 / max(1.0, float(slow_frames)))
    y = np.empty(len(x), dtype=np.float32)
    v = 0.0
    for i in range(len(x)):
        c = float(x[i])
        v += (f if c < v else s) * (c - v)
        y[i] = v
    return y


def _dyn_gain(key, sr, specs):
    """Per-bin, per-frame real gain. Thresholds are RELATIVE to each band's median."""
    S, win = _stft(key)
    mag = np.abs(S) * (2.0 / max(1e-9, float(win.sum())))
    freq = np.fft.rfftfreq(NFFT, 1.0 / float(sr))
    hop_ms = 1000.0 * HOP / float(sr)
    g = np.ones_like(mag, dtype=np.float32)
    stats = []
    for b in specs:
        lo, hi, off, max_db, ratio, atk_ms, rel_ms = b
        m = (freq >= lo) & (freq <= hi)
        if not m.any():
            stats.append((lo, hi, None, None, 0.0, 0.0, 0.0)); continue
        band = np.sqrt(np.mean(np.square(mag[:, m]), axis=1))
        edb = 20.0 * np.log10(band + 1e-12)
        med = float(np.median(edb))
        thr = med + float(off)
        over = np.maximum(edb - thr, 0.0)
        red = -np.minimum(over * (1.0 - 1.0 / float(ratio)), float(max_db))
        red = _smooth(red, max(1.0, atk_ms / hop_ms), max(1.0, rel_ms / hop_ms))
        g[:, m] *= (10.0 ** (red[:, None] / 20.0)).astype(np.float32)
        act = 100.0 * float(np.count_nonzero(red < -0.1)) / max(1, len(red))
        stats.append((lo, hi, med, thr, float(np.mean(red)), float(np.min(red)), act))
    return g, win, stats


def calibrate(x, sr, bands=((2500.0, 4500.0), (5500.0, 9000.0)),
              offsets=(3.0, 6.0, 9.0, 12.0)):
    """How much time each band would spend over threshold, per offset (dB above median)."""
    key = x.mean(axis=0) if x.ndim > 1 else x
    S, win = _stft(key)
    mag = np.abs(S) * (2.0 / max(1e-9, float(win.sum())))
    freq = np.fft.rfftfreq(NFFT, 1.0 / float(sr))
    rows = []
    for lo, hi in bands:
        m = (freq >= lo) & (freq <= hi)
        if not m.any():
            continue
        band = np.sqrt(np.mean(np.square(mag[:, m]), axis=1))
        edb = 20.0 * np.log10(band + 1e-12)
        med = float(np.median(edb))
        pct = []
        for off in offsets:
            over = np.maximum(edb - (med + off), 0.0)
            pct.append(100.0 * float(np.count_nonzero(over > 0.2)) / max(1, len(over)))
        rows.append((lo, hi, med, list(zip(offsets, pct))))
    return rows


def _specs(harsh_off=12.0, sib_off=10.0):
    """(lo_hz, hi_hz, offset_db_above_median, max_cut_db, ratio, attack_ms, release_ms)"""
    return [
        (2500.0, 4500.0, float(harsh_off), 3.0, 3.0, 10.0, 80.0),
        (5500.0, 9000.0, float(sib_off), 2.5, 3.0, 2.0, 40.0),
    ]


def dynamic_eq(x, sr, specs=None, get_stats=False):
    if specs is None:
        specs = _specs()
    x = np.asarray(x, dtype=np.float32)
    single = x.ndim == 1
    if single:
        x = x[None, :]
    key = x.mean(axis=0)
    g, win, stats = _dyn_gain(key, sr, specs)
    out = np.empty_like(x)
    for c in range(x.shape[0]):
        Sc, _ = _stft(x[c])
        out[c] = _istft(Sc * g, win, length=x.shape[1])
    res = out[0] if single else out
    return (res, stats) if get_stats else res


def two_band_deess(x, sr, get_stats=False):
    return dynamic_eq(x, sr, (SIB_LOW, SIB_HI), get_stats=get_stats)


def ms_width(x, sr, mono_below=120.0, air_hz=5000.0, air_boost=1.15):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim < 2 or x.shape[0] < 2:
        return x
    M = ((x[0] + x[1]) * 0.5).astype(np.float32)
    Sd = ((x[0] - x[1]) * 0.5).astype(np.float32)
    Sm, win = _stft(Sd)
    freq = np.fft.rfftfreq(NFFT, 1.0 / float(sr))
    w = np.ones_like(freq, dtype=np.float32)
    w[freq < mono_below] = 0.0
    r = (freq >= mono_below) & (freq < 800.0)
    w[r] = np.clip((freq[r] - mono_below) / max(1.0, 800.0 - mono_below), 0.0, 1.0)
    u = freq >= air_hz
    w[u] = 1.0 + (air_boost - 1.0) * np.clip(
        (freq[u] - air_hz) / max(1.0, 12000.0 - air_hz), 0.0, 1.0)
    Sd2 = _istft(Sm * w[None, :], win, length=x.shape[1])
    return np.stack([M + Sd2, M - Sd2]).astype(np.float32)


def duck_wet(dry, wet, sr, depth_db=-3.5, atk_ms=15.0, rel_ms=220.0, thr_db=-32.0):
    dry = np.asarray(dry, dtype=np.float32)
    wet = np.asarray(wet, dtype=np.float32)
    key = dry.mean(axis=0) if dry.ndim > 1 else dry
    S, _ = _stft(key)
    env = np.sqrt(np.mean(np.square(np.abs(S)), axis=1))
    edb = 20.0 * np.log10(env + 1e-12)
    act = np.clip((edb - thr_db) / 20.0, 0.0, 1.0).astype(np.float32)
    hop_ms = 1000.0 * HOP / float(sr)
    sm = _smooth(act, max(1.0, atk_ms / hop_ms), max(1.0, rel_ms / hop_ms))
    gf = (10.0 ** ((sm * float(depth_db)) / 20.0)).astype(np.float32)
    n = wet.shape[-1]
    g = np.ones(n, dtype=np.float32)
    for i in range(len(gf)):
        p = i * HOP
        if p >= n:
            break
        g[p:min(p + HOP, n)] = gf[i]
    return (wet * g).astype(np.float32)
