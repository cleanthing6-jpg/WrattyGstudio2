"""
reverb_fx.py - professional vocal reverb for WrattyGstudio.  numpy only.
"""
import numpy as np

REVERB_PRESETS = {
    "afrobeats": dict(rt60=1.30, hp=300.0, lp=9000.0,  duck_db=4.0, width=0.90, level_db=-20.0, er_db=-9.0,  hf_damp=0.55, lf_mult=0.90, pd_scale=1.0),
    "amapiano":  dict(rt60=1.80, hp=350.0, lp=10000.0, duck_db=5.0, width=1.00, level_db=-21.0, er_db=-11.0, hf_damp=0.60, lf_mult=0.85, pd_scale=1.1),
    "highlife":  dict(rt60=1.10, hp=250.0, lp=6500.0,  duck_db=3.0, width=0.80, level_db=-19.0, er_db=-7.0,  hf_damp=0.50, lf_mult=0.95, pd_scale=0.8),
    "pop":       dict(rt60=1.50, hp=300.0, lp=9500.0,  duck_db=4.0, width=0.90, level_db=-20.0, er_db=-9.0,  hf_damp=0.58, lf_mult=0.90, pd_scale=1.0),
    "rnb":       dict(rt60=2.10, hp=300.0, lp=7500.0,  duck_db=4.0, width=1.00, level_db=-18.0, er_db=-10.0, hf_damp=0.50, lf_mult=0.85, pd_scale=1.1),
    "rap":       dict(rt60=0.85, hp=350.0, lp=8500.0,  duck_db=6.0, width=0.70, level_db=-23.0, er_db=-6.0,  hf_damp=0.50, lf_mult=0.95, pd_scale=0.8),
    "neutral":   dict(rt60=1.20, hp=300.0, lp=9000.0,  duck_db=4.0, width=0.80, level_db=-21.0, er_db=-9.0,  hf_damp=0.55, lf_mult=0.90, pd_scale=1.0),
}

RT60_MIN, RT60_MAX = 0.5, 3.0
ACTIVE_GATE_DB = -45.0
_CENTERS = np.array([150.0, 500.0, 1500.0, 4500.0, 10000.0])
_IR_CACHE = {}


def fold_bpm(bpm, lo=70.0, hi=140.0):
    try: b = float(bpm)
    except (TypeError, ValueError): return 100.0
    if not np.isfinite(b) or b <= 0: return 100.0
    while b < lo: b *= 2.0
    while b > hi: b /= 2.0
    return b


def _mono(voc):
    a = np.asarray(voc)
    if a.ndim == 1: return a.astype(np.float64)
    return a.mean(axis=0, dtype=np.float64) if a.shape[0] <= a.shape[1] else a.mean(axis=1, dtype=np.float64)


def _rms(a, chunk=1 << 20):
    flat = np.asarray(a).reshape(-1)
    acc = 0.0
    for i in range(0, flat.size, chunk):
        c = flat[i:i + chunk].astype(np.float64)
        acc += float(np.dot(c, c))
    return float(np.sqrt(acc / max(flat.size, 1)))


def _shape(x, sr, hp, lp, order=2, block=1 << 17, pad=4096):
    n = len(x)
    out = np.empty(n, dtype=np.float32)
    nfft = 1 << int(np.ceil(np.log2(block + 2 * pad)))
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    f[0] = 1e-3
    H = np.ones_like(f)
    if hp: H = H / np.sqrt(1.0 + (hp / f) ** (2 * order))
    if lp: H = H / np.sqrt(1.0 + (f / lp) ** (2 * order))
    for s in range(0, n, block):
        e = min(n, s + block)
        a, b = max(0, s - pad), min(n, e + pad)
        y = np.fft.irfft(np.fft.rfft(x[a:b], nfft) * H, nfft)[:b - a]
        out[s:e] = y[s - a:e - a]
    return out


