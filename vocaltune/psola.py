"""TD-PSOLA pitch correction with fractional-sample grain placement.
Grains are cut around waveform-synchronous pitch marks and re-laid at the *target* spacing, so each
grain keeps its own spectral envelope (= formants stay put) and noise/breath/transients are not vocoded."""
from __future__ import annotations
import numpy as np
from . import dsp

def _runs(mask):
    d = np.diff(np.r_[0, mask.astype(np.int8), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))

def find_marks(x_mono, sr, f0_s, s0, s1):
    n = len(x_mono)
    pad = int(0.05 * sr)
    a, b = max(0, s0 - pad), min(n, s1 + pad)
    seg = x_mono[a:b]
    mid = f0_s(np.array([(s0 + s1) // 2]))[0]
    fc = float(np.clip(1.7 * mid, 260.0, 1300.0))
    xs = dsp.zero_phase(seg, dsp.butter_sos("lowpass", fc, sr, 2))
    pol = 1.0 if xs.max() >= -xs.min() else -1.0
    xs = pol * xs
    marks = []
    T0 = sr / f0_s(np.array([s0]))[0]
    lo = int(s0 - a); hi = int(min(len(xs), lo + T0))
    if hi <= lo + 2:
        return np.array([])
    pos = lo + int(np.argmax(xs[lo:hi]))
    marks.append(pos)
    end = s1 - a + 0.5 * T0
    while True:
        T = sr / f0_s(np.array([pos + a]))[0]
        cand = pos + T
        if cand > end or cand >= len(xs) - 3:
            break
        w = int(0.22 * T)
        l, h = int(cand) - w, int(cand) + w + 1
        if l < 1 or h >= len(xs) - 1:
            break
        idx = np.arange(l, h)
        score = xs[l:h] * (1.0 - 0.6 * ((idx - cand) / (w + 1e-9)) ** 2)
        pk = idx[int(np.argmax(score))]
        marks.append(pk)
        pos = pk
    m = np.array(marks, dtype=np.float64)
    mi = m.astype(int)
    ok = (mi > 0) & (mi < len(xs) - 1)
    y0, y1, y2 = xs[mi[ok] - 1], xs[mi[ok]], xs[mi[ok] + 1]
    den = y0 - 2 * y1 + y2
    d = np.where(np.abs(den) > 1e-12, 0.5 * (y0 - y2) / den, 0.0)
    m[ok] += np.clip(d, -0.5, 0.5)
    return m + a

def refine_marks(x, m, search_frac=0.12):
    m = m.copy()
    for k in range(1, len(m)):
        T = m[k] - m[k - 1]
        h = int(0.5 * T)
        W = max(1, int(search_frac * T))
        c0 = int(round(m[k - 1]))
        if c0 - h < 0 or int(m[k]) + W + h + 2 >= len(x):
            continue
        ref = x[c0 - h:c0 + h + 1] * np.hanning(2 * h + 1)
        base = int(round(m[k]))
        idx = (base - W - h + np.arange(2 * W + 1))[:, None] + np.arange(2 * h + 1)[None, :]
        if idx.min() < 0 or idx.max() >= len(x):
            continue
        cand = x[idx] * np.hanning(2 * h + 1)[None, :]
        num = cand @ ref
        den = np.sqrt((cand ** 2).sum(axis=1) * (ref ** 2).sum()) + 1e-12
        r = num / den
        j = int(np.argmax(r))
        d = 0.0
        if 0 < j < len(r) - 1:
            a, b, c = r[j - 1], r[j], r[j + 1]
            den2 = a - 2 * b + c
            d = 0.5 * (a - c) / den2 if abs(den2) > 1e-12 else 0.0
        m[k] = base + (j - W) + np.clip(d, -0.5, 0.5) - 0.0
    return m

def psola_correct(x, sr, f0, voiced, shift_cents, hop, formant_ratio=1.0, min_shift=2.0, return_diag=False, refine=True, oversample=8, mark_signal=None):
    X = x[:, None] if x.ndim == 1 else x
    mono = X.mean(axis=1) if mark_signal is None else np.asarray(mark_signal, dtype=np.float64)
    mono_ref = mono
    n = len(mono)
    nf = len(f0)
    logf = np.log2(np.maximum(f0, 1.0))
    good = f0 > 0
    logf_i = np.interp(np.arange(nf), np.where(good)[0], logf[good]) if good.any() else logf
    sh_i = shift_cents

    def f0_s(sidx):
        fr = np.clip(np.asarray(sidx, dtype=np.float64) / hop, 0, nf - 1)
        return 2.0 ** np.interp(fr, np.arange(nf), logf_i)

    def shift_s(sidx):
        fr = np.clip(np.asarray(sidx, dtype=np.float64) / hop, 0, nf - 1)
        return np.interp(fr, np.arange(nf), sh_i)

    out = X.copy()
    pmask = np.zeros(n)
    diag = {"runs": 0, "processed": 0, "skipped_bad_marks": 0, "skipped_small": 0}
    for fa, fb in _runs(voiced):
        diag["runs"] += 1
        if np.max(np.abs(shift_cents[fa:fb])) < min_shift:
            diag["skipped_small"] += 1
            continue
        s0, s1 = fa * hop, min(n, fb * hop)
        if (s1 - s0) < 0.03 * sr:
            continue
        m = find_marks(mono, sr, f0_s, s0, s1)
        if len(m) < 4:
            diag["skipped_bad_marks"] += 1
            continue
        m = refine_marks(mono_ref, m) if refine else m
        sp = np.diff(m)
        Texp = sr / f0_s(m[:-1])
        bad = np.mean(np.abs(sp / Texp - 1.0) > 0.30)
        if bad > 0.15:
            diag["skipped_bad_marks"] += 1
            continue
        Ta = np.empty(len(m)); Ta[1:-1] = 0.5 * (m[2:] - m[:-2]); Ta[0] = sp[0]; Ta[-1] = sp[-1]
        lo = int(max(0, np.floor(m[0] - Ta[0])))
        hi = int(min(n, np.ceil(m[-1] + Ta[-1])))
        L_out = hi - lo
        acc = np.zeros((L_out, X.shape[1])); wsum = np.zeros(L_out)
        s = m[0]; k = 0
        while s < m[-1]:
            while k + 1 < len(m) and abs(m[k + 1] - s) <= abs(m[k] - s):
                k += 1
            ratio = 2.0 ** (shift_s(s) / 1200.0)
            T_out = sr / (f0_s(s) * ratio)
            half = max(Ta[k], T_out) * 1.0
            n0 = int(np.ceil(s - half)); n1 = int(np.floor(s + half))
            n0c, n1c = max(n0, lo), min(n1, hi - 1)
            if n1c > n0c:
                idx = np.arange(n0c, n1c + 1)
                u = idx - s
                w = 0.5 * (1.0 + np.cos(np.pi * u / half))
                pos = m[k] + u * formant_ratio
                for ch in range(X.shape[1]):
                    g = dsp.cubic_sample(X[:, ch], pos)
                    acc[idx - lo, ch] += w * g
                wsum[idx - lo] += w
            s += T_out
        valid = wsum > 0.25
        y = np.where(valid[:, None], acc / np.maximum(wsum, 1e-6)[:, None], X[lo:hi])
        r = int(0.008 * sr)
        b = np.ones(L_out)
        b[:r] = dsp.smoothstep(np.arange(r), 0, r); b[-r:] = dsp.smoothstep(np.arange(r)[::-1], 0, r)
        b = b * valid
        out[lo:hi] = (1 - b)[:, None] * X[lo:hi] + b[:, None] * y
        pmask[lo:hi] = np.maximum(pmask[lo:hi], b)
        diag["processed"] += 1
    res = out[:, 0] if x.ndim == 1 else out
    diag['mask'] = pmask
    return (res, diag) if return_diag else res

def spectral_restore(orig, proc, sr, mask, max_db=3.5, nfft=4096):
    from scipy import signal
    X = orig[:, None] if orig.ndim == 1 else orig
    Y = proc[:, None] if proc.ndim == 1 else proc
    sel = mask > 0.99
    if sel.sum() < nfft * 4:
        return proc
    om, pm = X.mean(axis=1), Y.mean(axis=1)
    f, po = signal.welch(om[sel], sr, nperseg=nfft)
    _, pp = signal.welch(pm[sel], sr, nperseg=nfft)
    ratio_db = 10 * np.log10((po + 1e-20) / (pp + 1e-20))
    lf = np.log2(np.maximum(f, 20.0))
    sm = np.empty_like(ratio_db)
    for i in range(len(f)):
        w = np.exp(-0.5 * ((lf - lf[i]) / 0.18) ** 2)
        sm[i] = np.sum(w * ratio_db) / np.sum(w)
    sm = np.clip(sm, -max_db, max_db)
    sm[f < 80] = 0.0
    gain = 10 ** (sm / 20.0)
    nfir = 4096
    freqs = np.fft.rfftfreq(nfir, 1.0 / sr)
    G = np.interp(freqs, f, gain)
    h = np.fft.irfft(G, nfir)
    h = np.roll(h, nfir // 2)[1:] * np.hanning(nfir - 1)
    h = h / np.sum(h) * G[2:6].mean()
    Yf = np.stack([signal.fftconvolve(Y[:, c], h, mode="same") for c in range(Y.shape[1])], 1)
    mk = np.convolve(mask, np.hanning(int(0.010 * sr)) / np.hanning(int(0.010 * sr)).sum(), mode="same")[:, None]
    out = (1 - mk) * Y + mk * Yf
    return out[:, 0] if proc.ndim == 1 else out
