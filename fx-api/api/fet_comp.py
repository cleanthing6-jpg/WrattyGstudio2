"""UREI 1176LN Rev D — FET compressor emulation.

Models the actual signal path of a UREI 1176LN, not just its settings:

  1. FEEDBACK topology — the sidechain detects the OUTPUT (y[n-1]), not the
     input. This is the single biggest tonal difference from every
     feed-forward compressor plugin. It's why the 1176 sounds "grabby and
     fast" instead of "smooth and telegraphed."
  2. FET gain cell — near-instant attack (20 µs – 800 µs, per hardware).
     At 44.1 kHz a 20 µs attack is effectively one sample, so transients
     are caught before they can pass.
  3. Hard-knee gain computer with switchable ratios: 4:1, 8:1, 12:1, 20:1.
     "British mode" (all buttons in) stacks to ~20:1 with a wider knee.
  4. Input transformer rolloff on the SIDECHAIN only (~90 Hz HPF), matching
     modern reissue practice — audio path stays flat.
  5. Class A output stage: subtle asymmetric soft-clip, adds the FET's
     signature odd+even harmonic color under heavy GR.
  6. Stereo channels share a single linked detector — perfect imaging.

Attack is inherently faster than the LA-2A's, which is why the two work as
a pair: 1176 catches peaks, LA-2A glues the body.
"""
import numpy as np


def _db_to_lin(db):
    return 10.0 ** (db / 20.0)


def _lin_to_db(lin):
    return 20.0 * np.log10(np.maximum(lin, 1e-12))


def fet_compress(x, sr,
                 threshold_db=-20.0,
                 ratio=4.0,
                 attack_ms=0.100,       # 100 µs — mid hardware setting
                 release_ms=250.0,
                 input_gain_db=0.0,
                 makeup_db=0.0,
                 sidechain_hpf_hz=90.0,
                 sat_drive=0.10,
                 british_mode=False):
    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 1:
        a = a[None, :]
    n_ch, n = a.shape
    if n < 64:
        return x, {"note": "too short"}

    # -------- 1. Sidechain input transformer (~90 Hz HPF, detector path only)
    try:
        from scipy.signal import butter, sosfilt
        _sc = butter(1, sidechain_hpf_hz / (sr * 0.5), btype="high", output="sos")
        det_src = sosfilt(_sc, a, axis=1)
    except Exception:
        det_src = a

    pre_gain = _db_to_lin(input_gain_db)
    xin = (a * pre_gain).astype(np.float64)
    det = (det_src * pre_gain).astype(np.float64)

    # -------- 2. Near-instant attack — the 1176 signature
    atk_coef = float(np.exp(-1.0 / max(1.0, sr * attack_ms / 1000.0)))
    rel_coef = float(np.exp(-1.0 / max(1.0, sr * release_ms / 1000.0)))

    # -------- 3. Ratio / knee (hard-knee; British stacks to ~20:1)
    if british_mode:
        eff_ratio = 20.0
        knee_db   = 4.5
    else:
        eff_ratio = float(ratio)
        knee_db   = 3.0
    slope = 1.0 - 1.0 / eff_ratio

    # -------- 4. Feedback loop — sample-by-sample, sidechain reads y[n-1]
    out = np.empty_like(xin)
    gr_series = np.zeros(n, dtype=np.float64)
    env = 0.0

    x0 = xin[0]; x1 = xin[1] if n_ch > 1 else x0
    d0 = det[0]; d1 = det[1] if n_ch > 1 else d0
    o0 = out[0]; o1 = out[1] if n_ch > 1 else o0
    thr = float(threshold_db)
    inv_knee = 1.0 / knee_db
    log10 = np.log10

    for i in range(n):
        # FEEDBACK: look at the previous OUTPUT sample, not the input.
        if i > 0:
            pl = o0[i-1] if o0[i-1] >= 0 else -o0[i-1]
            if n_ch > 1:
                pr = o1[i-1] if o1[i-1] >= 0 else -o1[i-1]
                s = pl if pl >= pr else pr
            else:
                s = pl
        else:
            s = 0.0

        # Envelope follower — attack essentially instantaneous
        if s > env:
            env = atk_coef * env + (1.0 - atk_coef) * s
        else:
            env = rel_coef * env + (1.0 - rel_coef) * s

        # Gain computer — hard knee with a small quadratic transition
        env_db = 20.0 * log10(env + 1e-12) if env > 0.0 else -200.0
        over = env_db - thr
        if over <= -knee_db:
            gr = 0.0
        elif over >= 0.0:
            gr = -over * slope
        else:
            t = (over + knee_db) * inv_knee
            gr = -(over * slope) * t * t * (3.0 - 2.0 * t)

        gr_series[i] = gr
        g = 10.0 ** (gr / 20.0)
        o0[i] = x0[i] * g
        if n_ch > 1:
            o1[i] = x1[i] * g

    # -------- 5. Class A output — subtle FET asymmetric clip
    if sat_drive > 0.0:
        drive = 1.0 + float(sat_drive)
        bias  = 0.03 * float(sat_drive)
        tanh  = np.tanh
        out = (tanh((out + bias) * drive) - tanh(bias * drive)) / (drive * tanh(1.0))

    # -------- 6. Level-neutral auto-makeup (or manual if makeup_db != 0)
    if makeup_db == 0.0:
        rms_in  = float(np.sqrt(np.mean(xin ** 2))) + 1e-12
        rms_out = float(np.sqrt(np.mean(out ** 2))) + 1e-12
        auto_makeup_db = float(np.clip(20.0 * np.log10(rms_in / rms_out), -6.0, 12.0))
        out = out * _db_to_lin(auto_makeup_db)
    else:
        auto_makeup_db = 0.0
        out = out * _db_to_lin(makeup_db)

    info = {
        "model": "UREI 1176LN Rev D (FET, feedback)",
        "ratio": round(float(eff_ratio), 2),
        "british_mode": bool(british_mode),
        "threshold_db": round(float(thr), 2),
        "attack_ms": round(float(attack_ms), 3),
        "release_ms": round(float(release_ms), 1),
        "input_gain_db": round(float(input_gain_db), 2),
        "max_gr_db": round(float(gr_series.min()), 2),
        "avg_gr_db": round(float(gr_series.mean()), 2),
        "auto_makeup_db": round(auto_makeup_db, 2),
    }
    result = out.astype(np.float32)
    if x.ndim == 1:
        return result[0], info
    return result, info
