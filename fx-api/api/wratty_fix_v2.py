"""
wratty_fix_v2.py  -  drop-in adaptive fixes for the wratty-mix engine
numpy + scipy only.  Every function measures its OWN input in its OWN units,
so there is no scale mismatch with the engine's internal metrics.
"""
import numpy as np
from scipy import signal

EPS = 1e-12

BANDS = [("sub", 20, 60), ("b60", 60, 120), ("lm", 120, 250), ("m250", 250, 500),
         ("m500", 500, 1000), ("m1k", 1000, 2000), ("p2k", 2000, 4000),
         ("p4k", 4000, 6000), ("t6k", 6000, 9000), ("a9k", 9000, 12000)]
MASTER_WIN = {"sub": (-9.1, -2.5), "b60": (-8.6, -4.4), "lm": (-10.2, -5.6),
              "m250": (-11.1, -7.4), "m500": (-12.5, -8.7), "m1k": (-16.9, -11.5),
              "p2k": (-22.1, -15.6), "p4k": (-24.5, -22.0), "t6k": (-25.6, -21.7),
              "a9k": (-30.7, -24.0)}
CAPS = {"m250": (-1.5, 1.5), "m500": (-1.5, 1.5), "m1k": (-1.5, 1.5),
        "p2k": (-2.0, 2.0), "p4k": (-2.0, 3.0), "t6k": (-2.0, 3.0), "a9k": (-2.0, 3.0)}
MARGIN_DB = 0.5
DEADBAND_DB = 0.25
SIB_TOLERANCE_DB = 1.5

def _mono(x):
    x = np.asarray(x, np.float32)
    if x.ndim == 1:
        return x
    if x.shape[0] <= 2 and x.shape[1] > 2:
        return x.mean(axis=0)  # (channels, samples)
    return x.mean(axis=1)      # (samples, channels)

def rel_profile(x, sr):
    fr, p = signal.welch(_mono(x), sr, nperseg=8192)
    tot = p.sum() + EPS
    out = []
    for _, lo, hi in BANDS:
        sel = (fr >= lo) & (fr < min(hi, sr / 2))
        out.append(10 * np.log10(p[sel].sum() / tot + EPS))
    return np.array(out)

def _predict(prof, g):
    lin = 10 ** (prof / 10)
    gl = 10 ** (g / 10)
    total_new = (lin * gl).sum() + max(0.0, 1.0 - lin.sum())
    return prof + g - 10 * np.log10(total_new)

def plan_tone(prof):
    g = np.zeros(len(BANDS))
    for _ in range(6):
        pred = _predict(prof, g)
        for i, (n, _, _) in enumerate(BANDS):
            if n not in CAPS:
                continue
            wlo, whi = MASTER_WIN[n]
            if pred[i] < wlo:
                need = (wlo + MARGIN_DB) - pred[i]
            elif pred[i] > whi:
                need = (whi - MARGIN_DB) - pred[i]
            else:
                need = 0.0
            cmin, cmax = CAPS[n]
            g[i] = np.clip(g[i] + 0.7 * need, cmin, cmax)
    g[np.abs(g) < DEADBAND_DB] = 0.0
    return g

def _fir(g_db, sr, taps=4097):
    names = [n for n, _, _ in BANDS]
    centers = [np.sqrt(lo * hi) for _, lo, hi in BANDS]
    idx = [i for i, n in enumerate(names) if n in CAPS]
    fx = np.array([100.0, 180.0] + [centers[i] for i in idx] + [sr / 2 * 0.999])
    gy = np.array([0.0, 0.0] + [g_db[i] for i in idx] + [g_db[idx[-1]]])
    f = np.geomspace(100, sr / 2 * 0.999, 400)
    gd = np.interp(np.log(f), np.log(fx), gy)
    f = np.concatenate(([0.0], f, [sr / 2]))
    amp = 10 ** (np.concatenate(([0.0], gd, [gd[-1]])) / 20)
    return signal.firwin2(taps, f / (sr / 2), amp)

