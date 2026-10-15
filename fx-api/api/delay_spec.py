"""Spec-compliant stereo ping-pong delay for the vocal bus.

Follows afrobeats_default_preset_v1.json -> "delay" section.

  - auto-pick note value so delay_ms lands in [250, 500]
  - stereo ping-pong, feedback 0.25 (max 0.35)
  - HPF 400 / LPF 5000 on the return
  - light tape saturation
  - stereo width 0.8
  - 0.4 Hz / 2 ms chorus modulation
  - duck 6 dB / 5 ms attack / 150 ms release, keyed from source
  - send level -18 dB
"""
import numpy as np

try:
    from pedalboard import (
        Pedalboard, HighpassFilter, LowpassFilter,
        Chorus, Distortion, Gain,
    )
except Exception:
    Pedalboard = None


PRESETS = {
    "afrobeats": dict(
        feedback=0.25, feedback_max=0.35,
        send_db=-14.0,
        hpf_hz=500.0, lpf_hz=5000.0,
        saturation_drive_db=1.0,
        width=0.80,
        modulation_rate_hz=0.40, modulation_depth_ms=0.8,
        duck_db=6.0, duck_atk_ms=5.0, duck_rel_ms=150.0,
        note_factor_pref=(0.75, 0.5, 0.25, 1.0),
    ),
    "neutral": dict(
        feedback=0.25, feedback_max=0.35,
        send_db=-20.0,
        hpf_hz=400.0, lpf_hz=5000.0,
        saturation_drive_db=0.0,
        width=0.80,
        modulation_rate_hz=0.40, modulation_depth_ms=2.0,
        duck_db=6.0, duck_atk_ms=5.0, duck_rel_ms=150.0,
        note_factor_pref=(0.75, 0.5, 0.25, 1.0),
    ),
}


def _pick_note_factor(bpm, pref):
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        bpm = 100.0
    if not (bpm > 0) or bpm != bpm:
        bpm = 100.0
    beat_ms = 60000.0 / bpm
    for f in pref:
        d_ms = beat_ms * f
        if 100.0 <= d_ms <= 600.0:
            return float(f), float(d_ms)
    best = min(pref, key=lambda f: abs(beat_ms * f - 350.0))
    return float(best), float(beat_ms * best)


def _envelope(x, sr, atk_ms, rel_ms):
    atk = max(1, int(sr * atk_ms / 1000.0))
    rel = max(1, int(sr * rel_ms / 1000.0))
    ax = np.abs(x).astype(np.float32)
    ka = np.ones(atk, dtype=np.float32) / float(atk)
    kr = np.ones(rel, dtype=np.float32) / float(rel)
    e = np.convolve(ax, ka, mode="same")
    e = np.convolve(e, kr, mode="same")
    return e.astype(np.float32)


def render(voc, sr, bpm, preset="afrobeats"):
    if Pedalboard is None:
        return None, {"error": "pedalboard unavailable"}
    p = PRESETS.get(preset, PRESETS["neutral"])
    nf, delay_ms = _pick_note_factor(bpm, p["note_factor_pref"])
    delay_s = delay_ms / 1000.0

    a = np.asarray(voc, dtype=np.float32)
    if a.ndim == 1:
        a = np.stack([a, a])
    if a.shape[0] < 2:
        a = np.stack([a[0], a[0]])
    a = a[:2]
    n = a.shape[1]
    src = ((a[0] + a[1]) * 0.5).astype(np.float32)

    d = int(round(sr * delay_s))
    if d < 1:
        return None, {"error": "delay too short"}

    fb = min(float(p["feedback"]), float(p["feedback_max"]))
    pad = d * 12
    sp = np.zeros(n + pad, dtype=np.float32)
    sp[:n] = src
    out = np.zeros((2, n + pad), dtype=np.float32)
    g = 1.0
    off = d
    if off < n + pad:
        out[0, off:] += sp[:n + pad - off] * g * 0.5
        out[1, off:] += sp[:n + pad - off] * g * 0.5
        g *= fb
    side = 1
    for tap in range(2, 12):
        off = d * tap
        if off >= n + pad:
            break
        out[side, off:] += sp[:n + pad - off] * g
        side = 1 - side
        g *= fb

    out = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=float(p["hpf_hz"]) / 1.96),
        HighpassFilter(cutoff_frequency_hz=float(p["hpf_hz"]) / 1.96),
        HighpassFilter(cutoff_frequency_hz=float(p["hpf_hz"]) / 1.96),
        LowpassFilter(cutoff_frequency_hz=float(p["lpf_hz"]) / 0.644),
        LowpassFilter(cutoff_frequency_hz=float(p["lpf_hz"]) / 0.644),
    ])(out, sr).astype(np.float32)

    try:
        depth_n = float(p["modulation_depth_ms"]) / 25.0
        out = Pedalboard([
            Chorus(rate_hz=float(p["modulation_rate_hz"]),
                   depth=depth_n, mix=0.15),
        ])(out, sr).astype(np.float32)
    except Exception:
        pass

    drive = float(p["saturation_drive_db"])
    if drive > 0.01:
        try:
            out = Pedalboard([
                Distortion(drive_db=drive),
                Gain(gain_db=-drive),
            ])(out, sr).astype(np.float32)
        except Exception:
            pass

    mid = (out[0] + out[1]) * 0.5
    sd = (out[0] - out[1]) * 0.5 * float(p["width"])
    out = np.stack([mid + sd, mid - sd]).astype(np.float32)

    try:
        env = _envelope(src, sr, p["duck_atk_ms"], p["duck_rel_ms"])
        ep = float(env.max())
        if ep > 0:
            env = env / ep
        duck_lin = 10.0 ** (-(float(p["duck_db"]) * env) / 20.0)
        out = out * duck_lin[None, :]
    except Exception:
        pass

    send_lin = 10.0 ** (float(p["send_db"]) / 20.0)
    out = (out * send_lin).astype(np.float32)
    out = out[:, :n]

    try:
        _bpm_out = round(float(bpm), 1) if (isinstance(bpm, (int, float)) and bpm == bpm and bpm > 0) else 100.0
    except Exception:
        _bpm_out = 100.0

    info = {
        "preset": str(preset),
        "note_factor": round(nf, 3),
        "delay_ms": round(delay_ms, 1),
        "bpm_used": _bpm_out,
        "feedback": round(fb, 3),
        "send_db": float(p["send_db"]),
        "hpf_hz": float(p["hpf_hz"]),
        "lpf_hz": float(p["lpf_hz"]),
        "width": float(p["width"]),
        "duck_db": float(p["duck_db"]),
        "saturation_drive_db": drive,
        "modulation_rate_hz": float(p["modulation_rate_hz"]),
        "modulation_depth_ms": float(p["modulation_depth_ms"]),
    }
    return out, info
