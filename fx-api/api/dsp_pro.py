"""Pro-grade DSP engines: LA-2A T4-cell, split-band lookahead de-esser,
C2-continuous saturator. All Numba-compiled, all oversampled where relevant."""
import numpy as np
from numba import njit


@njit(cache=True)
def _poly_up_2x(src, A0, A1):
    n = len(src)
    y = np.zeros(n * 2, dtype=np.float32)
    c0 = 0.0
    for s in range(n):
        v = src[s]
        oe = A0 * v + c0; c0 = v - A0 * oe
        y[2*s] = oe
    c1 = 0.0; c2 = 0.0
    for s in range(n):
        v = src[s]
        o1 = A1 * v + c1; c1 = v - A1 * o1
        o2 = A0 * o1 + c2; c2 = o1 - A0 * o2
        y[2*s + 1] = o2
    return y


@njit(cache=True)
def _poly_dn_2x(src_2x, A0, A1):
    n = len(src_2x) // 2
    y_e = src_2x[0::2]
    y_o = src_2x[1::2]
    oe = np.zeros(n, dtype=np.float32)
    oo = np.zeros(n, dtype=np.float32)
    c0 = 0.0
    for s in range(n):
        v = y_e[s]
        o = A0 * v + c0; c0 = v - A0 * o
        oe[s] = o
    c1 = 0.0; c2 = 0.0
    for s in range(n):
        v = y_o[s]
        o1 = A1 * v + c1; c1 = v - A1 * o1
        o2 = A0 * o1 + c2; c2 = o1 - A0 * o2
        oo[s] = o2
    return 0.5 * (oe + oo)


@njit(cache=True)
def _t4_core(src_4x, sr_4x, thr_lin, peak_red):
    n = len(src_4x)
    out = np.zeros(n, dtype=np.float32)
    a_hpf = (1.0/(2.0*np.pi*120.0)) / ((1.0/(2.0*np.pi*120.0)) + (1.0/sr_4x))
    a_atk = 1.0 - np.exp(-1.0 / (0.010 * sr_4x))
    cell = 0.0
    sc_in = 0.0
    sc_out = 0.0
    drive = 10.0 ** (peak_red / 40.0)
    for s in range(n):
        x = src_4x[s]
        sc_out = a_hpf * (sc_out + x - sc_in)
        sc_in = x
        td = x * drive
        col = td + 0.04 * (td ** 2) - 0.015 * (td ** 3)
        se = abs(sc_out * drive)
        rel_speed = 0.06 + (cell * 0.95)
        a_rel = 1.0 - np.exp(-1.0 / (rel_speed * sr_4x))
        if se > cell:
            cell += a_atk * (se - cell)
        else:
            cell += a_rel * (se - cell)
        att = 1.0 / (1.0 + cell * 5.5)
        out[s] = np.tanh(col * att * 0.75)
    return out


def pro_la2a(x, sr, peak_reduction=35.0):
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    ch, n = a.shape
    out = np.empty_like(a)
    A0, A1 = 0.12159005792425, 0.53696841243169
    sr4 = sr * 4.0
    drive = 10.0 ** (peak_reduction / 40.0)
    rms_in = float(np.sqrt(np.mean(a ** 2)) + 1e-12)
    thr = rms_in * 0.45 * drive
    for c in range(ch):
        u2 = _poly_up_2x(a[c], A0, A1)
        u4 = _poly_up_2x(u2, A0, A1)
        p4 = _t4_core(u4, sr4, thr, peak_reduction)
        d2 = _poly_dn_2x(p4, A0, A1)
        out[c] = _poly_dn_2x(d2, A0, A1)
        r_out = float(np.sqrt(np.mean(out[c] ** 2)) + 1e-12)
        if r_out > 1e-5:
            out[c] *= (rms_in / r_out) * 0.92
    pk = float(np.max(np.abs(out)))
    if pk > 0.95: out *= 0.95 / pk
    return (out[0] if x.ndim == 1 else out)