def _duck_gain(x, sr, depth_db, release_ms):
    n = len(x)
    blk = max(1, int(sr * 0.001))
    m = n // blk
    if m < 10 or depth_db <= 0: return np.ones(n, dtype=np.float32)
    pk = np.abs(x[:m * blk]).reshape(m, blk).max(axis=1)
    att = np.exp(-1.0 / 3.0)
    rel = np.exp(-1.0 / max(release_ms, 20.0))
    env = np.empty(m); e = 0.0
    for i in range(m):
        c = att if pk[i] > e else rel
        e = c * e + (1.0 - c) * pk[i]
        env[i] = e
    env_db = 20.0 * np.log10(env + 1e-9)
    live = env > 1e-4
    ref_db = float(np.percentile(env_db[live], 75)) if live.any() else -20.0
    amt = np.clip((env_db - (ref_db - 20.0)) / 14.0, 0.0, 1.0)
    g = 10.0 ** (-depth_db * amt / 20.0)
    out = np.empty(n, dtype=np.float32)
    xs = (np.arange(m) + 0.5) * blk
    for i in range(0, n, 1 << 20):
        j = min(n, i + (1 << 20))
        out[i:j] = np.interp(np.arange(i, j), xs, g)
    return out


def _band_weights(nfft, sr):
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    f[0] = 1.0
    lf = np.log(f); lc = np.log(_CENTERS)
    k = len(lc); W = np.zeros((k, f.size))
    for i in range(k):
        if i == 0: W[i] = np.interp(lf, [lc[0], lc[1]], [1.0, 0.0], left=1.0, right=0.0)
        elif i == k - 1: W[i] = np.interp(lf, [lc[-2], lc[-1]], [0.0, 1.0], left=0.0, right=1.0)
        else: W[i] = np.interp(lf, [lc[i-1], lc[i], lc[i+1]], [0.0, 1.0, 0.0], left=0.0, right=0.0)
    return W


def make_ir(sr, rt60, pre_ms, er_db=-9.0, hf_damp=0.55, lf_mult=0.90, seed=7):
    key = (int(sr), round(float(rt60), 2), round(float(pre_ms), 1), round(float(er_db), 1),
           round(float(hf_damp), 2), round(float(lf_mult), 2), int(seed))
    hit = _IR_CACHE.get(key)
    if hit is not None: return hit
    L = int(sr * min(3.6, rt60 * 1.15 + 0.1))
    t = np.arange(L) / float(sr)
    nfft = 1 << int(np.ceil(np.log2(L)))
    Wt = _band_weights(nfft, sr)
    mult = [lf_mult, 1.0, 0.90, hf_damp, hf_damp * 0.6]
    shared = np.random.default_rng(seed).standard_normal(L)
    Xs = np.fft.rfft(shared, nfft)
    pre = int(round(pre_ms * sr / 1000.0))
    irs = []
    for ch in range(2):
        rng = np.random.default_rng(seed + 101 * (ch + 1))
        Xn = np.fft.rfft(rng.standard_normal(L), nfft)
        tail = np.zeros(L)
        for b in range(len(mult)):
            Xb = (Xs if b == 0 else Xn) * Wt[b]
            tail += np.fft.irfft(Xb, nfft)[:L] * np.exp(-6.9078 * t / (rt60 * mult[b]))
        t0 = 0.010
        tail *= np.where(t < t0, 0.0, 1.0 - np.exp(-(t - t0) / 0.020))
        tail /= max(float(np.sqrt(np.sum(tail ** 2))), 1e-12)
        er = np.zeros(L)
        times = np.sort(rng.uniform(0.004, 0.055, 10))
        kern = np.hanning(max(3, int(0.0004 * sr)))
        for k, tm in enumerate(times):
            i0 = int(tm * sr)
            amp = (0.88 ** k) * (1.0 if rng.random() > 0.5 else -1.0)
            er[i0:i0 + kern.size] += amp * kern[:max(0, min(kern.size, L - i0))]
        e_er = float(np.sum(er ** 2))
        if e_er > 0:
            er *= np.sqrt(10.0 ** (er_db / 10.0) / e_er)
        h = tail + er
        h /= max(float(np.sqrt(np.sum(h ** 2))), 1e-12)
        irs.append(np.concatenate([np.zeros(pre), h]))
    ir = np.stack(irs)
    if len(_IR_CACHE) > 24: _IR_CACHE.clear()
    _IR_CACHE[key] = ir
    return ir


