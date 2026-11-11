"""
vocal_fx_detect.py -- is this vocal ALREADY processed?  Stops the engine from stacking a second
reverb / delay / widening / tuning on top of effects the artist (or their DAW) already printed.

It measures; it does not guess.  Every effect needs SEVERAL independent signs before it is called, and
the engine is told to bypass only when the evidence is overwhelming.  Anything unclear = "normal":
the engine behaves exactly as it does today.

    a = analyze(voc, sr, bpm=None)       # voc: (N,) or (C,N) float
    a["reverb"]["confidence"], a["delay"]["delay_ms"], a["stereo"]["width"], a["pitch"]["tuned"] ...
    plan = engine_plan(a)                # what to change in the engine, per effect

    plan = {"reverb_send_scale": 0.0..1.0, "delay_send_scale": 0.0..1.0,
            "skip_adt": bool, "skip_widen": bool, "skip_pitch_correct": bool, "reasons": [...]}
      scale 1.0 = engine as usual, 0.0 = bypass (only when confidence >= BYPASS_AT),
      in between = reduce (confidence 0.55 .. BYPASS_AT).

numpy/scipy only, stateless, deterministic.
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

HOP = 0.01
BYPASS_AT = 0.90          # bypass an effect only at/above this confidence
REDUCE_AT = 0.55          # start reducing the engine's own effect above this


# ------------------------------------------------------------------ shared front end
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


# ------------------------------------------------------------------ reverb
def detect_reverb(P):
    e, runs, floor = P["e"], P["runs"], P["floor"]
    rows = []
    for i, (a, z) in enumerate(runs):
        if z - a < 25:
            continue
        nxt = runs[i + 1][0] if i + 1 < len(runs) else len(e)
        if nxt - z < 90:                                   # need ~0.9 s of quiet to look at the tail
            continue
        loc = float(np.median(e[z + 62: nxt - 3])) if nxt - z > 70 else floor
        seg = e[z + 1: z + 55] - loc                       # tail above the local floor
        a_ex = float(seg[11:25].mean()); b_ex = float(seg[25:45].mean())
        tt = np.arange(8, 45) * HOP; yy = seg[8:45]
        sl, ic = np.polyfit(tt, yy, 1)
        r2 = 1 - ((yy - (sl * tt + ic)) ** 2).sum() / (((yy - yy.mean()) ** 2).sum() + 1e-9)
        rt = float(np.clip(-60.0 / sl, 0.1, 5.0)) if sl < -1 else None
        ok = a_ex >= 9.0 and b_ex >= 3.0 and a_ex > b_ex and sl < -6.0 and r2 >= 0.55
        rows.append((a_ex, b_ex, sl, r2, rt, ok))
    n = len(rows)
    out = {"present": False, "confidence": 0.0, "phrases_checked": n, "rt60_s": None, "tail_db": None, "consistency": 0.0}
    if n < 3:
        out["why"] = "too few phrase endings with silence after them to judge"
        return out
    R = np.array([(r[0], r[1], r[2], r[3]) for r in rows]); okm = np.array([r[5] for r in rows])
    frac = float(okm.mean())
    good = R[okm] if okm.any() else R
    rts = [r[4] for r, k in zip(rows, okm) if k and r[4]]
    out.update(tail_db=round(float(np.median(R[:, 0])), 1), consistency=round(frac, 2),
               rt60_s=round(float(np.median(rts)), 2) if rts else None)
    c1 = (np.median(good[:, 0]) - 8.0) / 12.0          # how far the tail sits above the noise floor
    c2 = (frac - 0.35) / 0.40                          # how many phrase endings show it
    c3 = (np.median(good[:, 3]) - 0.5) / 0.35          # how clean the exponential decay is
    c4 = (okm.sum() - 2) / 4.0                         # how many independent examples
    out["confidence"] = round(_conf(c1, c2, c3, c4), 3) if okm.any() else 0.0
    out["present"] = out["confidence"] >= REDUCE_AT
    return out


# ------------------------------------------------------------------ delay / echo
def _logmel(P, nb=20, n=1024):
    sr = P["sr"]; hop = int(HOP * sr)
    f, t, S = sg.stft(P["m"], sr, nperseg=n, noverlap=n - hop, window="hann", boundary=None, padded=False)
    pw = np.abs(S) ** 2
    edges = np.geomspace(150, 7000, nb + 1)
    M = np.stack([pw[(f >= edges[i]) & (f < edges[i + 1])].sum(0) for i in range(nb)]) + 1e-12
    L = 10 * np.log10(M)
    V = L - L.mean(0, keepdims=True)
    V = V / (np.linalg.norm(V, axis=0, keepdims=True) + 1e-9)
    return V, L.mean(0)


def detect_delay(P, bpm=None):
    e, runs, floor = P["e"], P["runs"], P["floor"]
    V, lev = _logmel(P)
    n = min(V.shape[1], len(e)); V = V[:, :n]; e = e[:n]
    act = P["act"][:n]
    loc_floor = np.full(n, floor)
    quiet = ~act
    # bursts = energy that RE-ATTACKS inside a gap (reverb only ever decays; a delay brings the voice back)
    de = np.diff(e, prepend=e[0])
    cands = []
    for i, (a, z) in enumerate(runs):
        nxt = runs[i + 1][0] if i + 1 < len(runs) else n
        lo, hi = z + 8, min(nxt - 2, z + 160)
        if hi - lo < 12:
            continue
        seg = e[lo:hi]
        sm = ndimage.uniform_filter1d(seg, 3)
        pk, pr = sg.find_peaks(sm, prominence=5.0, distance=8)
        for p_, prom in zip(pk, pr["prominences"]):
            t = lo + int(p_)
            if sm[p_] - floor >= 7.0 and quiet[max(0, t - 1)]:
                cands.append(t)
    if len(cands) < 4:
        return {"present": False, "confidence": 0.0, "delay_ms": None, "bursts": len(cands), "why": "no repeated bursts in the gaps"}
    pairs = []
    for t in cands:
        if t < 12 or t + 2 >= n:
            continue
        vb = V[:, t - 2: t + 3].mean(1); vb /= (np.linalg.norm(vb) + 1e-9)
        best, bd = -1.0, 0
        for d in range(8, min(150, t - 3)):
            s0 = t - d
            if not act[max(0, s0 - 1): s0 + 2].any():
                continue
            vs = V[:, s0 - 2: s0 + 3].mean(1); vs /= (np.linalg.norm(vs) + 1e-9)
            sc = float(vb @ vs)
            if sc > best: best, bd = sc, d
        if best >= 0.80:
            drop = float(e[t] - e[t - bd])
            if -36.0 <= drop <= -1.0:
                pairs.append((bd, best, drop))
    if len(pairs) < 4:
        return {"present": False, "confidence": 0.0, "delay_ms": None, "bursts": len(cands), "matched": len(pairs), "why": "bursts do not copy earlier speech"}
    d = np.array([p[0] for p in pairs]); s = np.array([p[1] for p in pairs]); dr = np.array([p[2] for p in pairs])
    hist = np.bincount(d, minlength=160); hist = ndimage.uniform_filter1d(hist.astype(float), 3)
    mode = int(np.argmax(hist)); near = (np.abs(d - mode) <= 2) | (np.abs(d - 2 * mode) <= 3) | (np.abs(d - 3 * mode) <= 4)
    conc = float(near.mean())
    ms = float(np.mean(d[np.abs(d - mode) <= 2])) * HOP * 1000.0
    synced = None
    if bpm and 50 <= bpm <= 210:
        beat = 60000.0 / bpm
        fr = ms / beat
        synced = any(abs(fr - q) / q < 0.05 for q in (0.25, 1 / 3, 0.5, 0.75, 1.0, 1.5, 2.0))
    c1 = (len(pairs) - 3) / 6.0
    c2 = (conc - 0.5) / 0.4
    c3 = (float(np.median(s)) - 0.78) / 0.14
    c4 = 1.0 if (np.abs(d - mode) <= 2).sum() >= 4 else 0.0
    conf = _conf(c1, c2, c3, c4)
    fb = None
    if 0.2 < float(np.median(10 ** (dr / 20))) < 1.0:
        fb = round(float(np.median(10 ** (dr / 20))), 2)
    return {"present": conf >= REDUCE_AT, "confidence": round(conf, 3), "delay_ms": round(ms, 0), "bursts": len(cands),
            "matched": len(pairs), "concentration": round(conc, 2), "feedback_est": fb, "tempo_synced": synced}


# ------------------------------------------------------------------ stereo / doubles
def detect_stereo(P):
    st, act = P["st"], P["act"]
    sr = P["sr"]; n = int(HOP * sr)
    L, R = st[0], st[1]
    k = len(L) // n
    am = np.repeat(act[:k], n)[: k * n]
    l, r = L[: k * n][am], R[: k * n][am]
    if len(l) < sr:
        return {"present": False, "confidence": 0.0, "width": "unknown"}
    corr = float(np.corrcoef(l, r)[0, 1]) if l.std() > 0 and r.std() > 0 else 1.0
    M, S = (l + r) / 2, (l - r) / 2
    side_db = float(10 * np.log10((S ** 2).mean() / ((M ** 2).mean() + 1e-12) + 1e-12))
    seg = slice(0, min(len(L), 20 * sr))
    xc = sg.correlate(L[seg], R[seg], mode="full", method="fft"); mid = len(L[seg]) - 1
    W = int(0.04 * sr); win = xc[mid - W: mid + W + 1]
    lag_ms = float((np.argmax(np.abs(win)) - W) / sr * 1000.0)
    wide = corr < 0.985 or side_db > -22.0
    conf = _conf((0.995 - corr) / 0.08, 1.0) if wide else 0.0
    if side_db > -16.0:
        conf = max(conf, 0.95)
    return {"present": bool(wide and conf >= REDUCE_AT), "confidence": round(float(np.clip(conf, 0, 1)), 3),
            "correlation": round(corr, 3), "side_db": round(side_db, 1), "interchannel_lag_ms": round(lag_ms, 1),
            "width": "stereo" if wide else "mono/dual-mono"}


# ------------------------------------------------------------------ pitch correction
def _f0_track(P):
    m, sr, act = P["m"], P["sr"], P["act"]
    n = int(0.03 * sr); hop = int(HOP * sr)
    lo, hi = int(sr / 700), int(sr / 70)
    _W = np.hanning(n)
    _wac = np.fft.irfft(np.abs(np.fft.rfft(_W, 2 * n)) ** 2)[:n]
    _WAC = np.maximum(_wac / _wac[0], 0.05)
    f0 = []; cents = []
    for i in range(0, len(m) - n, hop):
        fi = i // hop
        if fi >= len(act) or not act[fi]:
            continue
        x = m[i:i + n] - m[i:i + n].mean()
        if np.abs(x).max() < 1e-4:
            continue
        X = np.fft.rfft(x * _W, 2 * n)
        ac = np.fft.irfft(np.abs(X) ** 2)[:n]
        ac = (ac / (ac[0] + 1e-12)) / _WAC          # divide out the window's own autocorrelation (else low voices fail the 0.88 test)
        seg = ac[lo:hi]
        k = int(np.argmax(seg))
        if seg[k] < 0.88 or k == 0 or k == len(seg) - 1:
            continue
        a_, b_, c_ = seg[k - 1], seg[k], seg[k + 1]
        den = a_ - 2 * b_ + c_
        kk = k + (0.5 * (a_ - c_) / den if abs(den) > 1e-12 else 0.0)
        f = sr / (lo + kk)
        f0.append((fi, f)); cents.append(1200 * np.log2(f / 440.0))
    return np.array(f0), np.array(cents)


def detect_pitch(P):
    f0, c = _f0_track(P)
    if len(c) < 200:
        return {"present": False, "confidence": 0.0, "tuned": False, "voiced_frames": int(len(c)), "why": "not enough clearly voiced frames"}
    best, bo = 0.0, 0.0
    for o in np.arange(-50, 50, 2.0):
        d = np.abs(((c - o + 50) % 100) - 50)
        fr = float((d <= 8).mean())
        if fr > best: best, bo = fr, float(o)
    fi = f0[:, 0]
    adj = np.diff(fi) == 1
    dc = np.abs(np.diff(c))
    flat = float((dc[adj] <= 1.5).mean()) if adj.any() else 0.0
    c1 = (best - 0.35) / 0.35          # random singing sits near 0.16-0.30
    c2 = (flat - 0.15) / 0.30
    conf = _conf(c1, c2)
    return {"present": conf >= REDUCE_AT, "tuned": conf >= REDUCE_AT, "confidence": round(conf, 3), "on_grid_fraction": round(best, 2),
            "flat_fraction": round(flat, 2), "voiced_frames": int(len(c)), "tuning_offset_cents": round(bo, 0)}


# ------------------------------------------------------------------ dynamics (information only)
def dynamics(P):
    m, sr, act = P["m"], P["sr"], P["act"]
    n = int(0.4 * sr); k = len(m) // n
    e = 20 * np.log10(np.sqrt((m[: k * n].reshape(k, n) ** 2).mean(1)) + 1e-9)
    ac = np.repeat(act, int(HOP * sr))[: k * n].reshape(k, n).mean(1) > 0.6
    v = e[ac]
    if len(v) < 10:
        return {"swing_db": None}
    swing = float(np.percentile(v, 95) - np.percentile(v, 10))
    fr = m[: len(m) // 441 * 441].reshape(-1, 441)
    crest = float(20 * np.log10(np.abs(m).max() / (np.sqrt((m[np.repeat(act, 441)[: len(m)] if len(np.repeat(act, 441)) >= len(m) else slice(None)] ** 2).mean()) + 1e-12)))
    return {"swing_db": round(swing, 1), "crest_db": round(crest, 1), "already_compressed": bool(swing <= 5.0 and crest <= 11.0)}


# ------------------------------------------------------------------ public API
def analyze(voc, sr, bpm=None):
    x = np.asarray(voc)
    if x.size == 0 or x.shape[-1] < sr * 12:
        return {"verdict": "unknown", "reasons": ["clip shorter than 12 s: not enough to judge"], "reverb": {"confidence": 0.0}, "delay": {"confidence": 0.0},
                "stereo": {"confidence": 0.0}, "pitch": {"confidence": 0.0}, "dynamics": {}}
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
    if r.get("confidence", 0) >= REDUCE_AT:
        plan["reasons"].append("reverb already in the vocal (tail %.0f dB above floor, RT60 ~%s s, confidence %.2f)" % (r.get("tail_db") or 0, r.get("rt60_s"), r["confidence"]))
    if d.get("confidence", 0) >= REDUCE_AT:
        plan["reasons"].append("delay already in the vocal (~%s ms, confidence %.2f)" % (d.get("delay_ms"), d["confidence"]))
    if s.get("confidence", 0) >= BYPASS_AT:
        plan["skip_adt"] = True; plan["skip_widen"] = True
        plan["reasons"].append("vocal is already stereo / doubled (correlation %.2f)" % s.get("correlation", 1.0))
    if p.get("confidence", 0) >= BYPASS_AT:
        plan["skip_pitch_correct"] = True
        plan["reasons"].append("pitch already corrected (%.0f%% of notes on the semitone grid)" % (100 * p.get("on_grid_fraction", 0)))
    return plan
