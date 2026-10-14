"""UREI 1176 Rev D — Numba-compiled, polyphase 2x oversampled."""
import numpy as np
from numba import njit


@njit(cache=True)
def _polyphase_iir_upsample_2x_core(x_ch, state_even, state_odd):
    samples = len(x_ch)
    y_e = np.zeros(samples, dtype=np.float32)
    y_o = np.zeros(samples, dtype=np.float32)
    A0 = 0.12159005792425
    A1 = 0.53696841243169
    s0 = state_even[0]
    for s in range(samples):
        v = x_ch[s]
        ov = A0 * v + s0
        s0 = v - A0 * ov
        y_e[s] = ov
    s1 = state_odd[0]; s2 = state_odd[1]
    for s in range(samples):
        v = x_ch[s]
        o1 = A1 * v + s1
        s1 = v - A1 * o1
        o2 = A0 * o1 + s2
        s2 = o1 - A0 * o2
        y_o[s] = o2
    state_even[0] = s0
    state_odd[0] = s1
    state_odd[1] = s2
    y = np.zeros(samples * 2, dtype=np.float32)
    y[0::2] = y_e
    y[1::2] = y_o
    return y


@njit(cache=True)
def _1176_solver(driven_signal, alpha_atk, alpha_rel, threshold, ratio):
    n = len(driven_signal)
    out_sig = np.zeros(n, dtype=np.float32)
    env = 0.0
    control = 1.0
    for s in range(n):
        vocal_out = driven_signal[s] * control
        rect = abs(vocal_out)
        if rect > env:
            env += alpha_atk * (rect - env)
        else:
            env += alpha_rel * (rect - env)
        if env > threshold:
            overshoot = env - threshold
            control = 1.0 / (1.0 + (overshoot * (ratio - 1.0)))
        else:
            control = 1.0
        out_sig[s] = np.arctan(vocal_out * 1.5) / 1.5
    return out_sig


def fet_compress(x, sr, threshold_db=-20.0, ratio=4.0,
                 attack_ms=5.0, release_ms=80.0,
                 input_drive_db=12.0, sidechain_hpf_hz=90.0,
                 sat_drive=0.10, british_mode=False, **_):
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    channels, samples = a.shape
    if samples < 64:
        return x, {"note": "too short"}

    try:
        from scipy.signal import butter, sosfilt
        sos = butter(1, sidechain_hpf_hz / (sr * 0.5), btype="high", output="sos")
        a_det = sosfilt(sos, a, axis=1).astype(np.float32)
    except Exception:
        a_det = a

    sr2 = sr * 2.0
    alpha_atk = 1.0 - np.exp(-1.0 / max(1.0, (attack_ms / 1000.0) * sr2))
    alpha_rel = 1.0 - np.exp(-1.0 / max(1.0, (release_ms / 1000.0) * sr2))

    det_rms = float(np.sqrt(np.mean(a_det ** 2) + 1e-12))
    thr_lin = max(1e-6, det_rms * (10.0 ** (threshold_db / 20.0)) * 10.0)
    if british_mode:
        ratio = 20.0

    drive_lin = 10.0 ** (input_drive_db / 20.0)

    out = np.zeros_like(a)
    for ch in range(channels):
        st_e = np.zeros(1, dtype=np.float32)
        st_o = np.zeros(2, dtype=np.float32)
        up = _polyphase_iir_upsample_2x_core(a[ch], st_e, st_o)
        up = up * drive_lin
        solved = _1176_solver(up, alpha_atk, alpha_rel, thr_lin, ratio)
        out[ch] = solved[0::2]

    if sat_drive > 0.0:
        d = 1.0 + float(sat_drive)
        b = 0.03 * float(sat_drive)
        out = (np.tanh((out + b) * d) - np.tanh(b * d)) / (d * np.tanh(1.0))

    rms_in = float(np.sqrt(np.mean(a ** 2)) + 1e-12)
    rms_out = float(np.sqrt(np.mean(out ** 2)) + 1e-12)
    makeup_db = float(np.clip(20.0 * np.log10(rms_in / rms_out), -6.0, 12.0))
    out = (out * (10.0 ** (makeup_db / 20.0))).astype(np.float32)

    pk = float(np.max(np.abs(out)))
    if pk > 0.95:
        out = (out * (0.95 / pk)).astype(np.float32)

    info = {
        "model": "UREI 1176LN Rev D (Numba + polyphase 2x)",
        "ratio": round(float(ratio), 2),
        "attack_ms": round(float(attack_ms), 3),
        "release_ms": round(float(release_ms), 1),
        "auto_makeup_db": round(makeup_db, 2),
    }
    result = out.astype(np.float32)
    if x.ndim == 1:
        return result[0], info
    return result, info