def _apply_fir(x, h):
    x = np.asarray(x, np.float32)
    if x.ndim == 1:
        return signal.fftconvolve(x, h, mode="same").astype(np.float32)
    if x.shape[0] <= 2 and x.shape[1] > 2:
        # (channels, samples)
        return np.stack([signal.fftconvolve(x[c, :], h, mode="same")
                         for c in range(x.shape[0])], axis=0).astype(np.float32)
    # (samples, channels)
    return np.stack([signal.fftconvolve(x[:, c], h, mode="same")
                     for c in range(x.shape[1])], axis=1).astype(np.float32)

def sib_index(x, sr):
    m = _mono(x)
    a = signal.sosfilt(signal.butter(4, [5000, 9000], "band", fs=sr, output="sos"), m)
    b = signal.sosfilt(signal.butter(4, [1000, 4000], "band", fs=sr, output="sos"), m)
    w = int(0.02 * sr)
    n = len(m) // w
    ra = np.sqrt((a[:n * w].reshape(n, w) ** 2).mean(1))
    rb = np.sqrt((b[:n * w].reshape(n, w) ** 2).mean(1))
    r = 20 * np.log10((ra + 1e-9) / (rb + 1e-9))
    act = rb > np.percentile(rb, 50)
    return float(np.percentile(r[act], 95))

def master_tone_correct(x, sr):
    names = [n for n, _, _ in BANDS]
    prof = rel_profile(x, sr)
    g = plan_tone(prof)
    rep = {"before_rel_db": dict(zip(names, np.round(prof, 1))),
           "gain_db": dict(zip(names, np.round(g, 2))),
           "applied": False, "sib_guard": False, "at_cap": []}
    for i, n in enumerate(names):
        if n in CAPS and (abs(g[i] - CAPS[n][1]) < 1e-6 or abs(g[i] - CAPS[n][0]) < 1e-6):
            rep["at_cap"].append(n)
    if np.max(np.abs(g)) < DEADBAND_DB:
        return np.asarray(x, np.float32), rep
    y = _apply_fir(x, _fir(g, sr))
    s0, s1 = sib_index(x, sr), sib_index(y, sr)
    rep["sib_before"], rep["sib_after"] = round(s0, 1), round(s1, 1)
    if s1 - s0 > SIB_TOLERANCE_DB:
        g2 = g.copy()
        for i, n in enumerate(names):
            if n in ("p4k", "t6k", "a9k") and g2[i] > 0:
                g2[i] *= 0.5
        y = _apply_fir(x, _fir(g2, sr))
        rep["sib_guard"] = True
        rep["gain_db"] = dict(zip(names, np.round(g2, 2)))
        rep["sib_after"] = round(sib_index(y, sr), 1)
    rep["applied"] = True
    rep["after_rel_db"] = dict(zip(names, np.round(rel_profile(y, sr), 1)))
    return y, rep

CARVE = [("lowmid", 150, 350, -8.0, 3.0, 1.0),
         ("mid",    500, 2000, 0.0, 1.5, 1.0),
         ("pres",  2000, 4500, -3.0, 3.0, 1.5),
         ("top",   4500, 8000, -3.0, 2.0, 0.5)]

def _frame_db(x, w):
    n = len(x) // w
    return 10 * np.log10((x[:n * w].reshape(n, w) ** 2).mean(1) + 1e-12)

def _smooth_env(db, hop_s, atk_ms=10.0, rel_ms=150.0):
    ka = np.exp(-hop_s * 1000.0 / atk_ms)
    kr = np.exp(-hop_s * 1000.0 / rel_ms)
    out = np.empty_like(db)
    y = db[0]
    for i, v in enumerate(db):
        k = ka if v > y else kr
        y = k * y + (1 - k) * v
        out[i] = y
    return out