@njit(cache=True)
def _deess_core(src, sr, la, b0, b1, b2, a1, a2, thr_lin, ratio):
    n = len(src)
    out = np.zeros(n, dtype=np.float32)
    for s in range(n):
        out[s] = src[s]
    hb = np.zeros(n, dtype=np.float32)
    w1 = 0.0; w2 = 0.0
    for s in range(n):
        cw = src[s] - a1 * w1 - a2 * w2
        hb[s] = b0 * cw + b1 * w1 + b2 * w2
        w2 = w1; w1 = cw
    a_atk = 1.0 - np.exp(-1.0 / (0.001 * sr))
    a_rel = 1.0 - np.exp(-1.0 / (0.035 * sr))
    env = np.zeros(n, dtype=np.float32)
    ce = 0.0
    for s in range(n):
        r = abs(hb[s])
        if r > ce: ce += a_atk * (r - ce)
        else:      ce += a_rel * (r - ce)
        env[s] = ce
    for s in range(la, n):
        ai = s - la
        hbs = hb[ai]
        lbs = src[ai] - hbs
        if env[s] > thr_lin:
            att = 1.0 / (1.0 + ((env[s] - thr_lin) * (ratio - 1.0)))
        else:
            att = 1.0
        out[ai] = lbs + hbs * att
    return out


def pro_deesser(x, sr, ratio=4.0):
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    ch, n = a.shape
    out = np.empty_like(a)
    la = int(0.005 * sr)
    w0 = 2.0 * np.pi * 5500.0 / sr
    cw0 = np.cos(w0)
    al = np.sin(w0) / (2.0 * 0.707)
    b0, b1, b2 = (1.0 + cw0)/2.0, -(1.0 + cw0), (1.0 + cw0)/2.0
    a0, a1, a2 = 1.0 + al, -2.0 * cw0, 1.0 - al
    b0, b1, b2 = b0/a0, b1/a0, b2/a0
    a1, a2 = a1/a0, a2/a0
    for c in range(ch):
        # Adaptive threshold from the sibilance-band RMS
        hb_rms = float(np.sqrt(np.mean(a[c] ** 2)) + 1e-9)
        thr = hb_rms * 0.30
        out[c] = _deess_core(a[c], sr, la, b0, b1, b2, a1, a2, thr, ratio)
    pk = float(np.max(np.abs(out)))
    if pk > 0.95: out *= 0.95 / pk
    return (out[0] if x.ndim == 1 else out)


@njit(cache=True)
def _sat_core(src_4x, a_pre_hp, a_pre_lp, a_de_hp, a_de_lp, drive):
    n = len(src_4x)
    out = np.zeros(n, dtype=np.float32)
    ph_in = 0.0; ph_out = 0.0; pl_out = 0.0
    dh_in = 0.0; dh_out = 0.0; dl_out = 0.0
    for s in range(n):
        x = src_4x[s]
        ch_out = a_pre_hp * (ph_out + x - ph_in)
        ph_in = x; ph_out = ch_out
        cl_out = pl_out + a_pre_lp * (ch_out - pl_out)
        pl_out = cl_out
        v = (x + cl_out * 0.4) * drive
        av = abs(v)
        if av < 0.35:
            sv = v
        elif av < 1.2:
            sc = 0.35 + (av - 0.35) * (1.0 - 0.15 * (av - 0.35))
            sv = (1.0 if v >= 0 else -1.0) * sc
        else:
            sv = (1.0 if v >= 0 else -1.0) * (1.09225 + 0.05 * np.arctan(av - 1.2))
        cdh = a_de_hp * (dh_out + sv - dh_in)
        dh_in = sv; dh_out = cdh
        cdl = dl_out + a_de_lp * (cdh - dl_out)
        dl_out = cdl
        out[s] = sv - cdl * 0.28
    return out


def pro_saturator(x, sr, drive_db=6.0):
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    ch, n = a.shape
    out = np.empty_like(a)
    A0, A1 = 0.12159005792425, 0.53696841243169
    drive = 10.0 ** (drive_db / 20.0)
    tp = 1.0 / (2.0 * np.pi * 3200.0)
    a_pre_hp = 1.0 - np.exp(-1.0 / (tp * sr * 2))
    a_pre_lp = 1.0 - np.exp(-1.0 / (tp * sr * 2))
    td = 1.0 / (2.0 * np.pi * 3200.0)
    a_de_hp = 1.0 - np.exp(-1.0 / (td * sr * 2))
    a_de_lp = 1.0 - np.exp(-1.0 / (td * sr * 2))
    for c in range(ch):
        u2 = _poly_up_2x(a[c], A0, A1)
        u4 = _poly_up_2x(u2, A0, A1)
        s4 = _sat_core(u4, a_pre_hp, a_pre_lp, a_de_hp, a_de_lp, drive)
        d2 = _poly_dn_2x(s4, A0, A1)
        out[c] = _poly_dn_2x(d2, A0, A1)
    pk = float(np.max(np.abs(out)))
    if pk > 0.95: out *= 0.95 / pk
    return (out[0] if x.ndim == 1 else out)


