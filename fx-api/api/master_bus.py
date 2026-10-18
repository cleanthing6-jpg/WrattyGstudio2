"""
master_bus.py  --  adaptive mastering bus for a multi-user beat+vocal automix.
Pure numpy/scipy. Stateless, deterministic, safe to run in parallel per user.

SIGNAL FLOW
  1 Input        sanitise (NaN/DC), measure
  2 Tonal EQ     linear-phase match toward the median of 5 commercial Afrobeats masters
  3 Multiband    3-band LR4 compressor (low / mid / high), thresholds from each band's own level
  4 Glue         stereo-linked bus compressor, side-chain high-passed, dual release
  5 Saturation   2x-oversampled soft saturation, parallel
  6 Stereo       bass-mono below 120 Hz, adaptive width
  7 Loudness     soft clipper -> look-ahead TRUE-PEAK limiter, iterated to the LUFS target
  8 QC           loudness, true peak, correlation, DC, clipping, balance warnings
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

CENTERS = np.array([31.5, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0, 200.0, 250.0, 315.0, 400.0,
                    500.0, 630.0, 800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0, 4000.0,
                    5000.0, 6300.0, 8000.0, 10000.0, 12500.0, 16000.0])
REF_MEDIAN = np.array([-26.1, -15.5, -8.6, -8.8, -11.1, -11.7, -11.6, -13.9, -14.2, -14.5, -15.2,
                       -12.9, -14.3, -14.9, -16.6, -19.3, -18.5, -18.4, -21.8, -24.7, -24.5, -24.9,
                       -26.2, -25.7, -26.5, -26.6, -30.4, -36.0])
REF_SIDE_DB = -8.4

PRESETS = {
    "streaming": dict(lufs=-11.5, ceil=-1.0, eq=0.4, mb=0.8, glue=1.0, sat=0.15, adapt_width=True, max_gr=4.5, clip=0.8),
    "afrobeats": dict(lufs=-10.0, ceil=-1.0, eq=0.5, mb=1.0, glue=1.3, sat=0.25, adapt_width=True, max_gr=6.0, clip=1.5),
    "club":      dict(lufs=-8.5,  ceil=-1.0, eq=0.5, mb=1.0, glue=1.6, sat=0.35, adapt_width=True, max_gr=8.0, clip=2.2),
}

HOP_S = 0.001


def _to_cn(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return np.stack([x, x]), "mono"
    if x.shape[0] in (1, 2) and x.shape[1] > 2:
        x = x if x.shape[0] == 2 else np.vstack([x, x])
        return x, "cn"
    if x.shape[1] == 1:
        x = np.hstack([x, x])
    return x.T.copy(), "nc"


def _from_cn(y, kind):
    if kind == "mono": return y.mean(axis=0).astype(np.float32)
    if kind == "nc":   return y.T.astype(np.float32)
    return y.astype(np.float32)


def _k_weight_sos(sr):
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = np.tan(np.pi * f0 / sr); Vh = 10 ** (G / 20); Vb = Vh ** 0.4996667741545416; a0 = 1 + K / Q + K * K
    s1 = sg.tf2sos([(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0],
                   [1, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0])
    f0, Q = 38.13547087602444, 0.5003270373238773
    K = np.tan(np.pi * f0 / sr); d = 1 + K / Q + K * K
    s2 = sg.tf2sos([1, -2, 1], [1, 2 * (K * K - 1) / d, (1 - K / Q + K * K) / d])
    return np.vstack([s1, s2])


def lufs(x, sr):
    y = sg.sosfilt(_k_weight_sos(sr), x, axis=-1)
    n, hop = int(0.4 * sr), int(0.1 * sr)
    k = (y.shape[1] - n) // hop + 1
    if k < 1:
        return -70.0
    z = np.array([(y[:, i * hop:i * hop + n] ** 2).mean(axis=1).sum() for i in range(k)])
    l = -0.691 + 10 * np.log10(z + 1e-12)
    g = z[l > -70]
    if len(g) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(g.mean()) - 10
    g2 = z[l > rel]
    return float(-0.691 + 10 * np.log10(g2.mean() + 1e-12))


def _hop_true_peaks(x, hop, os=4, chunk_s=8.0, sr=44100):
    C, N = x.shape
    k = N // hop
    out = np.zeros(k)
    step = int(chunk_s * sr) // hop * hop
    ctx = 256
    for s in range(0, k * hop, step):
        e = min(s + step, k * hop)
        a, b = max(0, s - ctx), min(N, e + ctx)
        up = sg.resample_poly(x[:, a:b], os, 1, axis=-1)
        up = np.abs(up)[:, (s - a) * os:(e - a) * os]
        nh = (e - s) // hop
        out[s // hop:s // hop + nh] = up.max(axis=0).reshape(nh, hop * os).max(axis=1)
    return out


def true_peak_db(x, sr):
    p = _hop_true_peaks(x, 256, sr=sr)
    return float(20 * np.log10(p.max() + 1e-12))


def _ltas(x, sr):
    m = x.mean(axis=0)
    f, P = sg.welch(m, sr, nperseg=16384)
    edges = np.concatenate([[CENTERS[0] / 2 ** (1 / 6)], CENTERS * 2 ** (1 / 6)])
    B = np.array([P[(f >= edges[i]) & (f < edges[i + 1])].sum() for i in range(len(CENTERS))])
    return 10 * np.log10(B / B.sum() + 1e-20)


def _side_db(x, sr):
    M, S = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2
    f, Pm = sg.welch(M, sr, nperseg=8192); _, Ps = sg.welch(S, sr, nperseg=8192)
    b = (f >= 200) & (f < 8000)
    return float(10 * np.log10((Ps[b].sum() + 1e-20) / (Pm[b].sum() + 1e-20)))


def _ballistics(gr, hop_s, att_s, rel_s):
    a_att, a_rel = 1 - np.exp(-hop_s / att_s), 1 - np.exp(-hop_s / rel_s)
    out = np.empty_like(gr); y = 0.0
    for i, v in enumerate(gr):
        y += (a_att if v > y else a_rel) * (v - y)
        out[i] = y
    return out


def _static_gr(level, thr, ratio, knee):
    over = level - thr
    gr = np.zeros_like(over)
    hi = over > knee / 2
    gr[hi] = over[hi] * (1 - 1 / ratio)
    mid = (~hi) & (over > -knee / 2)
    gr[mid] = (1 - 1 / ratio) * (over[mid] + knee / 2) ** 2 / (2 * knee)
    return gr


def _level_db(sig, hop, win_hops):
    C, N = sig.shape
    k = N // hop
    p = (sig[:, :k * hop].reshape(C, k, hop) ** 2).mean(axis=2).max(axis=0)
    p = ndimage.uniform_filter1d(p, size=win_hops, mode="nearest")
    return 10 * np.log10(p + 1e-12)


def _compress(sig, det, sr, maxgr, ratio, knee, att, rel, rms_ms, pct, dual_release=False):
    hop = max(1, int(HOP_S * sr)); hop_s = hop / sr
    lev = _level_db(det, hop, max(1, int(rms_ms / 1000 / hop_s)))
    live = lev > lev.max() - 55
    if live.sum() < 20 or maxgr <= 0:
        return None, np.zeros(len(lev))
    thr = np.percentile(lev[live], pct) - maxgr * ratio / (ratio - 1)
    gr = np.minimum(_static_gr(lev, thr, ratio, knee), maxgr * 2.2)
    if dual_release:
        g = 0.6 * _ballistics(gr, hop_s, att, rel * 3.0) + 0.4 * _ballistics(gr, hop_s, att, rel * 0.5)
    else:
        g = _ballistics(gr, hop_s, att, rel)
    N = sig.shape[1]
    gain = np.interp(np.arange(N), (np.arange(len(g)) + 0.5) * hop, 10 ** (-g / 20))
    return gain, g


def stage_eq(x, sr, strength, rep):
    cur = _ltas(x, sr)
    gap = REF_MEDIAN - cur
    mid_band = (CENTERS >= 100) & (CENTERS <= 8000)
    gap = gap - np.median(gap[mid_band])
    gap = ndimage.gaussian_filter1d(gap, 1.2, mode="nearest")
    g = np.sign(gap) * np.maximum(np.abs(gap) - 1.0, 0.0)
    g = g * strength
    vocal = (CENTERS >= 700) & (CENTERS <= 3200)
    g[vocal] = np.minimum(g[vocal], 0.0)
    g[CENTERS < 45] = np.minimum(g[CENTERS < 45], 0.0)
    g[CENTERS > 10000] = np.clip(g[CENTERS > 10000], -2.0, 1.5)
    g = np.clip(g, -3.0, 3.0)
    rep["eq_db"] = {str(int(c)): round(float(v), 2) for c, v in zip(CENTERS, g) if abs(v) >= 0.2}
    if np.abs(g).max() < 0.2:
        return x
    fg = np.geomspace(20.0, sr / 2 * 0.999, 400)
    gd = np.interp(np.log(fg), np.log(CENTERS), g)
    freqs = np.concatenate([[0.0], fg, [sr / 2]]); gains = 10 ** (np.concatenate([[gd[0]], gd, [gd[-1]]]) / 20)
    h = sg.firwin2(4095, freqs, gains, fs=sr)
    return np.stack([sg.oaconvolve(c, h, mode="same") for c in x])


def _lr4(sr, fc, kind):
    return sg.butter(2, fc, btype=kind, fs=sr, output="sos")


def _lp4(x, sr, fc): return sg.sosfilt(_lr4(sr, fc, "low"), sg.sosfilt(_lr4(sr, fc, "low"), x, axis=-1), axis=-1)
def _hp4(x, sr, fc): return sg.sosfilt(_lr4(sr, fc, "high"), sg.sosfilt(_lr4(sr, fc, "high"), x, axis=-1), axis=-1)


def split3(x, sr, f1=140.0, f2=3500.0):
    low, rest = _lp4(x, sr, f1), _hp4(x, sr, f1)
    mid, high = _lp4(rest, sr, f2), _hp4(rest, sr, f2)
    low = _lp4(low, sr, f2) + _hp4(low, sr, f2)
    return low, mid, high


def stage_multiband(x, sr, amount, rep):
    if amount <= 0:
        return x
    bands = split3(x, sr)
    cfg = [("low",  2.5, 2.0, 6.0, 0.010, 0.150, 30.0, 95),
           ("mid",  2.0, 1.8, 6.0, 0.020, 0.120, 15.0, 95),
           ("high", 2.5, 2.5, 6.0, 0.005, 0.080, 8.0, 97)]
    out, st = np.zeros_like(x), {}
    for (name, mg, r, kn, a, rl, rms, pc), b in zip(cfg, bands):
        gain, g = _compress(b, b, sr, mg * amount, r, kn, a, rl, rms, pc)
        out += b if gain is None else b * gain
        st[name] = {"avg_gr_db": round(float(g.mean()), 2), "max_gr_db": round(float(g.max()), 2)}
    rep["multiband"] = st
    return out


def stage_glue(x, sr, amount, rep):
    if amount <= 0:
        return x
    det = sg.sosfilt(sg.butter(2, 200.0, btype="high", fs=sr, output="sos"), x, axis=-1)
    gain, g = _compress(x, det, sr, 1.0 * amount, 2.0, 6.0, 0.030, 0.150, 20.0, 90, dual_release=True)
    rep["glue"] = {"avg_gr_db": round(float(g.mean()), 2), "max_gr_db": round(float(g.max()), 2)}
    return x if gain is None else x * gain


def stage_saturate(x, sr, amount, rep):
    if amount <= 0:
        return x
    d = 1.0 + 2.0 * amount
    up = sg.resample_poly(x, 2, 1, axis=-1)
    sat = np.tanh(d * up) / d
    y = sg.resample_poly((1 - amount) * up + amount * sat, 1, 2, axis=-1)[:, :x.shape[1]]
    rep["saturation"] = {"drive": round(d, 2), "blend": round(amount, 2)}
    return y


def stage_stereo(x, sr, adapt, rep, bass_mono_hz=120.0):
    M, S = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2
    S = sg.sosfiltfilt(sg.butter(4, bass_mono_hz, btype="high", fs=sr, output="sos"), S)
    cur = _side_db(np.stack([M + S, M - S]), sr)
    width = 1.0
    if adapt:
        width = float(np.clip(10 ** ((REF_SIDE_DB - cur) / 20 * 0.5), 0.9, 1.25))
    rep["stereo"] = {"bass_mono_hz": bass_mono_hz, "side_db_before_width": round(cur, 1), "width": round(width, 2)}
    S = S * width
    return np.stack([M + S, M - S])


def _soft_clip(x, ceil_lin, clip_db):
    if clip_db <= 0:
        return x
    room = ceil_lin * (10 ** (clip_db / 20) - 1.0)
    up = sg.resample_poly(x, 2, 1, axis=-1)
    a = np.abs(up)
    a = np.where(a > ceil_lin, ceil_lin + room * np.tanh((a - ceil_lin) / room), a)
    return sg.resample_poly(np.sign(up) * a, 1, 2, axis=-1)[:, :x.shape[1]]


def _limit(x, sr, ceil_lin, rel_fast=0.050, rel_slow=0.300, lookahead_s=0.006):
    hop = 32
    pk = _hop_true_peaks(x, hop, sr=sr)
    need = np.minimum(1.0, ceil_lin / np.maximum(pk, 1e-9))
    W = max(1, int(lookahead_s * sr / hop))
    m = ndimage.minimum_filter1d(need, size=2 * W + 1, mode="nearest")
    gs = ndimage.uniform_filter1d(m, size=2 * W + 1, mode="nearest")
    hs = hop / sr

    def rel(g, tau):
        a = 1 - np.exp(-hs / tau); out = np.empty_like(g); r = 1.0
        for i, v in enumerate(g):
            r = r + (1.0 - r) * a
            if v < r: r = v
            out[i] = r
        return out
    g = 0.5 * (rel(gs, rel_fast) + rel(gs, rel_slow))
    N = x.shape[1]
    gain = np.interp(np.arange(N), (np.arange(len(g)) + 0.5) * hop, g)
    return x * gain, -20 * np.log10(np.maximum(g, 1e-6))


def stage_loudness(x, sr, target, ceil_db, clip_db, max_gr, rep):
    ceil_lin = 10 ** ((ceil_db - 0.15) / 20)
    L0 = lufs(x, sr)
    G = target - L0
    best = None
    for it in range(4):
        y = _soft_clip(x * 10 ** (G / 20), ceil_lin, clip_db)
        y, gr = _limit(y, sr, ceil_lin)
        L = lufs(y, sr)
        live = gr[gr > 0.05]
        p95 = float(np.percentile(gr, 95))
        best = (y, L, gr, p95, G)
        if abs(L - target) < 0.15:
            break
        G += (target - L)
    y, L, gr, p95, G = best
    short = 0.0
    if p95 > max_gr:
        G -= (p95 - max_gr) * 0.9
        y = _soft_clip(x * 10 ** (G / 20), ceil_lin, clip_db)
        y, gr = _limit(y, sr, ceil_lin)
        L = lufs(y, sr); p95 = float(np.percentile(gr, 95)); short = target - L
    tp = true_peak_db(y, sr)
    if tp > ceil_db:
        y = y * 10 ** ((ceil_db - tp - 0.01) / 20); L = lufs(y, sr)
    rep["loudness"] = {"input_lufs": round(L0, 2), "gain_db": round(G, 2), "limiter_avg_gr_db": round(float(gr.mean()), 2),
                       "limiter_p95_gr_db": round(p95, 2), "limiter_max_gr_db": round(float(gr.max()), 2),
                       "shortfall_db": round(float(max(short, 0)), 2)}
    return y


def qc(x, sr, target, ceil_db, in_rep):
    w = []
    L, tp = lufs(x, sr), true_peak_db(x, sr)
    if tp > ceil_db + 0.1: w.append(f"true peak {tp:.2f} dBTP above ceiling {ceil_db}")
    if abs(L - target) > 0.6: w.append(f"loudness {L:.1f} LUFS is {abs(L - target):.1f} dB from target")
    c = float(np.corrcoef(x[0], x[1])[0, 1]) if x[0].std() > 0 else 1.0
    if c < 0.3: w.append(f"low L/R correlation {c:.2f}")
    if abs(x.mean()) > 0.005: w.append("DC offset present")
    clipped = int((np.abs(x) >= 0.9999).sum())
    if clipped: w.append(f"{clipped} samples at digital full scale")
    if in_rep.get("input_balance_warning"): w.append(in_rep["input_balance_warning"])
    return {"lufs": round(L, 2), "true_peak_dbtp": round(tp, 2), "plr_db": round(tp - L, 2),
            "correlation": round(c, 3),
            "crest_db": round(float(20 * np.log10(np.abs(x).max() / (np.sqrt((x ** 2).mean()) + 1e-12))), 2),
            "warnings": w}


def master(x, sr, preset="afrobeats", **over):
    p = dict(PRESETS.get(preset, PRESETS["afrobeats"])); p.update(over)
    xc, kind = _to_cn(x)
    rep = {"preset": preset, "params": p}
    if not np.isfinite(xc).all():
        xc = np.nan_to_num(xc)
    xc = xc - xc.mean(axis=1, keepdims=True)
    if np.abs(xc).max() < 1e-6 or xc.shape[1] < sr:
        rep["warning"] = "input silent or shorter than 1 s: not processed"
        return _from_cn(xc, kind), rep
    rep["input"] = {"lufs": round(lufs(xc, sr), 2), "true_peak_dbtp": round(true_peak_db(xc, sr), 2)}
    cur = _ltas(xc, sr)
    vb = (CENTERS >= 800) & (CENTERS <= 2500)
    vgap = float(np.median((cur - REF_MEDIAN)[vb]) - np.median((cur - REF_MEDIAN)[(CENTERS >= 100) & (CENTERS <= 8000)]))
    if vgap > 3.0:
        rep["input_balance_warning"] = (f"0.8-2.5 kHz is {vgap:.1f} dB hotter than commercial masters: "
                                        "vocal is probably too loud against the beat, fix in the mix not the master")
    y = stage_eq(xc, sr, p["eq"], rep)
    y = stage_multiband(y, sr, p["mb"], rep)
    y = stage_glue(y, sr, p["glue"], rep)
    y = stage_saturate(y, sr, p["sat"], rep)
    y = stage_stereo(y, sr, p["adapt_width"], rep)
    y = stage_loudness(y, sr, p["lufs"], p["ceil"], p["clip"], p["max_gr"], rep)
    rep["output"] = qc(y, sr, p["lufs"], p["ceil"], rep)
    return _from_cn(y, kind), rep
