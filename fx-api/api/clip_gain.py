"""Relative clip-gain rider — level-neutral vocal dynamics pre-stage.

Rides loud words down and quiet words up, targets the vocal's OWN average
(not a fixed dB), and stays level-neutral on average. This is what closes
the dynamic-range gap that compressors cannot touch (they only act above
threshold; quiet words pass through untouched).
"""
import numpy as np
from numba import njit


@njit(cache=True)
def _asym_solver(src, sr, active_mask, local_rms_db, avg_rms_db,
                 max_gain_db, attack_ms, release_ms):
    samples = len(src)
    out_sig = np.zeros(samples, dtype=np.float32)

    alpha_atk = 1.0 - np.exp(-1.0 / ((attack_ms / 1000.0) * sr))
    alpha_rel = 1.0 - np.exp(-1.0 / ((release_ms / 1000.0) * sr))

    current_gain = 1.0

    for s in range(samples):
        if active_mask[s]:
            ideal_db = avg_rms_db - local_rms_db[s]
            if ideal_db > max_gain_db:
                ideal_db = max_gain_db
            elif ideal_db < -max_gain_db:
                ideal_db = -max_gain_db
            target = 10.0 ** (ideal_db / 20.0)
        else:
            target = 1.0

        if target < current_gain:
            current_gain += alpha_atk * (target - current_gain)
        else:
            current_gain += alpha_rel * (target - current_gain)

        out_sig[s] = src[s] * current_gain

    return out_sig


def clip_gain_ride(x, sr, window_ms=100.0, max_gain_db=3.0,
                   silence_threshold_db=-42.0):
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    channels, samples = a.shape
    if samples < 256:
        return x

    sil_lin = 10.0 ** (silence_threshold_db / 20.0)
    win = int((window_ms / 1000.0) * sr)
    if win % 2:
        win += 1
    half = win // 2

    attack_ms  = 30.0
    release_ms = 250.0

    # Pass 1: local RMS per channel
    local_rms_db_list = []
    active_masks = []
    for ch in range(channels):
        src = a[ch]
        pad = np.pad(src, half, mode="reflect")
        sq  = pad.astype(np.float64) ** 2
        cs  = np.cumsum(sq)
        energy = cs[win:] - cs[:-win]
        rms = np.sqrt(np.maximum(energy / win, 1e-10))
        if len(rms) < samples:
            rms = np.pad(rms, (0, samples - len(rms)), mode="edge")
        elif len(rms) > samples:
            rms = rms[:samples]
        mask = rms > sil_lin
        rms_db = 20.0 * np.log10(rms)
        local_rms_db_list.append(rms_db)
        active_masks.append(mask)

    # Pass 2: one linked global average (linear-domain, no dB bias)
    pooled = np.concatenate([local_rms_db_list[ch][active_masks[ch]]
                             for ch in range(channels)])
    if pooled.size == 0:
        return a if a.ndim == 2 else a[0]
    pooled_lin = 10.0 ** (pooled / 20.0)
    global_avg_db = 20.0 * np.log10(np.mean(pooled_lin) + 1e-12)

    # Pass 3: solve each channel against the same global target
    out = np.zeros_like(a)
    for ch in range(channels):
        out[ch] = _asym_solver(
            a[ch], float(sr), active_masks[ch], local_rms_db_list[ch],
            float(global_avg_db), float(max_gain_db),
            float(attack_ms), float(release_ms),
        )

    # Peak safety
    pk = float(np.max(np.abs(out)))
    if pk > 0.95:
        out = (out * (0.95 / pk)).astype(np.float32)

    if x.ndim == 1:
        return out[0]
    return out
