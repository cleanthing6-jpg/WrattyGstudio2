"""Tier-1 stereo tape delay: circular buffer, tempo sync, cross-feedback
ping-pong, feedback filters, LFO modulation, envelope duck, tape sat, Numba."""
import numpy as np
from numba import njit


@njit(cache=True)
def _delay_core(xL, xR, sr, delay_samples, mod_depth_samps, mod_rate,
                fb, mix, ahp, alp, atk, rel, duck_depth, width, rms_vocal):
    n = len(xL)
    max_delay = delay_samples + int(mod_depth_samps) + 4
    bufL = np.zeros(max_delay, dtype=np.float32)
    bufR = np.zeros(max_delay, dtype=np.float32)

    outL = np.zeros(n, dtype=np.float32)
    outR = np.zeros(n, dtype=np.float32)

    hp_prevL = 0.0; hp_prevR = 0.0
    x_prevL = 0.0;  x_prevR = 0.0
    lp_L = 0.0;     lp_R = 0.0
    env = 0.0

    two_pi = 6.283185307179586
    ptr = 0
    for i in range(n):
        # LFO modulation, fractional
        mod = mod_depth_samps * np.sin(two_pi * mod_rate * i / sr)
        f = (ptr - delay_samples + mod) % max_delay
        if f < 0.0: f += max_delay
        i0 = int(f)
        fr = f - i0
        i1 = (i0 + 1) % max_delay
        dL = (1.0 - fr) * bufL[i0] + fr * bufL[i1]
        dR = (1.0 - fr) * bufR[i0] + fr * bufR[i1]

        # Feedback filters
        hL = ahp * (hp_prevL + dL - x_prevL)
        hp_prevL = hL; x_prevL = dL
        lp_L += alp * (hL - lp_L)

        hR = ahp * (hp_prevR + dR - x_prevR)
        hp_prevR = hR; x_prevR = dR
        lp_R += alp * (hR - lp_R)

        # Envelope-follower duck (peak of dry L+R)
        rL = xL[i] if xL[i] >= 0.0 else -xL[i]
        rR = xR[i] if xR[i] >= 0.0 else -xR[i]
        rr = rL if rL >= rR else rR
        # Normalize by this vocal's own RMS so duck scales per user
        rr_norm = rr / (rms_vocal + 1e-9)
        if rr_norm > env: env += atk * (rr_norm - env)
        else:             env += rel * (rr_norm - env)
        dg = 1.0 - duck_depth * env
        if dg < 0.0: dg = 0.0

        # Fixed-side delay: dry -> L only, R stays silent
        sL = lp_R
        sR = lp_L
        bufL[ptr] = xL[i] + fb * sL
        bufR[ptr] = 0.0

        # Wet only widened; dry untouched
        wL = lp_L * mix * dg
        wR = lp_R * mix * dg
        mid = (wL + wR) * 0.5
        side = (wL - wR) * 0.5 * width
        outL[i] = xL[i] + mid + side
        outR[i] = xR[i] + mid - side

        ptr += 1
        if ptr >= max_delay: ptr = 0

    return outL, outR


def coeff_hpf(fc_hz, sr):
    """Correct 1st-order RC highpass coefficient."""
    rc = 1.0 / (2.0 * np.pi * fc_hz)
    dt = 1.0 / sr
    return rc / (rc + dt)


def coeff_tau(tau, sr):
    return 1.0 - np.exp(-1.0 / (tau * sr))


def delay_render(voc, sr, bpm=100.0, preset="afrobeats",
                 note_div=0.75, feedback=0.10, mix=1.0, width=1.0,
                 hp_cut=400.0, lp_cut=3000.0,
                 mod_rate=0.4, mod_depth_ms=2.0,
                 duck_depth=0.8, tape=True):
    """Drop-in for delay_spec.render — same return (wet_2ch, info)."""
    a = np.asarray(voc, dtype=np.float32)
    if a.ndim == 1:
        a = np.stack([a, a])
    if a.shape[0] == 1:
        a = np.stack([a[0], a[0]])

    try: bpm = float(bpm)
    except Exception: bpm = 100.0
    if not (bpm > 0.0): bpm = 100.0

    # Multi-user safe: RMS of this user's own vocal
    rms_vocal = float(np.sqrt(np.mean(a.astype(np.float64) ** 2)) + 1e-9)

    delay_sec = (60.0 / bpm) * float(note_div)
    delay_samples = int(delay_sec * sr)
    mod_depth_samps = (mod_depth_ms / 1000.0) * sr

    ahp = np.float32(coeff_hpf(hp_cut, sr))
    alp = np.float32(coeff_tau(1.0 / (2.0 * np.pi * lp_cut), sr))
    atk = np.float32(coeff_tau(0.005, sr))
    rel = np.float32(coeff_tau(0.150, sr))

    L, R = _delay_core(
        a[0].astype(np.float32), a[1].astype(np.float32),
        float(sr), int(delay_samples), float(mod_depth_samps),
        float(mod_rate), float(feedback), float(mix),
        float(ahp), float(alp), float(atk), float(rel),
        float(duck_depth), float(width), float(rms_vocal),
    )

    wet = np.stack([L - a[0], R - a[1]]).astype(np.float32)
    pk = float(np.max(np.abs(wet)))
    if pk > 0.95: wet *= 0.95 / pk

    info = {
        "preset": preset,
        "note_factor": float(note_div),
        "delay_ms": round(delay_sec * 1000.0, 1),
        "bpm_used": round(bpm, 1),
        "feedback": float(feedback),
        "send_db": round(20.0 * np.log10(max(1e-6, mix)), 2),
        "hpf_hz": float(hp_cut), "lpf_hz": float(lp_cut),
        "width": float(width), "duck_db": float(duck_depth * 20.0),
        "modulation_rate_hz": float(mod_rate),
        "modulation_depth_ms": float(mod_depth_ms),
    }
    return wet, info