def carve_beat(beat, vocal, sr, fallback=False):
    b = np.asarray(beat, np.float32)
    bm, v = _mono(b), _mono(vocal)
    n = min(len(bm), len(v))
    w = int(0.05 * sr)
    gate = signal.sosfiltfilt(signal.butter(4, [300, 3000], "band", fs=sr, output="sos"), v[:n])
    gdb = _frame_db(gate, w)
    act = gdb > (np.percentile(gdb, 95) - 30)
    out = b.copy()
    rep = {}
    hop = int(0.005 * sr)
    for name, lo, hi, floor, cap, fb in CARVE:
        sos = signal.butter(4, [lo, hi], "band", fs=sr, output="sos")
        vb = signal.sosfiltfilt(sos, v[:n])
        bb = signal.sosfiltfilt(sos, bm[:n])
        vp = (vb[:len(act) * w].reshape(len(act), w) ** 2).mean(1)
        bp = (bb[:len(act) * w].reshape(len(act), w) ** 2).mean(1)
        C = 10 * np.log10(vp[act].mean() + EPS) - 10 * np.log10(bp[act].mean() + EPS)
        depth = min(cap, 0.6 * (floor - C)) if C < floor else 0.0
        if fallback:
            depth = max(depth, fb)
        rep[name] = {"C_db": round(float(C), 1), "floor_db": floor,
                     "depth_db": round(float(depth), 2), "at_cap": bool(depth >= cap - 1e-6)}
        if depth < 0.1:
            continue
        env = _smooth_env(_frame_db(vb, hop), hop / sr)
        thr = np.percentile(env, 95) - 30.0
        a = np.clip((env - thr) / 12.0, 0.0, 1.0)
        centers = (np.arange(len(a)) + 0.5) * hop
        gain_db = np.interp(np.arange(len(b)), centers, -depth * a)
        g_lin = (10 ** (gain_db / 20) - 1.0).astype(np.float32)
        if out.ndim == 1:
            out += signal.sosfiltfilt(sos, b).astype(np.float32) * g_lin
        else:
            for c in range(out.shape[1]):
                out[:, c] += signal.sosfiltfilt(sos, b[:, c]).astype(np.float32) * g_lin
    return out, rep

def qa(x, sr):
    x = np.asarray(x, np.float32)
    names = [n for n, _, _ in BANDS]
    prof = rel_profile(x, sr)
    fr, p = signal.welch(_mono(x), sr, nperseg=8192)
    bp = lambda lo, hi: 10 * np.log10(p[(fr >= lo) & (fr < hi)].sum() + EPS)
    top_minus_pres = bp(5500, 10000) - bp(2000, 5500)
    res = {"rel_db": dict(zip(names, np.round(prof, 1))),
           "top_minus_presence_db": round(float(top_minus_pres), 1),
           "sib_index": round(sib_index(x, sr), 1)}
    if x.ndim == 2:
        L, R = x[:, 0], x[:, 1]
        M, S = (L + R) / 2, (L - R) / 2
        res["side_minus_mid_db"] = round(float(10 * np.log10((S ** 2).mean() / ((M ** 2).mean() + EPS) + EPS)), 1)
        res["mono_loss_db"] = round(float(20 * np.log10(np.sqrt((M ** 2).mean()) / np.sqrt((x ** 2).mean() + EPS) + EPS)), 2)
    m = _mono(x)
    res["crest_db"] = round(float(20 * np.log10(np.abs(x).max() / (np.sqrt((m ** 2).mean()) + EPS))), 1)
    res["clipped_samples"] = int((np.abs(x) >= 0.999).sum())
    fails = []
    for i, n in enumerate(names):
        if n in CAPS:
            lo, hi = MASTER_WIN[n]
            if prof[i] < lo - 1.0 or prof[i] > hi + 1.0:
                fails.append(f"{n} {prof[i]:.1f} outside {lo}..{hi} (+/-1)")
    if res.get("mono_loss_db", 0) < -0.5:
        fails.append("mono loss > 0.5 dB")
    if res["clipped_samples"] > 0:
        fails.append("clipped samples")
    res["fails"], res["pass"] = fails, not fails
    return res

def needs_declip(x, thr=0.999, min_run=3, min_runs=20):
    a = np.abs(np.asarray(x, np.float32))
    if a.ndim == 2:
        a = a.max(axis=1)
    hit = np.concatenate(([0], (a >= thr).astype(np.int8), [0]))
    d = np.diff(hit)
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    return int(((ends - starts) >= min_run).sum()) > min_runs

def tail_warning(stem, keep_samples, floor_db=-50.0):
    tail = _mono(stem)[keep_samples:]
    if len(tail) == 0:
        return False, -120.0
    lvl = 20 * np.log10(np.sqrt((tail.astype(np.float64) ** 2).mean()) + 1e-9)
    return bool(lvl > floor_db), float(lvl)