def _conv_blocks(x, ir, block=1 << 16):
    n, L = len(x), ir.shape[1]
    nfft = 1 << int(np.ceil(np.log2(block + L - 1)))
    HL = np.fft.rfft(ir[0], nfft)
    HR = np.fft.rfft(ir[1], nfft)
    out = np.zeros((2, n + L - 1), dtype=np.float32)
    for s in range(0, n, block):
        seg = x[s:s + block]
        if float(np.max(np.abs(seg))) < 1e-7: continue
        X = np.fft.rfft(seg, nfft)
        m = len(seg) + L - 1
        out[0, s:s + m] += np.fft.irfft(X * HL, nfft)[:m]
        out[1, s:s + m] += np.fft.irfft(X * HR, nfft)[:m]
    return out


def render(voc, sr, bpm, preset="neutral", overrides=None, target_rms=None, out_len=None):
    p = dict(REVERB_PRESETS.get(str(preset).lower(), REVERB_PRESETS["neutral"]))
    if overrides: p.update(overrides)
    x = _mono(voc)
    n = len(x)
    n_out = int(out_len) if out_len else n
    info = {"preset": str(preset), "rt60_s": None, "predelay_ms": None, "bpm_used": None, "density": None, "duck_db": None, "ir_len_s": None}
    wet = np.zeros((2, n_out), dtype=np.float32)
    if n < sr // 2 or float(np.max(np.abs(x))) < 1e-6: return wet, info
    w = int(0.05 * sr); k = n // w
    fr = 20.0 * np.log10(np.sqrt((x[:k * w].reshape(k, w) ** 2).mean(axis=1)) + 1e-12)
    act = fr > ACTIVE_GATE_DB
    dens = float(act.mean()) if k else 0.0
    b = fold_bpm(bpm)
    rt = float(p["rt60"]) * float(np.clip(100.0 / b, 0.8, 1.25))
    lvl = float(p["level_db"]); duck = float(p["duck_db"])
    if dens > 0.75: rt *= 0.85; lvl -= 1.5
    elif dens < 0.45: rt *= 1.15; lvl += 1.5
    rt = float(np.clip(rt, RT60_MIN, RT60_MAX))
    pre_ms = float(np.clip(60000.0 / b / 16.0 * float(p["pd_scale"]), 18.0, 45.0))
    ir = make_ir(sr, rt, pre_ms, p["er_db"], p["hf_damp"], p["lf_mult"])
    send = _shape(x, sr, p["hp"], p["lp"])
    full = _conv_blocks(send, ir)
    m = min(full.shape[1], n_out)
    wet[:, :m] = full[:, :m]
    del full
    wd = float(np.clip(p["width"], 0.0, 1.0))
    if wd < 1.0:
        mid = (wet[0] + wet[1]) * 0.5
        side = (wet[0] - wet[1]) * 0.5 * wd
        wet[0] = mid + side
        wet[1] = mid - side
    mask = np.repeat(act, w)
    mask = np.concatenate([mask, np.zeros(max(0, n - mask.size), dtype=bool)])[:n]
    ref_send = _rms(send[mask]) if mask.any() else 1e-6
    wm = wet[:, :n][:, mask[:min(n, n_out)]] if mask.any() else wet
    cur_act = _rms(wm) if wm.size else 1e-6
    if cur_act > 1e-12:
        wet *= np.float32(ref_send * 10.0 ** (lvl / 20.0) / cur_act)
    release = float(np.clip(0.20 * rt * 1000.0, 120.0, 350.0))
    gain = _duck_gain(x, sr, duck, release)
    mm = min(n, n_out)
    wet[:, :mm] *= gain[None, :mm]
    if target_rms is not None and target_rms > 0:
        cur = _rms(wet)
        if cur > 1e-12: wet *= np.float32(target_rms / cur)
    peak = float(np.abs(wet).max())
    if peak > 0.5: wet *= np.float32(0.5 / peak)
    info.update({"rt60_s": round(rt, 2), "predelay_ms": round(pre_ms, 1), "bpm_used": round(b, 1), "density": round(dens, 3), "duck_db": round(duck, 1), "ir_len_s": round(ir.shape[1] / sr, 2), "release_ms": round(release)})
    return wet, info
