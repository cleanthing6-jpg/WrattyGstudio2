"""Tier-1 DSP: asymmetric exciter + LFO ADT doubler.
Numba-compiled, in-place where possible, polyphase oversampled.
Wired with live values (band 5-10k, taps 14/22ms, pan ±0.30, blend 0.22/0.08)."""
import numpy as np
from numba import njit


@njit(cache=True)
def _biquad_sat_inplace(src, b0, b1, b2, a1, a2, drive):
    w1 = 0.0; w2 = 0.0
    n = len(src)
    for s in range(n):
        cw = src[s] - a1 * w1 - a2 * w2
        y = b0 * cw + b1 * w1 + b2 * w2
        w2 = w1; w1 = cw
        d = y * drive
        src[s] = np.tanh(d * 1.2) if d > 0.0 else np.arctan(d * 0.8)


@njit(cache=True)
def _polyphase_up_core(src, out_2x, A0, A1):
    samples = len(src)
    c0 = c1 = c2 = 0.0
    for s in range(samples):
        v = src[s]
        oe = A0 * v + c0; c0 = v - A0 * oe
        out_2x[2*s] = oe
        o1 = A1 * v + c1; c1 = v - A1 * o1
        o2 = A0 * o1 + c2; c2 = o1 - A0 * o2
        out_2x[2*s + 1] = o2


@njit(cache=True)
def _polyphase_dn_core(src_2x, out_1x, A0, A1):
    n = len(out_1x)
    c0 = c1 = c2 = 0.0
    for s in range(n):
        ve = src_2x[2*s]
        oe = A0 * ve + c0; c0 = ve - A0 * oe
        vo = src_2x[2*s + 1]
        o1 = A1 * vo + c1; c1 = vo - A1 * o1
        o2 = A0 * o1 + c2; c2 = o1 - A0 * o2
        out_1x[s] = 0.5 * (oe + o2)


@njit(cache=True)
def _hermite_core(src, targets, out):
    n = len(src)
    for s in range(len(targets)):
        t = targets[s]
        i0 = int(t)
        f = t - i0
        im1 = 0 if i0 - 1 < 0 else i0 - 1
        i1 = i0 + 1
        i2 = n - 1 if i0 + 2 >= n else i0 + 2
        a0 = src[i0]
        a1 = 0.5 * (src[i1] - src[im1])
        a2 = src[im1] - 2.5 * src[i0] + 2.0 * src[i1] - 0.5 * src[i2]
        a3 = 0.5 * (src[i2] - src[im1]) + 1.5 * (src[i0] - src[i1])
        out[s] = ((a3 * f + a2) * f + a1) * f + a0


@njit(cache=True)
def _frame_filter_inplace(sig, alpha_hp, alpha_lp):
    n = len(sig)
    in_prev = 0.0; hp_prev = 0.0; lp_prev = 0.0
    for s in range(n):
        ci = sig[s]
        hp = alpha_hp * (hp_prev + ci - in_prev)
        in_prev = ci; hp_prev = hp
        lp = lp_prev + alpha_lp * (hp - lp_prev)
        lp_prev = lp
        sig[s] = lp


def exciter(x, sr, drive_db=8.0, blend=0.08):
    """Asymmetric band-limited exciter, live band 5-10k, live blend 0.08."""
    ch, n = x.shape
    A0, A1 = 0.12159005792425, 0.53696841243169
    is_mono = ch == 1 or np.array_equal(x[0], x[-1])

    buf = np.zeros(n * 2, dtype=np.float32)
    harm = np.zeros(n, dtype=np.float32)
    out = np.empty_like(x)

    sr2 = sr * 2.0
    drive = 10.0 ** (drive_db / 20.0)
    f0 = 7071.06          # geometric center of 5k and 10k
    w0 = 2.0 * np.pi * f0 / sr2
    cw, sw = np.cos(w0), np.sin(w0)
    Q = 0.707
    alpha = sw / (2.0 * Q)
    b0, b1, b2 = alpha, 0.0, -alpha
    a0, a1, a2 = 1.0 + alpha, -2.0 * cw, 1.0 - alpha
    b0, b1, b2 = b0/a0, b1/a0, b2/a0
    a1, a2 = a1/a0, a2/a0

    if is_mono:
        _polyphase_up_core(x[0], buf, A0, A1)
        _biquad_sat_inplace(buf, b0, b1, b2, a1, a2, drive)
        _polyphase_dn_core(buf, harm, A0, A1)
        for c in range(ch):
            out[c] = x[c] + harm * blend
    else:
        for c in range(ch):
            _polyphase_up_core(x[c], buf, A0, A1)
            _biquad_sat_inplace(buf, b0, b1, b2, a1, a2, drive)
            _polyphase_dn_core(buf, harm, A0, A1)
            out[c] = x[c] + harm * blend

    pk = float(np.max(np.abs(out)))
    if pk > 0.95:
        out *= 0.95 / pk
    return out


def adt_double(x, sr, depth_ms=14.0, rate_hz=0.5, right_offset_ms=8.0,
               pan=0.30, blend=0.22):
    """LFO-modulated ADT. Live taps 14/22 ms, live pan ±0.30, live blend 0.22."""
    ch, n = x.shape
    src = x[0]

    t = np.arange(n, dtype=np.float32) / np.float32(sr)
    base = np.float32(depth_ms / 1000.0 * sr)
    r_off = np.float32(right_offset_ms / 1000.0 * sr)
    mod = np.float32(3.5 / 1000.0 * sr)

    lfo_l = np.sin(2.0 * np.pi * rate_hz * t).astype(np.float32)
    lfo_r = np.cos(2.0 * np.pi * rate_hz * t).astype(np.float32)

    idx = np.arange(n, dtype=np.float32)
    lim = np.float32(n - 2.5)
    tg_l = np.clip(idx - (base + lfo_l * mod), 0.0, lim).astype(np.float32)
    tg_r = np.clip(idx - (base + r_off + lfo_r * mod), 0.0, lim).astype(np.float32)

    dl = np.empty(n, dtype=np.float32)
    dr = np.empty(n, dtype=np.float32)
    _hermite_core(src, tg_l, dl)
    _hermite_core(src, tg_r, dr)

    ahp = np.float32((1.0/(2.0*np.pi*150.0)) / ((1.0/(2.0*np.pi*150.0)) + (1.0/sr)))
    alp = np.float32((1.0/sr) / ((1.0/(2.0*np.pi*10000.0)) + (1.0/sr)))
    _frame_filter_inplace(dl, ahp, alp)
    _frame_filter_inplace(dr, ahp, alp)

    p_lL = np.float32(np.sqrt((1.0 + pan) / 2.0) * np.sqrt(2.0))
    p_lR = np.float32(np.sqrt((1.0 - pan) / 2.0) * np.sqrt(2.0))
    p_rL = np.float32(np.sqrt((1.0 - pan) / 2.0) * np.sqrt(2.0))
    p_rR = np.float32(np.sqrt((1.0 + pan) / 2.0) * np.sqrt(2.0))

    out = np.empty((2, n), dtype=np.float32)
    if ch == 1:
        out[0] = src + (dl * blend * p_lL) + (dr * blend * p_rL)
        out[1] = src + (dl * blend * p_lR) + (dr * blend * p_rR)
    else:
        out[0] = x[0] + (dl * blend * p_lL) + (dr * blend * p_rL)
        out[1] = x[1] + (dl * blend * p_lR) + (dr * blend * p_rR)

    pk = float(np.max(np.abs(out)))
    if pk > 0.95:
        out *= 0.95 / pk
    return out
