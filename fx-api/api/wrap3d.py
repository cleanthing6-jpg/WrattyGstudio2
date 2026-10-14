"""3D Head-Wrap — spatial wrap for lead vocal. M/S, mono-safe."""
import numpy as np
import scipy.signal as signal


def _biquad_to_sos(b, a):
    return np.array([[b[0], b[1], b[2], a[0], a[1], a[2]]], dtype=np.float32)


def _soft_clip_knee(x, ceiling=0.98, threshold_db=-3.0):
    threshold = 10.0 ** (threshold_db / 20.0)
    out = x.copy()
    mask = np.abs(x) > threshold
    if np.any(mask):
        sgn = np.sign(x[mask])
        abs_x = np.abs(x[mask])
        scaled = (abs_x - threshold) / (ceiling - threshold)
        out[mask] = sgn * (threshold + (ceiling - threshold) * np.tanh(scaled))
    return np.clip(out, -ceiling, ceiling)


def _shelf_coeffs(freq_hz, gain_db, s=0.707, sr=44100):
    w0 = 2.0 * np.pi * freq_hz / sr
    A = 10.0 ** (gain_db / 40.0)
    alpha = np.sin(w0) / 2.0 * np.sqrt((A + 1.0 / A) * (1.0 / s - 1.0) + 2.0)
    cw = np.cos(w0)
    b = [A * ((A + 1.0) - (A - 1.0) * cw + 2.0 * np.sqrt(A) * alpha),
         2.0 * A * ((A - 1.0) - (A + 1.0) * cw),
         A * ((A + 1.0) - (A - 1.0) * cw - 2.0 * np.sqrt(A) * alpha)]
    a = [(A + 1.0) + (A - 1.0) * cw + 2.0 * np.sqrt(A) * alpha,
         -2.0 * ((A - 1.0) + (A + 1.0) * cw),
         (A + 1.0) + (A - 1.0) * cw - 2.0 * np.sqrt(A) * alpha]
    return b, a


def _peaking_coeffs(freq_hz, gain_db, q, sr=44100):
    w0 = 2.0 * np.pi * freq_hz / sr
    alpha = np.sin(w0) / (2.0 * q)
    A = 10.0 ** (gain_db / 40.0)
    b = [1.0 + alpha * A, -2.0 * np.cos(w0), 1.0 - alpha * A]
    a = [1.0 + alpha / A, -2.0 * np.cos(w0), 1.0 - alpha / A]
    return b, a


def apply_wrap(vocal_mono, sr=44100, instrumental_rms=-14.0):
    a = np.asarray(vocal_mono, dtype=np.float32)
    if a.ndim == 2:
        a = a.mean(axis=0)
    n = a.shape[0]
    if n < 64:
        return np.stack([a, a]).astype(np.float32)

    # Base path
    wrap = a.copy()
    sos_hp = signal.butter(4, 180.0 / (sr * 0.5), btype="highpass", output="sos")
    wrap = signal.sosfilt(sos_hp, wrap).astype(np.float32)

    b, aa = _peaking_coeffs(2500.0, -3.5, 1.4, sr)
    wrap = signal.sosfilt(_biquad_to_sos(b, aa), wrap).astype(np.float32)

    b, aa = _shelf_coeffs(11000.0, 2.0, 0.707, sr)
    wrap = signal.sosfilt(_biquad_to_sos(b, aa), wrap).astype(np.float32)

    # Haas delays
    dL = int(round(0.011 * sr))
    dR = int(round(0.023 * sr))
    wrap_L = np.zeros(n, dtype=np.float32)
    wrap_R = np.zeros(n, dtype=np.float32)
    if dL < n:
        wrap_L[dL:] = wrap[:-dL]
    if dR < n:
        wrap_R[dR:] = wrap[:-dR]

    # Head-shadow shelves
    b, aa = _shelf_coeffs(4000.0, -2.0, 0.707, sr)
    wrap_R = signal.sosfilt(_biquad_to_sos(b, aa), wrap_R).astype(np.float32)
    b, aa = _shelf_coeffs(4000.0, +2.0, 0.707, sr)
    wrap_L = signal.sosfilt(_biquad_to_sos(b, aa), wrap_L).astype(np.float32)

    # Adaptive gain: -14 dB base, +2 dB if dense
    gain = 0.2
    if instrumental_rms > -12.0:
        gain *= 10.0 ** (2.0 / 20.0)
    wrap_L = wrap_L * gain
    wrap_R = wrap_R * gain

    # M/S: keep half mid for mono depth
    wm = 0.5 * (wrap_L + wrap_R)
    ws = 0.5 * (wrap_L - wrap_R)
    out_L = a + 0.5 * wm + ws
    out_R = a + 0.5 * wm - ws

    # Knee soft clip
    out_L = _soft_clip_knee(out_L, 0.98, -3.0)
    out_R = _soft_clip_knee(out_R, 0.98, -3.0)

    return np.stack([out_L, out_R]).astype(np.float32)
