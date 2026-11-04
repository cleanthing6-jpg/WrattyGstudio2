"""
song_sections.py -- adaptive section awareness (intro / verse / chorus / bridge / outro).
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

MIN_BARS = 24
MIN_CONFIDENCE = 0.5
CTRL_RATE = 100.0
MAX_VOCAL_DB = 1.5
MAX_SEND_DB = 2.0
BAND_EDGES = np.geomspace(40, 12000, 17)
CHROMA_BINS = 12

def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=0) if x.ndim == 2 else x

def _stft_pow(x, sr, n=2048, hop=512):
    f, t, S = sg.stft(x, sr, nperseg=n, noverlap=n - hop, window="hann", boundary=None, padded=False)
    return f, t, np.abs(S) ** 2

def _band_db(f, P):
    out = np.zeros((len(BAND_EDGES) - 1, P.shape[1]))
    for i in range(len(BAND_EDGES) - 1):
        out[i] = P[(f >= BAND_EDGES[i]) & (f < BAND_EDGES[i + 1])].sum(0)
    return 10 * np.log10(out + 1e-12)

def _onset_env(P_db_bands):
    d = np.maximum(np.diff(P_db_bands, axis=1, prepend=P_db_bands[:, :1]), 0).sum(0)
    return d

def estimate_tempo(env, frame_s):
    e = env - ndimage.uniform_filter1d(env, int(2.0 / frame_s))
    ac = sg.correlate(e, e, mode="full", method="fft")[len(e) - 1:]
    lags = np.arange(len(ac))
    sel = (lags >= int(0.3 / frame_s)) & (lags <= int(1.0 / frame_s))
    k = lags[sel][np.argmax(ac[sel])]
    return 60.0 / (k * frame_s)

def downbeat_phase(env, frame_s, bar_s):
    nb = int(len(env) * frame_s / bar_s) - 1
    cands = np.arange(0.0, bar_s, 0.01); scores = np.zeros(len(cands))
    for j, cand in enumerate(cands):
        idx = ((cand + np.arange(nb) * bar_s) / frame_s).astype(int)
        scores[j] = env[idx[idx < len(env)]].sum()
    top = scores.max()
    near = cands[scores >= 0.93 * top]
    thr = np.percentile(env[env > 0], 90) if (env > 0).any() else 0.0
    first = np.argmax(env > thr) * frame_s
    ph0 = first % bar_s
    d = np.minimum(np.abs(near - ph0), bar_s - np.abs(near - ph0))
    return float(near[np.argmin(d)])

def _bar_features(beat, voc, sr, bpm):
    hop = 512; frame_s = hop / sr
    fb, tb, Pb = _stft_pow(_mono(beat), sr)
    fv, tv, Pv = _stft_pow(_mono(voc), sr)
    n = min(Pb.shape[1], Pv.shape[1]); Pb, Pv, tb = Pb[:, :n], Pv[:, :n], tb[:n]
    Bb = _band_db(fb, Pb)
    env = _onset_env(Bb)
    if bpm is None or not (50 <= bpm <= 210):
        bpm = estimate_tempo(env, frame_s)
        while bpm < 70: bpm *= 2
        while bpm > 150: bpm /= 2
    bar_s = 4 * 60.0 / bpm
    phase = downbeat_phase(env, frame_s, bar_s)
    nbar = int((n * frame_s - phase) / bar_s)
    Vv = _band_db(fv, Pv)
    vrms = 10 * np.log10(Pv.sum(0) + 1e-12)
    vact = vrms > (np.percentile(vrms, 95) - 35.0)
    sel = (fv >= 90) & (fv <= 1000)
    pc = np.round(12 * np.log2(np.maximum(fv, 1.0) / 440.0) + 69).astype(int) % 12
    cent = (fv[:, None] * Pv).sum(0) / (Pv.sum(0) + 1e-12)
    feats = {"beat_timbre": [], "beat_rms": [], "beat_density": [], "voc_rms": [], "voc_act": [],
             "voc_cent": [], "voc_chroma": [], "voc_rate": []}
    venv = _onset_env(Vv)
    for b in range(nbar):
        a = int((phase + b * bar_s) / frame_s); z = int((phase + (b + 1) * bar_s) / frame_s)
        z = min(max(z, a + 2), n)
        feats["beat_timbre"].append(Bb[:, a:z].mean(1))
        feats["beat_rms"].append(10 * np.log10(Pb[:, a:z].sum(0).mean() + 1e-12))
        feats["beat_density"].append(float((env[a:z] > np.percentile(env, 75)).mean()))
        act = vact[a:z]
        feats["voc_act"].append(float(act.mean()))
        if act.sum() >= 3:
            feats["voc_rms"].append(float(vrms[a:z][act].mean()))
            feats["voc_cent"].append(float(np.log2(cent[a:z][act].mean() + 1.0)))
            ch = np.zeros(12)
            for k in range(12):
                ch[k] = Pv[sel & (pc == k)][:, a:z][:, act].sum()
            feats["voc_chroma"].append(ch / (ch.sum() + 1e-12))
            feats["voc_rate"].append(float((venv[a:z] > np.percentile(venv, 85)).mean()))
        else:
            feats["voc_rms"].append(np.nan); feats["voc_cent"].append(np.nan)
            feats["voc_chroma"].append(np.zeros(12)); feats["voc_rate"].append(0.0)
    out = {k: np.array(v) for k, v in feats.items()}
    out.update(bpm=float(bpm), bar_s=float(bar_s), phase=float(phase), nbar=int(nbar))
    return out

def _z(x):
    x = np.array(x, dtype=float)
    ok = np.isfinite(x)
    if ok.sum() < 3:
        return np.zeros_like(x)
    m, s = x[ok].mean(), x[ok].std() + 1e-9
    z = (x - m) / s
    z[~ok] = 0.0
    return z

def _feature_matrix(F):
    tim = F["beat_timbre"] - F["beat_timbre"].mean(0)
    tim = tim / (tim.std(0, keepdims=True) + 1e-6)
    tim = tim / np.sqrt(tim.shape[1])
    cols = [0.9 * tim, 0.6 * _z(F["beat_rms"])[:, None], 0.4 * _z(F["beat_density"])[:, None],
            0.7 * _z(F["voc_rms"])[:, None], 0.8 * _z(F["voc_act"])[:, None], 0.5 * _z(F["voc_cent"])[:, None],
            0.6 * _z(F["voc_rate"])[:, None]]
    ch = F["voc_chroma"]
    cols.append(0.9 * (ch - ch.mean(0)) / (ch.std(0) + 1e-6) / np.sqrt(12))
    return np.hstack(cols)

def _ssm(X):
    Xn = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    S = Xn @ Xn.T
    return S

def _novelty(S, K=4):
    n = S.shape[0]
    g = np.exp(-0.5 * (np.arange(-K, K) + 0.5) ** 2 / (K / 2.0) ** 2)
    sign = np.sign(np.arange(-K, K) + 0.5)
    Kern = np.outer(sign * g, sign * g)
    pad = np.pad(S, K, mode="edge")
    nov = np.zeros(n)
    for i in range(n):
        nov[i] = (pad[i: i + 2 * K, i: i + 2 * K] * Kern).sum()
    return nov

def _boundaries(S, min_len=4):
    nov = _novelty(S, 4)
    nov = ndimage.gaussian_filter1d(nov, 0.6)
    thr = nov.mean() + 0.35 * nov.std()
    p, _ = sg.find_peaks(nov, height=thr, distance=min_len)
    b = [0] + [int(x) for x in p if min_len <= x <= S.shape[0] - min_len] + [S.shape[0]]
    return sorted(set(b)), nov

def _merge_short(b, X, min_len=4):
    changed = True
    while changed and len(b) > 2:
        changed = False
        for i in range(len(b) - 1):
            if b[i + 1] - b[i] < min_len:
                if i == 0: del b[1]
                elif i == len(b) - 2: del b[i]
                else:
                    sl = X[b[i - 1]:b[i]].mean(0); sr_ = X[b[i + 1]:b[i + 2]].mean(0); me = X[b[i]:b[i + 1]].mean(0)
                    cs = lambda a, c: a @ c / (np.linalg.norm(a) * np.linalg.norm(c) + 1e-9)
                    j = i if cs(me, sl) >= cs(me, sr_) else i + 1
                    del b[j]
                changed = True
                break
    return b

def _group(segvecs, thr=0.55):
    gid = []; protos = []
    cs = lambda a, c: float(a @ c / (np.linalg.norm(a) * np.linalg.norm(c) + 1e-9))
    for v in segvecs:
        best, bi = -1.0, -1
        for i, p in enumerate(protos):
            s = cs(v, p)
            if s > best: best, bi = s, i
        if best >= thr: gid.append(bi)
        else: protos.append(v); gid.append(len(protos) - 1)
    return np.array(gid)

def analyze(beat, voc, sr, bpm=None):
    res = {"sections": [], "confidence": 0.0, "strength": 0.0, "reason": "", "bars": 0}
    b = np.asarray(beat); v = np.asarray(voc)
    if b.size == 0 or v.size == 0 or b.shape[-1] < sr * 30:
        res["reason"] = "too short"; return res
    try:
        F = _bar_features(beat, voc, sr, bpm)
    except Exception as e:
        res["reason"] = "feature extraction failed: %s" % str(e)[:60]; return res
    nb = F["nbar"]; res.update(bpm=round(F["bpm"], 1), bars=nb)
    if nb < MIN_BARS:
        res["reason"] = "only %d bars (need %d)" % (nb, MIN_BARS); return res
    if (F["voc_act"] > 0.25).mean() < 0.25:
        res["reason"] = "vocal is active in too few bars"; return res
    X = _feature_matrix(F)
    S = _ssm(X)
    bnd, nov = _boundaries(S)
    bnd = _merge_short(bnd, X)
    segs = [(bnd[i], bnd[i + 1]) for i in range(len(bnd) - 1)]
    inten = 0.35 * _z(F["beat_rms"]) + 0.15 * _z(F["beat_density"]) + 0.30 * _z(F["voc_rms"]) + 0.20 * _z(F["voc_cent"])
    inten = ndimage.uniform_filter1d(inten, 2)
    segvec = np.array([X[a:z].mean(0) for a, z in segs])
    gid = _group(segvec)
    sact = np.array([F["voc_act"][a:z].mean() for a, z in segs])
    sint = np.array([inten[a:z].mean() for a, z in segs])
    counts = np.bincount(gid, minlength=gid.max() + 1)
    labels = ["verse"] * len(segs)
    for i, (a, z) in enumerate(segs):
        if sact[i] < 0.2: labels[i] = "break"
    if sact[0] < 0.25 or segs[0][1] <= 12 and sact[0] < 0.4: labels[0] = "intro"
    if len(segs) > 1 and (sact[-1] < 0.25): labels[-1] = "outro"
    cand = [g for g in range(len(counts)) if counts[g] >= 2 and np.mean([sact[i] for i in range(len(segs)) if gid[i] == g]) > 0.4]
    if cand:
        chorus_g = max(cand, key=lambda g: np.mean([sint[i] for i in range(len(segs)) if gid[i] == g]))
        for i in range(len(segs)):
            if gid[i] == chorus_g and labels[i] == "verse": labels[i] = "chorus"
    for i in range(len(segs)):
        if labels[i] == "verse" and counts[gid[i]] == 1 and i > len(segs) // 2 and 0 < i < len(segs) - 1 and sint[i] < np.median(sint):
            labels[i] = "bridge"
    inside = np.mean([S[a:z, a:z].mean() for a, z in segs]) if segs else 0.0
    mask = np.ones_like(S, bool)
    for a, z in segs: mask[a:z, a:z] = False
    between = S[mask].mean() if mask.any() else 0.0
    contrast = float(inside - between)
    c_struct = float(np.clip((contrast - 0.08) / 0.30, 0, 1))
    c_len = float(np.clip((len(segs) - 2) / 3.0, 0, 1)) * float(np.clip((nb - MIN_BARS + 8) / 24.0, 0, 1))
    c_rep = 1.0 if cand else 0.0
    c_voc = float(np.clip(((F["voc_act"] > 0.25).mean() - 0.2) / 0.3, 0, 1))
    conf = float((c_struct * c_len * max(c_rep, 0.05) * c_voc) ** 0.25)
    res.update(confidence=round(conf, 3), parts={"structure": round(c_struct, 2), "segments": round(c_len, 2), "repeats": c_rep, "vocal": round(c_voc, 2)}, contrast=round(contrast, 3))
    bs = F["bar_s"]; ph = F["phase"]
    res["sections"] = [{"label": labels[i], "start_s": round(ph + a * bs, 2), "end_s": round(ph + z * bs, 2), "bars": int(z - a), "group": int(gid[i]), "vocal_activity": round(float(sact[i]), 2), "intensity": round(float(sint[i]), 2)} for i, (a, z) in enumerate(segs)]
    res["_internal"] = {"bar_s": bs, "phase": ph, "labels": labels, "segs": segs, "intensity": inten, "nbar": nb}
    if conf < MIN_CONFIDENCE:
        res["reason"] = "structure not clear enough (confidence %.2f): neutral curves" % conf
        res["strength"] = 0.0
    else:
        res["strength"] = float(np.clip((conf - MIN_CONFIDENCE) / 0.3, 0, 1))
        res["reason"] = "sections detected"
    return res

LIFT = {"chorus": (+1.0, +1.5, +1.5, +0.06), "verse": (0.0, -1.0, -1.0, -0.03), "bridge": (-0.3, +0.5, 0.0, 0.0), "intro": (0.0, +1.0, 0.0, 0.0), "outro": (0.0, +1.0, 0.0, 0.0), "break": (0.0, +0.5, 0.0, 0.0)}

def control_curves(res, n_samples, sr):
    n = int(np.ceil(n_samples / sr * CTRL_RATE)) + 1
    zero = lambda: np.zeros(n)
    out = {"rate": CTRL_RATE, "vocal_db": zero(), "send_db": zero(), "double_db": zero(), "width": zero(), "strength": res.get("strength", 0.0)}
    if res.get("strength", 0.0) <= 0 or "_internal" not in res:
        return out
    I = res["_internal"]; bs, ph = I["bar_s"], I["phase"]
    t = np.arange(n) / CTRL_RATE
    cont = np.interp(t, ph + (np.arange(I["nbar"]) + 0.5) * bs, I["intensity"])
    vals = {k: np.zeros(n) for k in ("vocal_db", "send_db", "double_db", "width")}
    for lab, (a, z) in zip(I["labels"], I["segs"]):
        m = ((t >= ph + a * bs) & (t < ph + z * bs)).astype(float)
        for key, val in zip(("vocal_db", "send_db", "double_db", "width"), LIFT[lab]):
            vals[key] += m * val
    xf = int(round(bs * CTRL_RATE))
    for k in vals:
        v = ndimage.gaussian_filter1d(vals[k], xf / 2.5)
        if k == "vocal_db":
            v = v + 0.35 * np.clip(ndimage.gaussian_filter1d(cont, xf / 4.0), -1.5, 1.5)
        out[k] = v * res["strength"]
    out["vocal_db"] = np.clip(out["vocal_db"], -MAX_VOCAL_DB, MAX_VOCAL_DB)
    out["send_db"] = np.clip(out["send_db"], -MAX_SEND_DB, MAX_SEND_DB)
    out["double_db"] = np.clip(out["double_db"], -MAX_SEND_DB, MAX_SEND_DB)
    out["width"] = np.clip(out["width"], -0.08, 0.08)
    return out

def apply_gain_db(x, sr, curve_db, rate=CTRL_RATE):
    a = np.asarray(x)
    n = a.shape[-1]
    g = 10 ** (np.interp(np.arange(n) / sr, np.arange(len(curve_db)) / rate, curve_db) / 20.0)
    return (a * g).astype(a.dtype if np.issubdtype(a.dtype, np.floating) else np.float32)
