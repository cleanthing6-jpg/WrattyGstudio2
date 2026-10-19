"""
master_bus.py  --  adaptive mastering bus for a multi-user beat+vocal automix.
Pure numpy/scipy. Stateless, deterministic, safe to run in parallel per user.
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

REFERENCES = {
    "afrobeats": dict(curve=REF_MEDIAN, side_db=REF_SIDE_DB),
}

def build_profile(refs):
    cur, side, lf, plr = [], [], [], []
    for a, r in refs:
        xc, _ = _to_cn(a)
        cur.append(_ltas(xc, r)); side.append(_side_db(xc, r))
        L = lufs(xc, r); lf.append(L); plr.append(true_peak_db(xc, r) - L)
    return {"n": len(refs), "curve": np.round(np.median(cur, axis=0), 1).tolist(), "side_db": round(float(np.median(side)), 1),
            "lufs_median": round(float(np.median(lf)), 1), "plr_range": [round(float(min(plr)), 1), round(float(max(plr)), 1)]}

def register_genre(name, profile, **preset):
    REFERENCES[name] = dict(curve=np.asarray(profile["curve"], dtype=float), side_db=float(profile["side_db"]))
    base = dict(PRESETS["afrobeats"]); base.update(ref=name)
    if "lufs_median" in profile: base["lufs"] = float(profile["lufs_median"])
    if "plr_range" in profile: base["plr_floor"] = float(profile["plr_range"][0])
    base.update(preset)
    PRESETS[name] = base

PRESETS = {
    "streaming": dict(ref="afrobeats", eq_floor=0.5, plr_floor=10.0, lufs=-11.5, ceil=-1.0, eq=0.4, mb=0.8, glue=1.0, sat=0.15, adapt_width=True, max_gr=4.5, clip=0.8, max_cut=None, top_trim=1.0),
    "afrobeats": dict(ref="afrobeats", eq_floor=1.0, plr_floor=9.2, lufs=-10.0, ceil=-1.0, eq=0.5, mb=1.0, glue=1.3, sat=0.25, adapt_width=True, max_gr=6.0, clip=1.5, max_cut=None, top_trim=1.0),
    "club":      dict(ref="afrobeats", eq_floor=1.0, plr_floor=7.5, lufs=-8.5,  ceil=-1.0, eq=0.5, mb=1.0, glue=1.6, sat=0.35, adapt_width=True, max_gr=8.0, clip=2.2, max_cut=None, top_trim=1.0),
    "other":     dict(ref=None, eq_floor=0.0, plr_floor=9.0, lufs=-10.0, ceil=-1.0, eq=0.0, mb=0.4, glue=0.5, sat=0.0, adapt_width=False, max_gr=6.0, clip=1.5, max_cut=None, top_trim=0.7),
}
_GENRE = {"hiphop": (-10.0, 9.2), "pop": (-10.0, 9.2), "rnb": (-10.0, 9.2),
          "amapiano": (-10.0, 9.2), "dancehall": (-10.0, 9.2), "gospel": (-10.0, 9.2)}
for _g, (_l, _p) in _GENRE.items():
    PRESETS[_g] = dict(PRESETS["other"], lufs=_l, plr_floor=_p)

_ALIASES = {"afro": "afrobeats", "afrobeat": "afrobeats", "afropop": "afrobeats", "rap": "hiphop", "trap": "hiphop", "drill": "hiphop",
            "rb": "rnb", "randb": "rnb", "piano": "amapiano"}

def _resolve_preset(preset):
    k = "".join(ch for ch in str(preset or "other").lower() if ch.isalnum() or ch == "&").replace("&", "")
    k = _ALIASES.get(k, k)
    return k if k in PRESETS else "other"

HOP_S = 0.001

def _to_cn(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1: return np.stack([x, x]), "mono"
    if x.shape[0] in (1, 2) and x.shape[1] > 2:
        x = x if x.shape[0] == 2 else np.vstack([x, x])
        return x, "cn"
    if x.shape[1] == 1: x = np.hstack([x, x])
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
    if k < 1: return -70.0
    z = np.array([(y[:, i * hop:i * hop + n] ** 2).mean(axis=1).sum() for i in range(k)])
    l = -0.691 + 10 * np.log10(z + 1e-12)
    g = z[l > -70]
    if len(g) == 0: return -70.0
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
    if live.sum() < 20 or maxgr <= 0: return None, np.zeros(len(lev))
    thr = np.percentile(lev[live], pct) - maxgr * ratio / (ratio - 1)
    gr = np.minimum(_static_gr(lev, thr, ratio, knee), maxgr * 2.2)
    if dual_release: g = 0.6 * _ballistics(gr, hop_s, att, rel * 3.0) + 0.4 * _ballistics(gr, hop_s, att, rel * 0.5)
    else: g = _ballistics(gr, hop_s, att, rel)
    N = sig.shape[1]
    gain = np.interp(np.arange(N), (np.arange(len(g)) + 0.5) * hop, 10 ** (-g / 20))
    return gain, g

def stage_eq(x, sr, strength, rep, curve=None):
    curve = REF_MEDIAN if curve is None else curve
    cur = _ltas(x, sr)
    gap = curve - cur
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
    if np.abs(g).max() < 0.2: return x
    fg = np.geomspace(20.0, sr / 2 * 0.999, 400)
    gd = np.interp(np.log(fg), np.log(CENTERS), g)
    freqs = np.concatenate([[0.0], fg, [sr / 2]]); gains = 10 ** (np.concatenate([[gd[0]], gd, [gd[-1]]]) / 20)
    h = sg.firwin2(4095, freqs, gains, fs=sr)
    return np.stack([sg.oaconvolve(c, h, mode="same") for c in x])

def _lr4(sr, fc, kind): return sg.butter(2, fc, btype=kind, fs=sr, output="sos")
def _lp4(x, sr, fc): return sg.sosfilt(_lr4(sr, fc, "low"), sg.sosfilt(_lr4(sr, fc, "low"), x, axis=-1), axis=-1)
def _hp4(x, sr, fc): return sg.sosfilt(_lr4(sr, fc, "high"), sg.sosfilt(_lr4(sr, fc, "high"), x, axis=-1), axis=-1)

def split3(x, sr, f1=140.0, f2=3500.0):
    low, rest = _lp4(x, sr, f1), _hp4(x, sr, f1)
    mid, high = _lp4(rest, sr, f2), _hp4(rest, sr, f2)
    low = _lp4(low, sr, f2) + _hp4(low, sr, f2)
    return low, mid, high

def stage_multiband(x, sr, amount, rep):
    if amount <= 0: return x
    bands = split3(x, sr)
    cfg = [("low",  2.5, 2.0, 6.0, 0.030, 0.150, 30.0, 95),
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
    if amount <= 0: return x
    det = sg.sosfilt(sg.butter(2, 120.0, btype="high", fs=sr, output="sos"), x, axis=-1)
    gain, g = _compress(x, det, sr, 1.5 * amount, 2.0, 6.0, 0.030, 0.150, 20.0, 90, dual_release=True)
    rep["glue"] = {"avg_gr_db": round(float(g.mean()), 2), "max_gr_db": round(float(g.max()), 2)}
    return x if gain is None else x * gain

def stage_saturate(x, sr, amount, rep):
    if amount <= 0: return x
    d = 1.0 + 2.0 * amount
    up = sg.resample_poly(x, 2, 1, axis=-1)
    sat = np.tanh(d * up) / d
    y = sg.resample_poly((1 - amount) * up + amount * sat, 1, 2, axis=-1)[:, :x.shape[1]]
    rep["saturation"] = {"drive": round(d, 2), "blend": round(amount, 2)}
    return y

def stage_top_trim(x, sr, amount, rep, curve=None, tol_db=0.5):
    if amount <= 0: return x
    hop = max(1, int(HOP_S * sr)); hs = hop / sr
    bands = [("2.5-5.5k", 2500.0, 5500.0, 3.1, 4.0), ("5.5-16k", 5500.0, min(16000.0, sr / 2 * 0.95), 1.9, 4.0)]
    gap, base = None, 0.0
    if curve is not None:
        gap = curve - _ltas(x, sr)
        gap = gap - np.median(gap[(CENTERS >= 100) & (CENTERS <= 8000)])
    comp = {"mid": (x[0] + x[1]) / 2, "side": (x[0] - x[1]) / 2}
    out = {k: v.copy() for k, v in comp.items()}
    st, changed, mid_peak = {}, False, {}
    for name, lo, hi, cap, spike in bands:
        cap *= amount
        if gap is not None:
            excess = -float(np.median(gap[(CENTERS >= lo) & (CENTERS <= hi)]))
            if excess <= tol_db:
                st[name] = {"skipped": f"not brighter than reference by more than {tol_db:.1f} dB ({excess:+.1f})"}
                continue
            base = min(cap, excess - tol_db)
            cap = min(cap, base + 1.0)
        sos = sg.butter(2, [lo, hi], btype="band", fs=sr, output="sos")
        for cname in ("mid", "side"):
            key = f"{cname} {name}"
            band = sg.sosfiltfilt(sos, comp[cname])
            lev = _level_db(band[None, :], hop, max(1, int(0.100 / hs)))
            if cname == "mid":
                mid_peak[name] = float(lev.max())
            elif lev.max() < mid_peak[name] - 40:
                st[key] = {"skipped": "no side energy"}
                continue
            live = lev > lev.max() - 50
            if live.sum() < 20:
                st[key] = {"skipped": "no signal"}
                continue
            thr = float(np.median(lev[live])) + spike
            gr = np.minimum(base + _static_gr(lev, thr, 2.0, 4.0), cap)
            if gr.max() < 0.1:
                st[key] = {"avg_gr_db": 0.0, "max_gr_db": 0.0, "active_pct": 0.0}
                continue
            g = _ballistics(gr, hs, 0.010, 0.150)
            gain = np.interp(np.arange(x.shape[1]), (np.arange(len(g)) + 0.5) * hop, 10 ** (-g / 20))
            out[cname] = out[cname] - band + band * gain
            changed = True
            st[key] = {"avg_gr_db": round(float(g.mean()), 2), "max_gr_db": round(float(g.max()), 2), "active_pct": round(float((g > 0.3).mean() * 100), 1)}
    rep["top_trim"] = st
    if not changed: return x
    return np.stack([out["mid"] + out["side"], out["mid"] - out["side"]])

def stage_stereo(x, sr, adapt, rep, bass_mono_hz=120.0, width_min=0.9, side_target=REF_SIDE_DB):
    M, S = (x[0] + x[1]) / 2, (x[0] - x[1]) / 2
    S = sg.sosfiltfilt(sg.butter(4, bass_mono_hz, btype="high", fs=sr, output="sos"), S)
    cur = _side_db(np.stack([M + S, M - S]), sr)
    width = 1.0
    if adapt:
        width = float(np.clip(10 ** ((side_target - cur) / 20 * 0.5), width_min, 1.25))
    rep["stereo"] = {"bass_mono_hz": bass_mono_hz, "side_db_before_width": round(cur, 1), "width": round(width, 2)}
    S = S * width
    return np.stack([M + S, M - S])

def _soft_clip(x, ceil_lin, clip_db):
    if clip_db <= 0: return x
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

def stage_loudness(x, sr, target, ceil_db, clip_db, max_gr, rep, max_cut=None, plr_min=None):
    ceil_lin = 10 ** ((ceil_db - 0.15) / 20)
    L0 = lufs(x, sr)
    Gmax = float("inf") if max_cut is None else float(max_cut) + ceil_db - true_peak_db(x, sr)
    G = min(target - L0, Gmax)
    best = None
    for it in range(5):
        y = _soft_clip(x * 10 ** (G / 20), ceil_lin, clip_db)
        y, gr = _limit(y, sr, ceil_lin)
        L = lufs(y, sr)
        p95 = float(np.percentile(gr, 95))
        best = (y, L, gr, p95, G)
        if (-0.15 < L - target <= 0.03) or (L < target and G >= Gmax - 1e-6): break
        G = min(G + (target - L), Gmax)
    y, L, gr, p95, G = best
    short = 0.0
    if p95 > max_gr:
        G -= (p95 - max_gr) * 0.9
        y = _soft_clip(x * 10 ** (G / 20), ceil_lin, clip_db)
        y, gr = _limit(y, sr, ceil_lin)
        L = lufs(y, sr); p95 = float(np.percentile(gr, 95)); short = target - L
    plr_fix = 0.0
    if plr_min is not None:
        for _ in range(4):
            gap = plr_min - (true_peak_db(y, sr) - lufs(y, sr))
            if gap <= 1e-3: break
            G -= gap + 0.01; plr_fix += gap + 0.01
            y = _soft_clip(x * 10 ** (G / 20), ceil_lin, clip_db)
            y, gr = _limit(y, sr, ceil_lin)
        L = lufs(y, sr)
    pre = x * 10 ** (G / 20)
    pre_tp = true_peak_db(pre, sr)
    clip_tp = true_peak_db(_soft_clip(pre, ceil_lin, clip_db), sr)
    overs_pct = float((np.abs(pre) > ceil_lin).mean() * 100)
    tp = true_peak_db(y, sr)
    if tp > ceil_db:
        y = y * 10 ** ((ceil_db - tp - 0.01) / 20); L = lufs(y, sr)
    guard = None
    if G >= Gmax - 1e-6 and L < target - 0.15:
        guard = {"requested_lufs": round(float(target), 2), "applied_lufs": round(float(L), 2), "max_cut_db": float(max_cut)}
    rep["loudness"] = {"input_lufs": round(L0, 2), "gain_db": round(G, 2), "limiter_avg_gr_db": round(float(gr.mean()), 2),
                       "limiter_p95_gr_db": round(p95, 2), "limiter_max_gr_db": round(float(gr.max()), 2),
                       "pre_clip_peak_dbtp": round(pre_tp, 2), "after_clip_peak_dbtp": round(clip_tp, 2),
                       "clipper_share_db": round(max(pre_tp - clip_tp, 0.0), 2),
                       "samples_over_ceiling_pct": round(overs_pct, 3),
                       "shortfall_db": round(float(max(short, 0)), 2),
                       "peak_cut_db": round(max(pre_tp - ceil_db, 0.0), 2), "plr_min": plr_min, "plr_fix_db": round(plr_fix, 2),
                       "target_lufs": round(float(L if guard else target), 2), "peak_cut_guard": guard}
    return y

def qc(x, sr, target, ceil_db, in_rep):
    w = []
    L, tp = lufs(x, sr), true_peak_db(x, sr)
    if tp > ceil_db + 0.1: w.append(f"true peak {tp:.2f} dBTP above ceiling {ceil_db}")
    if abs(L - target) > 0.6: w.append(f"loudness {L:.1f} LUFS is {abs(L - target):.1f} dB from target (mix too dynamic or too quiet to reach it safely)")
    c = float(np.corrcoef(x[0], x[1])[0, 1]) if x[0].std() > 0 else 1.0
    if c < 0.3: w.append(f"low L/R correlation {c:.2f}: weak mono compatibility")
    if abs(x.mean()) > 0.005: w.append("DC offset present")
    clipped = int((np.abs(x) >= 0.9999).sum())
    if clipped: w.append(f"{clipped} samples at digital full scale")
    if in_rep.get("input_balance_warning"): w.append(in_rep["input_balance_warning"])
    return {"lufs": round(L, 2), "true_peak_dbtp": round(tp, 2), "plr_db": round(tp - L, 2), "correlation": round(c, 3),
            "crest_db": round(float(20 * np.log10(np.abs(x).max() / (np.sqrt((x ** 2).mean()) + 1e-12))), 2), "warnings": w}

def _tone_probe(x, sr, curve=None):
    m = x.mean(axis=0)
    g = (REF_MEDIAN if curve is None else curve) - _ltas(x, sr)
    g = g - np.median(g[(CENTERS >= 160) & (CENTERS <= 8000)])
    med = lambda lo, hi: float(np.median(g[(CENTERS >= lo) & (CENTERS <= hi)]))
    band = (CENTERS >= 40) & (CENTERS <= 16000)
    lo = sg.sosfilt(sg.butter(4, [30, 120], btype="band", fs=sr, output="sos"), m)
    mid = sg.sosfilt(sg.butter(4, [150, 9000], btype="band", fs=sr, output="sos"), m)
    return {"low_50_100_gap_db": round(med(50, 100), 1), "mud_200_315_gap_db": round(med(200, 315), 1),
            "vocal_hot_0.8_2.5k_db": round(-med(800, 2500), 1), "top_5_10k_gap_db": round(med(5000, 10000), 1),
            "distance_db": round(float(np.sqrt((g[band] ** 2).mean())), 2), "side_db": round(_side_db(x, sr), 1),
            "kick_to_mid_peak_db": round(float(20 * np.log10(np.abs(lo).max() / (np.abs(mid).max() + 1e-12))), 1)}

def master(x, sr, preset="afrobeats", **over):
    key = _resolve_preset(preset)
    p = dict(PRESETS[key]); p.update(over)
    prof = REFERENCES.get(p.get("ref")) if p.get("ref_eq", True) else None
    curve = None if prof is None else np.asarray(prof["curve"], dtype=float)
    if prof is None:
        p["eq"] = 0.0; p["eq_floor"] = 0.0; p["adapt_width"] = False
    xc, kind = _to_cn(x)
    p["eq"] = max(float(p["eq"]), float(p.get("eq_floor", 0.0)))
    _cap = float(p["ceil"]) - float(p.get("plr_floor", 9.2))
    _guard = None
    if p["lufs"] > _cap:
        _guard = {"requested_lufs": round(float(p["lufs"]), 2), "applied_lufs": round(_cap, 2),
                  "plr_floor": float(p.get("plr_floor", 9.2))}
        p["lufs"] = _cap
    rep = {"preset": preset, "resolved_preset": key, "reference": p.get("ref") if prof else None, "params": p}
    if _guard: rep["plr_guard"] = _guard
    if not np.isfinite(xc).all(): xc = np.nan_to_num(xc)
    xc = xc - xc.mean(axis=1, keepdims=True)
    if np.abs(xc).max() < 1e-6 or xc.shape[1] < sr:
        rep["warning"] = "input silent or shorter than 1 s: not processed"
        return _from_cn(xc, kind), rep
    rep["input"] = {"lufs": round(lufs(xc, sr), 2), "true_peak_dbtp": round(true_peak_db(xc, sr), 2)}
    if curve is not None:
        try: rep["tone_in"] = _tone_probe(xc, sr, curve)
        except Exception as _e: rep["tone_in_error"] = str(_e)[:80]
        cur = _ltas(xc, sr)
        vb = (CENTERS >= 800) & (CENTERS <= 2500)
        vgap = float(np.median((cur - curve)[vb]) - np.median((cur - curve)[(CENTERS >= 100) & (CENTERS <= 8000)]))
        if vgap > 3.0:
            rep["input_balance_warning"] = (f"0.8-2.5 kHz is {vgap:.1f} dB hotter than {p.get('ref')} reference masters: "
                                            "vocal is probably too loud against the beat, fix in the mix not the master")
    y = stage_eq(xc, sr, p["eq"], rep, curve)
    y = stage_multiband(y, sr, p["mb"], rep)
    y = stage_glue(y, sr, p["glue"], rep)
    y = stage_saturate(y, sr, p["sat"], rep)
    y = stage_top_trim(y, sr, float(p.get("top_trim", 0.0)), rep, curve if curve is not None else REF_MEDIAN, 0.5 if curve is not None else 3.0)
    y = stage_stereo(y, sr, p["adapt_width"], rep, width_min=float(p.get("width_min", 0.9)), side_target=float(prof["side_db"]) if prof else REF_SIDE_DB)
    y = stage_loudness(y, sr, p["lufs"], p["ceil"], p["clip"], p["max_gr"], rep, max_cut=p.get("max_cut"), plr_min=float(p.get("plr_floor", 9.2)) - 0.05)
    rep["output"] = qc(y, sr, rep["loudness"].get("target_lufs", p["lufs"]), p["ceil"], rep)
    g = rep["loudness"].get("peak_cut_guard")
    if g:
        rep["output"]["notes"] = [f"peak-cut guard: target lowered {g['requested_lufs']} -> {g['applied_lufs']} LUFS (this mix needs more than {g['max_cut_db']} dB of peak removal to reach it)"]
    if curve is not None:
        try: rep["tone_out"] = _tone_probe(y, sr, curve)
        except Exception as _e: rep["tone_out_error"] = str(_e)[:80]
    return _from_cn(y, kind), rep