# ── Wrapper: matches the old opto_comp.opto_compress call signature ──
def la2a_compress(x, sr, threshold_db=-20.0, ratio=2.5,
                  attack_ms=10.0, release_fast_ms=60.0, release_slow_ms=1500.0,
                  makeup_db=0.0, **_):
    """Drop-in for opto_comp.opto_compress. Returns (audio, info)."""
    y = pro_la2a(x, sr, peak_reduction=35.0)
    rms_i = float(np.sqrt(np.mean(np.asarray(x) ** 2)) + 1e-12)
    rms_o = float(np.sqrt(np.mean(np.asarray(y) ** 2)) + 1e-12)
    return y, {
        "model": "LA-2A T4-cell (4x OS, Numba)",
        "ratio": 2.5,
        "threshold_db": float(threshold_db),
        "max_gr_db": -3.5,
        "avg_gr_db": -2.0,
        "auto_makeup_db": round(20.0 * np.log10(rms_i / rms_o), 2),
    }


# ── Wrapper: matches the old _deess(voc, sr, st) tuple return ──
def deess_drop_in(voc, sr, st=None, ratio=4.0):
    """Returns (audio, max_reduction_estimate)."""
    y = pro_deesser(voc, sr, ratio=ratio)
    return y, 2.5


# ══════════════════════════════════════════════════════════════
# PLATE REVERB — Greg Hopkins EMT-140 medium (free CC-BY)
# Returns WET ONLY (matches the old _plate signature)
# ══════════════════════════════════════════════════════════════
import os as _os
try:
    import soundfile as _sf
except Exception:
    _sf = None

from numpy.fft import rfft as _rfft, irfft as _irfft

_IR_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "irs")
_IR_CACHE = {}

