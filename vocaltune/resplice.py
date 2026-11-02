"""Resample + cycle-splice pitch correction (classic time-domain method).
The voiced signal is read back at a time-varying rate r(t)=2^(shift/1200): that moves the pitch with NO overlap-add,
so noise, breath and HF detail keep their natural texture."""
from __future__ import annotations
import numpy as np
from scipy import signal
from . import dsp

def _runs(mask):
    d = np.diff(np.r_[0, mask.astype(np.int8), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))

def _best_period(ref_sig, c, T0, sgn, lo_f=0.85, hi_f=1.15):
    n = len(ref_sig)
    Lw = int(max(8, T0))
    cands = np.arange(int(lo_f * T0), int(hi_f * T0) + 2)
    base = int(c)
    if base < 0 or base + Lw >= n:
        return T0
    ref = ref_sig[base:base + Lw] * np.hanning(Lw)
    starts = base - sgn * cands
    ok = (starts >= 0) & (starts + Lw < n)
    if ok.sum() < 3:
        return T0
    cands, starts = cands[ok], starts[ok]
    idx = starts[:, None] + np.arange(Lw)[None, :]
    seg = ref_sig[idx] * np.hanning(Lw)[None, :]
    r = (seg @ ref) / (np.sqrt((seg ** 2).sum(axis=1) * (ref ** 2).sum()) + 1e-12)
    j = int(np.argmax(r))
    d = 0.0
    if 0 < j < len(r) - 1:
        a, b, c3 = r[j - 1], r[j], r[j + 1]
        den = a - 2 * b + c3
        d = 0.5 * (a - c3) / den if abs(den) > 1e-12 else 0.0
    return float(cands[j] + np.clip(d, -0.5, 0.5))

def resplice_run(Xo, mono, sr, s0, s1, ratio, T_of, os=4):
    n_out = s1 - s0
    out = np.zeros((n_out, Xo.shape[1]))
    def read(pos):
        return np.stack([dsp.cubic_sample(Xo[:, c], pos * os) for c in range(Xo.shape[1])], 1)
    i = 0
    p = float(s0)
    nsplice = 0
    while i < n_out:
        r_rem = ratio[i:]
        inc = np.cumsum(r_rem) - r_rem
        pos = p + inc
        drift = pos - (s0 + i + np.arange(n_out - i))
        thr = 0.5 * T_of(s0 + i + np.arange(n_out - i))
        hit = np.abs(drift) > thr
        j = int(np.argmax(hit)) if hit.any() else n_out - i
        out[i:i + j] = read(pos[:j])
        if not hit.any():
            break
        sgn = 1 if drift[j] > 0 else -1
        T0 = float(T_of(s0 + i + j))
        Tp = _best_period(mono, pos[j], T0, sgn)
        L = int(min(max(Tp, 0.004 * sr), n_out - (i + j)))
        r_x = ratio[i + j:i + j + L]
        p_old = pos[j] + (np.cumsum(r_x) - r_x)
        p_new = p_old - sgn * Tp
        w = 0.5 - 0.5 * np.cos(np.pi * (np.arange(L) + 0.5) / L)
        out[i + j:i + j + L] = (1 - w)[:, None] * read(p_old) + w[:, None] * read(p_new)
        p = p_old[-1] + r_x[-1] - sgn * Tp
        i = i + j + L
        nsplice += 1
    return out, nsplice

def resplice_correct(x, sr, f0, voiced, shift_cents, hop, min_shift=2.0, return_diag=False, mark_signal=None, os=4):
    X = x[:, None] if x.ndim == 1 else x
    mono = X.mean(axis=1) if mark_signal is None else np.asarray(mark_signal, dtype=np.float64)
    n = len(X); nf = len(f0)
    good = f0 > 0
    logf_i = np.interp(np.arange(nf), np.where(good)[0], np.log2(np.maximum(f0, 1)[good])) if good.any() else np.zeros(nf)
    T_of = lambda s: sr / (2.0 ** np.interp(np.clip(np.asarray(s, dtype=np.float64) / hop, 0, nf - 1), np.arange(nf), logf_i))
    out = X.copy(); pmask = np.zeros(n)
    diag = {"runs": 0, "processed": 0, "skipped_small": 0, "splices": 0}
    for fa, fb in _runs(voiced):
        diag["runs"] += 1
        if np.max(np.abs(shift_cents[fa:fb])) < min_shift:
            diag["skipped_small"] += 1; continue
        s0, s1 = fa * hop, min(n, fb * hop)
        if s1 - s0 < 0.03 * sr:
            continue
        m = int(0.08 * sr)
        lo, hi = max(0, s0 - m), min(n, s1 + m)
        seg = X[lo:hi]
        Xo = np.stack([signal.resample_poly(seg[:, c], os, 1) for c in range(seg.shape[1])], 1)
        sh = np.interp(np.arange(s0, s1) / hop, np.arange(nf), shift_cents)
        ratio = 2.0 ** (sh / 1200.0)
        Tl = lambda s: T_of(np.asarray(s) + lo)
        y, ns = resplice_run(Xo, mono[lo:hi], sr, s0 - lo, s1 - lo, ratio, Tl, os)
        r = int(0.010 * sr)
        b = np.ones(s1 - s0); r = min(r, (s1 - s0) // 2)
        b[:r] = dsp.smoothstep(np.arange(r), 0, r); b[-r:] = dsp.smoothstep(np.arange(r)[::-1], 0, r)
        out[s0:s1] = (1 - b)[:, None] * X[s0:s1] + b[:, None] * y
        pmask[s0:s1] = np.maximum(pmask[s0:s1], b)
        diag["processed"] += 1; diag["splices"] += ns
    diag["mask"] = pmask
    res = out[:, 0] if x.ndim == 1 else out
    return (res, diag) if return_diag else res
