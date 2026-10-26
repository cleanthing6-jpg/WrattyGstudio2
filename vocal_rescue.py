"""
vocal_rescue.py -- adaptive rescue for bad (phone / untreated-room) vocal recordings.
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

BANDS = np.array([100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500,
                  3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000], float)
REF_VOC = np.array([-45.2, -29.1, -18.0, -14.4, -11.6, -12.3, -8.4, -7.1, -9.5, -10.9, -12.7, -12.4,
                    -15.0, -19.1, -18.6, -22.5, -21.4, -22.5, -21.8, -20.7, -21.9, -25.4, -32.2])
SIB_TOP = -6.1
HF_BOTTOM = -17.5
BAD_AT = 0.30
STAGE_AT = 0.15

def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=0) if x.ndim == 2 else x

def _frames(m, sr, win=0.02):
    n = max(1, int(win * sr)); k = len(m) // n
    return m[: k * n].reshape(k, n), n

def _active(m, sr):
    fr, n = _frames(m, sr)
    e = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    return fr, e, e > (np.percentile(e, 95) - 40.0)

def _bands(P, f):
    b = lambda a, c: P[(f >= a) & (f < c)].sum() + 1e-20
    return b

def _ltas_db(m, sr):
    fr, e, act = _active(m, sr)
    seg = fr[act].reshape(-1) if act.sum() > 10 else m
    f, P = sg.welch(seg, sr, nperseg=8192)
    edges = np.concatenate([[BANDS[0] / 2 ** (1 / 6)], BANDS * 2 ** (1 / 6)])
    edges = np.minimum(edges, sr / 2)
    B = np.array([P[(f >= edges[i]) & (f < edges[i + 1])].sum() for i in range(len(BANDS))]) + 1e-20
    return 10 * np.log10(B / B.sum()), f, P

def _indices(m, sr):
    _, f, P = _ltas_db(m, sr)
    b = _bands(P, f)
    return (10 * np.log10(b(5000, 9000) / b(1000, 4000)),
            10 * np.log10(b(10000, min(16000, sr / 2 * 0.98)) / b(1000, 4000)))

def _rt60(m, sr):
    fr, n = _frames(m, sr, 0.01)
    e = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    e = ndimage.uniform_filter1d(e, 3)
    top = np.percentile(e, 90); floor = np.percentile(e, 5)
    act = e > top - 30
    decs = []
    i = 15
    while i < len(e) - 60:
        if act[i - 1] and not act[i] and act[i - 15:i].all():
            L0 = np.mean(e[i - 3:i]); seg = e[i:i + 60]
            if L0 - floor > 25:
                idx = np.where(seg < L0 - 15)[0]
                if len(idx) and not (e[i:i + idx[0] + 1] > top - 30).any():
                    decs.append(idx[0] * 0.01)
            i += 30
        i += 1
    rt = float(np.median(decs) * 4.0) if len(decs) >= 4 else None
    return rt

def analyze(voc, sr):
    m = _mono(voc)
    sib, hf = _indices(m, sr)
    L, f, P = _ltas_db(m, sr)
    dev = L - REF_VOC
    dev = dev - np.median(dev)
    dist = float(np.sqrt((dev ** 2).mean()))
    rt = _rt60(m, sr)
    sev = {"sibilance": float(np.clip((sib - SIB_TOP) / 6.0, 0, 1)),
           "bandwidth": float(np.clip((HF_BOTTOM - hf) / 12.0, 0, 1)),
           "tone": float(np.clip((dist - 4.5) / 5.0, 0, 1)),
           "room": float(np.clip(((rt or 0.0) - 0.45) / 0.5, 0, 1))}
    bad = max(sev.values()) >= BAD_AT
    return {"sib_db": round(float(sib), 1), "hf_db": round(float(hf), 1), "tone_dist_db": round(dist, 1),
            "rt60_s": None if rt is None else round(rt, 2),
            "severity": {k: round(v, 2) for k, v in sev.items()}, "bad": bool(bad)}, dev

def _stft(x, sr, n=2048):
    return sg.stft(x, sr, nperseg=n, noverlap=n * 3 // 4, window="hann")

def _istft(S, sr, length, n=2048):
    _, y = sg.istft(S, sr, nperseg=n, noverlap=n * 3 // 4, window="hann")
    y = y[:length]
    return np.pad(y, (0, max(0, length - len(y))))

def _each(voc, fn):
    x = np.asarray(voc, dtype=np.float64)
    return fn(x) if x.ndim == 1 else np.stack([fn(c) for c in x])

def _dereverb(x, sr, rt60, sev):
    rt60 = float(np.clip(rt60, 0.25, 1.2))
    alpha = 0.8 + 0.8 * sev
    gmin = 10 ** (-(6.0 + 6.0 * sev) / 20)
    n = 2048; hop = n // 4
    delay = max(1, int(round(0.06 * sr / hop)))
    decay = np.exp(-13.8 * (delay * hop / sr) / rt60)

    def one(c):
        f, t, S = _stft(c, sr, n)
        P = np.abs(S) ** 2
        Ps = ndimage.uniform_filter1d(P, 3, axis=1, mode="nearest")
        late = np.zeros_like(P)
        late[:, delay:] = decay * Ps[:, :-delay]
        G = np.sqrt(np.maximum(1.0 - alpha * late / (P + 1e-12), gmin ** 2))
        G = ndimage.uniform_filter(G, size=(5, 3), mode="nearest")
        return _istft(S * G, sr, len(c), n)
    return _each(x, one)

def _tone(x, sr, dev, sev):
    freqs = np.concatenate([[0.0], BANDS, [sr / 2]])
    g = -0.5 * (0.5 + 0.5 * sev) * np.sign(dev) * np.maximum(np.abs(dev) - 2.5, 0.0)
    g = np.clip(ndimage.gaussian_filter1d(g, 1.0, mode="nearest"), -6.0, 4.0)
    gains = 10 ** (np.concatenate([[g[0] * 0.5], g, [g[-1]]]) / 20)
    ok = freqs <= sr / 2
    h = sg.firwin2(2047, freqs[ok], gains[ok], fs=sr)
    return _each(x, lambda c: sg.oaconvolve(c, h, mode="same")), {int(b): round(float(v), 1) for b, v in zip(BANDS, g) if abs(v) >= 0.3}

def _sibilance(x, sr, target=-7.5):
    n = 2048
    m = _mono(x)

    def stats(S):
        f = np.fft.rfftfreq(n, 1 / sr)
        P = np.abs(S) ** 2
        s = P[(f >= 5000) & (f < 9000)].sum(0) + 1e-12
        r = P[(f >= 1000) & (f < 4000)].sum(0) + 1e-12
        return f, s, r
    f, t, S = _stft(m, sr, n)
    f, s, r = stats(S)
    act = (s + r) > np.percentile(s + r, 70) * 0.05
    S_db = 10 * np.log10(s / r)

    def idx(Sref):
        R = np.clip(0.9 * (S_db - Sref), 0, 10.0)
        return 10 * np.log10((s[act] * 10 ** (-R[act] / 10)).sum() / r[act].sum()), R
    lo, hi = np.percentile(S_db[act], 5), np.percentile(S_db[act], 99)
    if idx(hi)[0] <= target:
        for _ in range(14):
            mid = (lo + hi) / 2
            if idx(mid)[0] > target: hi = mid
            else: lo = mid
        Sref = hi
    else:
        Sref = hi
    cur, R = idx(Sref)
    R = ndimage.maximum_filter1d(R, 3)
    R = ndimage.uniform_filter1d(R, 3)
    fb = np.fft.rfftfreq(n, 1 / sr)
    shape = np.clip((fb - 4000) / 1000, 0, 1) * np.clip((13000 - fb) / 2000, 0, 1)

    def one(c):
        _, _, Sc = _stft(c, sr, n)
        G = 10 ** (-(shape[:, None] * R[None, : Sc.shape[1]]) / 20)
        return _istft(Sc * G, sr, len(c), n)
    return _each(x, one), {"mean_cut_db": round(float(R[act].mean()), 2), "max_cut_db": round(float(R.max()), 2),
                           "predicted_sib_db": round(float(cur), 1)}

def _air(x, sr, hf_now):
    m = _mono(x)
    nyq = sr / 2 * 0.98
    band = sg.sosfilt(sg.butter(4, [3000, 6500], btype="band", fs=sr, output="sos"), m)
    rms = np.sqrt((band ** 2).mean()) + 1e-12
    exc = np.abs(band) / rms - np.mean(np.abs(band) / rms)
    exc = sg.sosfilt(sg.butter(4, [9500, min(15500, nyq)], btype="band", fs=sr, output="sos"), exc)
    env = np.sqrt(ndimage.uniform_filter1d(band ** 2, int(0.01 * sr)))
    gate = np.clip(env / (np.percentile(env, 90) * 0.5 + 1e-12), 0, 1) ** 2
    gate = ndimage.uniform_filter1d(gate, int(0.01 * sr))
    f, P = sg.welch(m, sr, nperseg=8192)
    p_ref = P[(f >= 1000) & (f < 4000)].sum()
    p_hf = P[(f >= 10000) & (f < min(16000, nyq))].sum() + 1e-20
    want = p_ref * 10 ** ((HF_BOTTOM + 1.5) / 10) - p_hf
    fe, Pe = sg.welch(exc * gate, sr, nperseg=8192)
    p_exc = Pe[(fe >= 10000) & (fe < min(16000, nyq))].sum() + 1e-20
    scale = float(np.clip(np.sqrt(max(want, 0) / p_exc), 0.0, 3.0))
    add = exc * gate * scale
    return _each(x, lambda c: c + add[: len(c)]), {"added_hf_db": round(float(10 * np.log10((p_hf + max(want, 0)) / p_hf)), 1)}

def rescue(voc, sr, stage="all"):
    x = np.asarray(voc)
    if x.size == 0 or (x.ndim == 1 and len(x) < sr * 2) or (x.ndim == 2 and x.shape[1] < sr * 2):
        return voc, {"action": "bypass", "reason": "too short"}
    info, dev = analyze(x, sr)
    rep = {"action": "bypass", "analysis": info, "applied": {}}
    if not info["bad"]:
        rep["reason"] = "recording is within the commercial range"
        return voc, rep
    sev = info["severity"]
    y = x.astype(np.float64)
    m0 = _mono(y)
    rms0 = np.sqrt((m0 ** 2).mean()) + 1e-12
    if stage in ("pre", "all"):
        if sev["room"] >= STAGE_AT and info["rt60_s"]:
            y = _dereverb(y, sr, info["rt60_s"], sev["room"])
            rep["applied"]["dereverb"] = {"rt60_s": info["rt60_s"], "strength": round(sev["room"], 2)}
    if stage in ("post", "all"):
        if sev["tone"] >= STAGE_AT:
            y, moves = _tone(y, sr, dev, sev["tone"])
            rep["applied"]["tone"] = moves
        sib_now, hf_now = _indices(_mono(y), sr)
        if sib_now > SIB_TOP:
            y, d = _sibilance(y, sr)
            rep["applied"]["sibilance"] = d
        sib_now, hf_now = _indices(_mono(y), sr)
        if hf_now < HF_BOTTOM - 1.0 and sev["bandwidth"] >= STAGE_AT:
            y, d = _air(y, sr, hf_now)
            rep["applied"]["air"] = d
    if rep["applied"]:
        rep["action"] = "rescued"
        g = float(np.clip(rms0 / (np.sqrt((_mono(y) ** 2).mean()) + 1e-12), 0.7, 1.4))
        y = y * g
        pk = np.abs(y).max()
        if pk > 0.999:
            y = y * (0.999 / pk)
        rep["level_match_db"] = round(20 * np.log10(g), 2)
        after, _ = analyze(y, sr)
        rep["after"] = {"sib_db": after["sib_db"], "hf_db": after["hf_db"], "tone_dist_db": after["tone_dist_db"],
                        "rt60_s": after["rt60_s"]}
        return y.astype(x.dtype if np.issubdtype(x.dtype, np.floating) else np.float32), rep
    rep["reason"] = "nothing to apply for this stage"
    return voc, rep
