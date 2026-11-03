"""
vocal_align.py -- MODULE 1: adaptive phase alignment (vocal to beat).
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

HOP_S = 0.001
DEADBAND_MS = 1.0
MIN_CONFIDENCE = 0.55
MIN_ONSETS = 30

def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=0) if x.ndim == 2 else x

def _onset_env(x, sr, bands):
    hop = max(1, int(round(HOP_S * sr)))
    nper = 1 << int(np.ceil(np.log2(max(64, 0.006 * sr))))
    f, t, S = sg.stft(x, sr, nperseg=nper, noverlap=nper - hop, window="hann", boundary=None, padded=False)
    P = np.abs(S) ** 2
    out = np.zeros(P.shape[1])
    for lo, hi, w in bands:
        e = P[(f >= lo) & (f < min(hi, sr / 2 * 0.98))].sum(axis=0) + 1e-12
        le = 10 * np.log10(e)
        le = ndimage.uniform_filter1d(le, 3)
        rise = np.maximum(le[3:] - le[:-3], 0.0)
        rise = np.concatenate([np.zeros(3), rise])
        scale = np.median(rise[rise > 0]) if (rise > 0).any() else 1.0
        out += w * rise / (scale + 1e-9)
    out = out - ndimage.uniform_filter1d(out, 201)
    return np.maximum(out, 0.0), t[0] if len(t) else 0.0

VOCAL_BANDS = [(300, 1500, 1.0), (1500, 8000, 1.0)]
BEAT_BANDS = [(40, 150, 1.0), (150, 600, 0.8), (2000, 9000, 0.7)]

def _syllables(env):
    e = ndimage.gaussian_filter1d(env, 8.0)
    pos = e[e > 0]
    if pos.size < 10: return np.array([], dtype=int)
    p, _ = sg.find_peaks(e, height=np.percentile(pos, 85), distance=int(0.09 / HOP_S))
    return p

def vocal_density(voc, sr):
    m = _mono(voc)
    env, _ = _onset_env(m, sr, VOCAL_BANDS)
    pk = _syllables(env)
    n = int(0.05 * sr); k = len(m) // n
    e = 20 * np.log10(np.sqrt((m[: k * n].reshape(k, n) ** 2).mean(1)) + 1e-9)
    active_s = max(float((e > np.percentile(e, 95) - 35).sum()) * 0.05, 1.0)
    return len(pk) / active_s, pk, env

def max_shift_for(rate):
    return float(np.interp(rate, [2.5, 5.5], [22.0, 8.0]))

def _lag_sums(v, b, W, starts):
    n = len(v); out = np.zeros((len(starts), 2 * W + 1))
    for j, L in enumerate(range(-W, W + 1)):
        if L >= 0:
            prod = np.zeros(n); prod[: n - L] = v[L:] * b[: n - L]
        else:
            prod = np.zeros(n); prod[-L:] = v[: n + L] * b[-L:]
        out[:, j] = np.add.reduceat(prod, starts)
    return out

def _peak_lag(c, W, sigma_ms):
    c = ndimage.gaussian_filter1d(c, sigma_ms / (HOP_S * 1000))
    k = int(np.argmax(c))
    if 0 < k < len(c) - 1:
        a, b, d = c[k - 1], c[k], c[k + 1]; den = a - 2 * b + d
        kk = k + 0.5 * (a - d) / den if abs(den) > 1e-15 else float(k)
    else:
        kk = float(k)
    return (kk - W) * HOP_S * 1000.0, c, k

def estimate(voc, beat, sr, max_shift_ms=None):
    m_v, m_b = _mono(voc), _mono(beat)
    rate, pk, env_v = vocal_density(m_v, sr)
    lim = max_shift_ms if max_shift_ms is not None else max_shift_for(rate)
    env_b, _ = _onset_env(m_b, sr, BEAT_BANDS)
    n = min(len(env_v), len(env_b))
    v = ndimage.gaussian_filter1d(env_v[:n], 2.0); b = ndimage.gaussian_filter1d(env_b[:n], 2.0)
    v = (v - v.mean()) / (v.std() + 1e-9); b = (b - b.mean()) / (b.std() + 1e-9)
    W = int(round((lim + 6.0) / (HOP_S * 1000)))
    blk = int(2.5 / HOP_S); starts = np.arange(0, n - blk // 2, blk)
    S = _lag_sums(v, b, W, starts)
    c_all = S.sum(0) / n
    lag, cs, k = _peak_lag(c_all, W, 3.0)
    peak = cs[k]
    rng = np.random.default_rng(1234); nulls = []
    for _ in range(30):
        sh = int(rng.uniform(3.0, max(3.5, n * HOP_S - 3.0)) / HOP_S)
        Sn = _lag_sums(np.roll(v, sh), b, W, starts)
        nulls.append(ndimage.gaussian_filter1d(Sn.sum(0) / n, 3.0 / (HOP_S * 1000)).max())
    null95 = float(np.percentile(nulls, 95))
    ratio = float(peak / (null95 + 1e-9))
    lags = []
    for _ in range(80):
        idx = rng.integers(0, len(starts), len(starts))
        lags.append(_peak_lag(S[idx].sum(0) / n, W, 3.0)[0])
    boot = float(np.std(lags))
    edge = float(max(cs[0], cs[-1]) / (peak + 1e-12))
    at_edge = abs(lag) > lim + 4.5
    c_sig = float(np.clip((ratio - 1.3) / 1.2, 0, 1))
    c_boot = float(np.clip((4.0 - boot) / 3.0, 0, 1))
    c_edge = float(np.clip((0.85 - edge) / 0.35, 0, 1))
    c_n = float(np.clip((len(pk) - MIN_ONSETS + 25) / 50.0, 0, 1))
    conf = float((c_sig * c_boot * c_edge * c_n) ** 0.25)
    return {"offset_ms": float(lag), "confidence": round(conf, 3),
            "parts": {"significant": round(c_sig, 2), "stable": round(c_boot, 2), "inside_window": round(c_edge, 2), "evidence": round(c_n, 2)},
            "peak_vs_chance": round(ratio, 2), "bootstrap_std_ms": round(boot, 2), "onsets": int(len(pk)),
            "attacks_per_s": round(float(rate), 2), "max_shift_ms": round(float(lim), 1), "at_search_edge": bool(at_edge)}

def shift_ms(x, sr, ms):
    s = ms * sr / 1000.0
    ia = int(np.floor(s)); fr = s - ia
    a = np.asarray(x)
    one = a.ndim == 1
    A = a[None, :] if one else a
    out = np.zeros(A.shape, dtype=np.float64)
    if fr > 1e-6:
        taps = 32
        k = np.arange(-taps + 1, taps + 1) - fr
        h = np.sinc(k) * np.kaiser(2 * taps, 9.0)
        h /= h.sum()
        for ch in range(A.shape[0]):
            y = sg.fftconvolve(A[ch].astype(np.float64), h[::-1], mode="full")
            y = y[taps - 1: taps - 1 + A.shape[1]]
            out[ch] = y
    else:
        out = A.astype(np.float64).copy()
    if ia > 0:
        out = np.concatenate([out[:, ia:], np.zeros((out.shape[0], ia))], axis=1)
    elif ia < 0:
        out = np.concatenate([np.zeros((out.shape[0], -ia)), out[:, :out.shape[1] + ia]], axis=1)
    out = out.astype(a.dtype if np.issubdtype(a.dtype, np.floating) else np.float32)
    return out[0] if one else out

def align(voc, beat, sr, groove_ms=0.0, max_shift_ms=None, min_confidence=MIN_CONFIDENCE):
    v = np.asarray(voc)
    if v.size == 0 or np.asarray(beat).size == 0 or v.shape[-1] < sr * 8:
        return voc, {"action": "abort", "reason": "too short to measure"}
    try:
        est = estimate(voc, beat, sr, max_shift_ms)
    except Exception as e:
        return voc, {"action": "abort", "reason": "measurement failed: %s" % str(e)[:80]}
    rep = dict(est)
    off = est["offset_ms"] - groove_ms
    rep["measured_offset_ms"] = round(est["offset_ms"], 2)
    if est["onsets"] < MIN_ONSETS:
        rep.update(action="abort", reason="too few syllable attacks (%d) to trust the lock" % est["onsets"]); return voc, rep
    if est["confidence"] < min_confidence:
        rep.update(action="abort", reason="low confidence %.2f" % est["confidence"]); return voc, rep
    if est["at_search_edge"] or abs(off) > est["max_shift_ms"]:
        rep.update(action="abort", reason="needed shift exceeds limit"); return voc, rep
    if abs(off) < DEADBAND_MS:
        rep.update(action="bypass", reason="already within %.1f ms" % DEADBAND_MS, applied_ms=0.0); return voc, rep
    out = shift_ms(voc, sr, off)
    rep.update(action="aligned", applied_ms=round(-off, 2), reason="vocal was %.1f ms %s the beat" % (abs(off), "behind" if off > 0 else "ahead of"))
    return out, rep

def align_group(stems, beat, sr, lead_index=0, **kw):
    out0, rep = align(stems[lead_index], beat, sr, **kw)
    if rep.get("action") != "aligned":
        return list(stems), rep
    ms = -rep["applied_ms"]
    return [shift_ms(s, sr, ms) for s in stems], rep