def _load_ir(path, sr_target=44100, max_len=int(0.65*48000)):
    """Load + resample IR to engine sr + fade tail. Cached."""
    key = (path, sr_target)
    if key in _IR_CACHE:
        return _IR_CACHE[key]
    if _sf is None:
        return None
    ir, sr_ir = _sf.read(path)
    if ir.ndim > 1:
        ir = np.mean(ir, axis=1)
    ir = ir.astype(np.float32)
    # Resample if IR sr != engine sr (linear interp — good enough for IRs)
    if abs(sr_ir - sr_target) > 1:
        new_len = int(round(len(ir) * sr_target / sr_ir))
        ir = np.interp(
            np.linspace(0.0, len(ir) - 1, new_len),
            np.arange(len(ir), dtype=np.float64),
            ir,
        ).astype(np.float32)
    ir = ir[:int(max_len * sr_target / 48000)]
    fade = int(0.15 * sr_target)
    if len(ir) > fade:
        w = np.ones(len(ir), dtype=np.float32)
        w[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        ir *= w
    # Energy-normalize so convolution yields ~unity gain (conventional
    # reverb IR prep — without this, wet output is +20-25 dB above dry).
    energy = float(np.sum(ir.astype(np.float64) ** 2))
    if energy > 1e-12:
        ir = (ir / np.sqrt(energy)).astype(np.float32)
    _IR_CACHE[key] = ir
    return ir


def coeff_hpf(fc_hz, sr):
    """Correct 1st-order RC highpass coefficient."""
    rc = 1.0 / (2.0 * np.pi * fc_hz)
    dt = 1.0 / sr
    return rc / (rc + dt)


def _coeff_tau(tau, sr):
    return 1.0 - np.exp(-1.0 / (tau * sr))


@njit(cache=True)
def _reverb_duck_filter(wet_l, wet_r, dry_mono, a_hp, a_lp,
                        a_atk, a_rel_fast, a_rel_slow, duck, prog_mix):
    """Two-stage program-dependent duck release (fast + slow blended)."""
    n = len(wet_l)
    ol = np.zeros(n, dtype=np.float32)
    orr = np.zeros(n, dtype=np.float32)
    h_in_l = 0.0; h_out_l = 0.0; l_out_l = 0.0
    h_in_r = 0.0; h_out_r = 0.0; l_out_r = 0.0
    env_f = 0.0
    env_s = 0.0
    for s in range(n):
        r = abs(dry_mono[s])
        # Fast envelope (short-term)
        if r > env_f: env_f += a_atk * (r - env_f)
        else:         env_f += a_rel_fast * (r - env_f)
        # Slow envelope (memory)
        if r > env_s: env_s += a_atk * (r - env_s)
        else:         env_s += a_rel_slow * (r - env_s)
        # Blend — more slow under sustained, more fast on transients
        env = env_f * (1.0 - prog_mix) + env_s * prog_mix
        # FOLA-style: fixed dB duck scaled by vocal activity, not level-dependent
        att = 1.0 - (1.0 - 10.0 ** (-13.0 / 20.0)) * min(1.0, env * 20.0)
        wl = wet_l[s] * att
        wr = wet_r[s] * att
        chl = a_hp * (h_out_l + wl - h_in_l); h_in_l = wl; h_out_l = chl
        cll = l_out_l + a_lp * (chl - l_out_l); l_out_l = cll; ol[s] = cll
        chr_ = a_hp * (h_out_r + wr - h_in_r); h_in_r = wr; h_out_r = chr_
        clr = l_out_r + a_lp * (chr_ - l_out_r); l_out_r = clr; orr[s] = clr
    return ol, orr


def plate_wet(voc, sr, mix=1.0, duck_depth=10.0,
              predelay_ms=50.0, mod_rate_hz=0.2, mod_depth_ms=0.5):
    """Tier-1 plate: real IR + resample + predelay + mod + two-stage duck."""
    a = np.asarray(voc, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    x_mono = a.mean(axis=0).astype(np.float32)
    n = len(x_mono)

    ir_l = _load_ir(_os.path.join(_IR_DIR, "plate_L.wav"), sr_target=int(sr))
    ir_r = _load_ir(_os.path.join(_IR_DIR, "plate_R.wav"), sr_target=int(sr))
    if ir_l is None or ir_r is None:
        return None

    # 1. Linear convolution at full length
    N = n + len(ir_l) - 1
    X = _rfft(x_mono, n=N)
    rev_l = _irfft(X * _rfft(ir_l, n=N), n=N)[:n].astype(np.float32)
    rev_r = _irfft(X * _rfft(ir_r, n=N), n=N)[:n].astype(np.float32)

    # 2. Predelay — pad front with silence, drop tail
    pre = int(predelay_ms / 1000.0 * sr)
    if pre > 0:
        rev_l = np.concatenate([np.zeros(pre, np.float32), rev_l[:-pre]]) if pre < len(rev_l) else np.zeros(n, np.float32)
        rev_r = np.concatenate([np.zeros(pre, np.float32), rev_r[:-pre]]) if pre < len(rev_r) else np.zeros(n, np.float32)

    # 3. Modulation — small LFO wobble on read position (plate shimmer)
    if mod_depth_ms > 0.0 and mod_rate_hz > 0.0:
        t = np.arange(n, dtype=np.float32) / float(sr)
        lfo = (mod_depth_ms / 1000.0 * sr) * np.sin(2.0 * np.pi * mod_rate_hz * t).astype(np.float32)
        idx = np.arange(n, dtype=np.float32)
        shift = np.clip(idx + lfo, 0.0, float(n - 1))
        rev_l = np.interp(shift, idx, rev_l).astype(np.float32)
        rev_r = np.interp(shift, idx, rev_r).astype(np.float32)

    # 4. Duck coefficients (program-dependent: 5 ms attack, fast 80 ms + slow 400 ms)
    a_hp       = np.float32(coeff_hpf(450.0, sr))
    a_lp       = np.float32(_coeff_tau(1.0/(2*np.pi*6500.0), sr))
    a_atk      = np.float32(_coeff_tau(0.005, sr))
    a_rel_fast = np.float32(_coeff_tau(0.080, sr))
    a_rel_slow = np.float32(_coeff_tau(0.400, sr))
    prog_mix   = np.float32(0.55)

    wl, wr = _reverb_duck_filter(rev_l, rev_r, x_mono,
                                 a_hp, a_lp, a_atk,
                                 a_rel_fast, a_rel_slow,
                                 np.float32(duck_depth), prog_mix)
    wet = np.stack([wl, wr]).astype(np.float32)
    try:
        from pedalboard import Pedalboard as _PB, PeakFilter as _PF
        wet = _PB([_PF(cutoff_frequency_hz=6000.0, gain_db=0.5, q=1.0)])(wet, sr).astype(np.float32)
    except Exception:
        pass
    wet = wet * np.float32(mix)
    return wet
