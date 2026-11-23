"""
vocal_fx_detect.py -- is this vocal ALREADY processed?  Stops the engine from stacking a second
reverb / delay / widening / tuning on top of effects the artist (or their DAW) already printed.
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

HOP = 0.01
BYPASS_AT = 0.90
REDUCE_AT = 0.45

def _prep(voc, sr):
    x = np.asarray(voc, dtype=np.float64)
    st = x if x.ndim == 2 else np.stack([x, x])
    st = st[:2]
    m = st.mean(0)
    n = int(HOP * sr)
    sos = sg.butter(4, [150, 6000], btype="band", fs=sr, output="sos")
    b = sg.sosfilt(sos, m)
    k = len(b) // n
    e = 20 * np.log10(np.sqrt((b[: k * n].reshape(k, n) ** 2).mean(1)) + 1e-9)
    top = float(np.percentile(e, 95)); floor = float(np.percentile(e, 5))
    act = e > max(top - 32.0, floor + 12.0)
    act = ndimage.binary_closing(act, np.ones(8)); act = ndimage.binary_opening(act, np.ones(5))
    lab, nl = ndimage.label(act)
    runs = [(int(np.where(lab == j)[0][0]), int(np.where(lab == j)[0][-1])) for j in range(1, nl + 1)]
    return {"st": st, "m": m, "e": e, "act": act, "runs": runs, "top": top, "floor": floor, "sr": sr}

def _conf(*parts):
    p = np.clip(np.array(parts, dtype=float), 0.0, 1.0)
    return float(np.prod(p) ** (1.0 / len(p))) if (p > 0).all() else float(np.prod(p))

def detect_reverb(P):
    e, runs, floor = P["e"], P["runs"], P["floor"]
    rows = []
    for i, (a, z) in enumerate(runs):
        if z - a < 25: continue
        nxt = runs[i + 1][0] if i + 1 < len(runs) else len(e)
        if nxt - z < 90: continue
        loc = float(np.median(e[z + 62: nxt - 3])) if nxt - z > 70 else floor
        seg = e[z + 1: z + 55] - loc
        seg = np.minimum.accumulate(ndimage.uniform_filter1d(seg, 5, mode="nearest"))
        a_ex = float(seg[11:25].mean()); b_ex = float(seg[25:45].mean())
        tt = np.arange(8, 45) * HOP; yy = seg[8:45]
        sl, ic = np.polyfit(tt, yy, 1)
        r2 = 1 - ((yy - (sl * tt + ic)) ** 2).sum() / (((yy - yy.mean()) ** 2).sum() + 1e-9)
        rt = float(np.clip(-60.0 / sl, 0.1, 5.0)) if sl < -1 else None
        ok = a_ex >= 9.0 and b_ex >= 3.0 and a_ex > b_ex and sl < -6.0 and r2 >= 0.55
        rows.append((a_ex, b_ex, sl, r2, rt, ok))
    n = len(rows)
    out = {"present": False, "confidence": 0.0, "phrases_checked": n, "rt60_s": None, "tail_db": None, "consistency": 0.0}
    if n < 3: return out
    R = np.array([(r[0], r[1], r[2], r[3]) for r in rows]); okm = np.array([r[5] for r in rows])
    frac = float(okm.mean())
    good = R[okm] if okm.any() else R
    rts = [r[4] for r, k in zip(rows, okm) if k and r[4]]
    out.update(tail_db=round(float(np.median(R[:, 0])), 1), consistency=round(frac, 2),
               rt60_s=round(float(np.median(rts)), 2) if rts else None)
    c1 = (np.median(good[:, 0]) - 8.0) / 12.0
    c2 = (frac - 0.35) / 0.40
    c3 = (np.median(good[:, 3]) - 0.5) / 0.35
    c4 = (okm.sum() - 2) / 4.0
    out["confidence"] = round(_conf(c1, c2, c3, c4), 3) if okm.any() else 0.0
    out["present"] = out["confidence"] >= REDUCE_AT
    return out

def _lag_profile(P, hi_ms=1700):
    sr = P["sr"]
    sos = sg.butter(4, [200, 5000], btype="band", fs=sr, output="sos")
    b = sg.sosfilt(sos, P["m"])
    n = int(0.02 * sr); k = len(b) // n
    fr = b[: k * n].reshape(k, n)
    g = np.sqrt((fr ** 2).mean(1, keepdims=True))
    fr = np.where(g > 1e-4, fr / (g + 1e-12), 0.0)
    b = fr.reshape(-1)
    N = 1 << int(np.ceil(np.log2(len(b) * 2)))
    X = np.fft.rfft(b, N)
    ac = np.fft.irfft(np.abs(X) ** 2)[: int(hi_ms / 1000 * sr)]
    return ac / (ac[0] + 1e-12)

def detect_delay(P, bpm=None):
    sr = P["sr"]
    ac = _lag_profile(P)
    lo = int(0.08 * sr); hi = len(ac) - int(0.05 * sr)
    a = ac[lo:hi]
    w = int(0.06 * sr) | 1
    med = sg.medfilt(np.abs(a), w)
    mad = sg.medfilt(np.abs(np.abs(a) - med), w) + 1e-9
    z = (a - med) / (1.4826 * mad)
    idx = sg.find_peaks(z, height=6.0, distance=int(0.02 * sr))[0]
    idx = idx[a[idx] >= 0.02]
    out = {"present": False, "confidence": 0.0, "delay_ms": None, "peaks": len(idx)}
    if len(idx) == 0: return out
    lag = (idx + lo) / sr * 1000.0; amp = a[idx]; zz = z[idx]
    best = None
    for D in lag:
        mem = [(i, kk) for i, l in enumerate(lag) for kk in range(1, 8) if abs(l - kk * D) <= max(8.0, 0.02 * kk * D)]
        if not mem: continue
        ii = sorted({i for i, _ in mem}); ks = sorted({kk for _, kk in mem})
        strong = float(amp[ii].max())
        score = (len(ks), strong, -D)
        if best is None or score > best[0]:
            best = (score, D, ii, ks)
    _, D, ii, ks = best
    nmem = len(ks); strong = float(amp[ii].max()); zs = float(np.median(zz[ii]))
    c_amp = (strong - 0.03) / 0.12
    c_z = (zs - 5.0) / 8.0
    c_cnt = (nmem - 1) / 2.0 if nmem > 1 else (1.0 if strong >= 0.25 else 0.0)
    conf = _conf(c_amp, c_z, c_cnt)
    ms = float(np.mean([lag[i] / kk for i, kk in [(i, kk) for i, kk in
               [(i, kk) for i in ii for kk in range(1, 8) if abs(lag[i] - kk * D) <= max(8.0, 0.02 * kk * D)]]]))
    synced = None
    if bpm and 50 <= bpm <= 210:
        beat = 60000.0 / bpm; fr = ms / beat
        synced = any(abs(fr - q) / q < 0.05 for q in (0.25, 1 / 3, 0.5, 0.75, 1.0, 1.5, 2.0))
    fb = None
    amps = {kk: float(amp[i]) for i in ii for kk in range(1, 8) if abs(lag[i] - kk * D) <= max(8.0, 0.02 * kk * D)}
    rat = [amps[k + 1] / amps[k] for k in amps if k + 1 in amps and amps[k] > 0 and amps[k + 1] < amps[k]]
    if rat: fb = round(float(np.median(rat)), 2)
    return {"present": conf >= REDUCE_AT, "confidence": round(conf, 3), "delay_ms": round(ms, 0), "peaks": len(idx),
            "repeats": nmem, "strongest_peak": round(strong, 3), "feedback_est": fb, "tempo_synced": synced}

def detect_stereo(P):
    st, act = P["st"], P["act"]
    sr = P["sr"]; n = int(HOP * sr)
    L, R = st[0], st[1]
    k = len(L) // n
    am = np.repeat(act[:k], n)[: k * n]
    l, r = L[: k * n][am], R[: k * n][am]
    if len(l) < sr: return {"present": False, "confidence": 0.0, "width": "unknown"}
    corr = float(np.corrcoef(l, r)[0, 1]) if l.std() > 0 and r.std() > 0 else 1.0
    M, S = (l + r) / 2, (l - r) / 2
    side_db = float(10 * np.log10((S ** 2).mean() / ((M ** 2).mean() + 1e-12) + 1e-12))
    seg = slice(0, min(len(L), 20 * sr))
    xc = sg.correlate(L[seg], R[seg], mode="full", method="fft"); mid = len(L[seg]) - 1
    W = int(0.04 * sr); win = xc[mid - W: mid + W + 1]
    lag_ms = float((np.argmax(np.abs(win)) - W) / sr * 1000.0)
    wide = corr < 0.985 or side_db > -22.0
    conf = _conf((0.995 - corr) / 0.08, 1.0) if wide else 0.0
    if side_db > -16.0: conf = max(conf, 0.95)
    return {"present": bool(wide and conf >= REDUCE_AT), "confidence": round(float(np.clip(conf, 0, 1)), 3),
            "correlation": round(corr, 3), "side_db": round(side_db, 1), "interchannel_lag_ms": round(lag_ms, 1),
            "width": "stereo" if wide else "mono/dual-mono"}

def _f0_track(P):
    m, sr, act = P["m"], P["sr"], P["act"]
    n = int(0.03 * sr); hop = int(HOP * sr)
    lo, hi = int(sr / 700), int(sr / 70)
    win = np.hanning(n)
    Wf = np.fft.rfft(win, 2 * n); aw = np.fft.irfft(np.abs(Wf) ** 2)[:n]; aw = aw / aw[0]
    aw = np.maximum(aw, 0.05)
    f0 = []; cents = []
    for i in range(0, len(m) - n, hop):
        fi = i // hop
        if fi >= len(act) or not act[fi]: continue
        x = m[i:i + n] - m[i:i + n].mean()
        if np.abs(x).max() < 1e-4: continue
        X = np.fft.rfft(x * win, 2 * n)
        ac = np.fft.irfft(np.abs(X) ** 2)[:n]
        ac = ac / (ac[0] + 1e-12) / aw
        seg = ac[lo:hi]
        mx = float(seg.max())
        if mx < 0.88: continue
        k = int(np.argmax(seg >= 0.93 * mx))
        while k + 1 < len(seg) and seg[k + 1] > seg[k]: k += 1
        if k == 0 or k == len(seg) - 1: continue
        a_, b_, c_ = seg[k - 1], seg[k], seg[k + 1]
        den = a_ - 2 * b_ + c_
        kk = k + (0.5 * (a_ - c_) / den if abs(den) > 1e-12 else 0.0)
        f = sr / (lo + kk)
        f0.append((fi, f)); cents.append(1200 * np.log2(f / 440.0))
    return np.array(f0), np.array(cents)

def detect_pitch(P):
    f0, c = _f0_track(P)
    if len(c) < 200: return {"present": False, "confidence": 0.0, "tuned": False, "voiced_frames": int(len(c))}
    best, bo = 0.0, 0.0
    for o in np.arange(-50, 50, 2.0):
        d = np.abs(((c - o + 50) % 100) - 50)
        fr = float((d <= 8).mean())
        if fr > best: best, bo = fr, float(o)
    fi = f0[:, 0]
    adj = np.diff(fi) == 1
    dc = np.abs(np.diff(c))
    flat = float((dc[adj] <= 1.5).mean()) if adj.any() else 0.0
    c1 = (best - 0.35) / 0.35
    c2 = (flat - 0.15) / 0.30
    conf = _conf(c1, c2)
    return {"present": conf >= REDUCE_AT, "tuned": conf >= REDUCE_AT, "confidence": round(conf, 3), "on_grid_fraction": round(best, 2),
            "flat_fraction": round(flat, 2), "voiced_frames": int(len(c)), "tuning_offset_cents": round(bo, 0)}

def dynamics(P):
    return {"swing_db": None}

def analyze(voc, sr, bpm=None):
    voc = np.asarray(voc)
    if voc.ndim == 2 and voc.shape[0] > voc.shape[1] and voc.shape[1] <= 8: voc = voc.T
    if voc.ndim == 2 and voc.shape[0] == 1: voc = voc[0]
    x = voc
    if x.size == 0 or x.shape[-1] < sr * 12:
        return {"verdict": "unknown", "reasons": ["clip shorter than 12 s"], "reverb": {"confidence": 0.0}, "delay": {"confidence": 0.0}, "stereo": {"confidence": 0.0}, "pitch": {"confidence": 0.0}, "dynamics": {}}
    P = _prep(voc, sr)
    a = {"reverb": detect_reverb(P), "delay": detect_delay(P, bpm), "stereo": detect_stereo(P), "pitch": detect_pitch(P), "dynamics": dynamics(P)}
    hits = [k for k in ("reverb", "delay", "stereo", "pitch") if a[k].get("confidence", 0) >= BYPASS_AT]
    maybe = [k for k in ("reverb", "delay", "stereo", "pitch") if REDUCE_AT <= a[k].get("confidence", 0) < BYPASS_AT]
    a["verdict"] = ("processed: " + ", ".join(hits)) if hits else ("probably processed: " + ", ".join(maybe)) if maybe else "dry (no effects found)"
    a["reasons"] = []
    return a

def engine_plan(a):
    plan = {"reverb_send_scale": 1.0, "delay_send_scale": 1.0, "skip_adt": False, "skip_widen": False, "skip_pitch_correct": False, "reasons": []}
    def scale(c):
        if c >= BYPASS_AT: return 0.0
        if c >= REDUCE_AT: return float(np.clip(1.2 - 1.2 * c, 0.1, 1.0))
        return 1.0
    r, d, s, p = a["reverb"], a["delay"], a["stereo"], a["pitch"]
    plan["reverb_send_scale"] = scale(r.get("confidence", 0.0))
    plan["delay_send_scale"] = scale(d.get("confidence", 0.0))
    if r.get("confidence", 0) >= REDUCE_AT: plan["reasons"].append("reverb already in the vocal")
    if d.get("confidence", 0) >= REDUCE_AT: plan["reasons"].append("delay already in the vocal")
    if s.get("confidence", 0) >= BYPASS_AT:
        plan["skip_adt"] = True; plan["skip_widen"] = True
        plan["reasons"].append("vocal is already stereo / doubled")
    if p.get("confidence", 0) >= BYPASS_AT:
        plan["skip_pitch_correct"] = True
        plan["reasons"].append("pitch already corrected")
    return plan


# --- short-gap reverb/delay detection (fx_detect_extra) ---
try:
    import fx_detect_extra as _fxx
    _analyze_base = analyze
    def analyze(voc, sr, bpm=None):
        a = _analyze_base(voc, sr, bpm)
        try:
            return _fxx.augment(a, voc, sr, bpm)
        except Exception as _e:
            a["extra_error"] = str(_e)[:80]
            return a
except Exception:
    pass
