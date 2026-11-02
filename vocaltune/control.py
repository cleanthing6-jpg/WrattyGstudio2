"""Correction controller: note segmentation, hysteresis-based target selection, retune dynamics,
humanize, vibrato handling. Output: a smooth per-frame pitch SHIFT (cents) to apply to the vocal."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scipy.ndimage import median_filter, gaussian_filter1d
from . import dsp, theory

@dataclass
class Settings:
    retune_ms: float = 30.0
    amount: float = 0.9
    flex_cents: float = 12.0
    humanize: float = 0.35
    vibrato_keep: float = 1.0
    add_vibrato_cents: float = 0.0
    vibrato_rate_hz: float = 5.4
    vibrato_delay_s: float = 0.30
    transpose_semitones: float = 0.0
    detune_cents: float = 0.0
    hysteresis_cents: float = 22.0
    split_cents: float = 85.0
    glide_slope: tuple = (350.0, 800.0)
    max_shift_cents: float = 200.0
    conf_gate: tuple = (0.45, 0.80)
    formant_shift_semitones: float = 0.0
    min_shift_to_process: float = 2.0

@dataclass
class Note:
    start: int
    end: int
    center_cents: float
    target_midi: int
    deviation_cents: float
    mean_conf: float

@dataclass
class Correction:
    shift_cents: np.ndarray
    target_midi: np.ndarray
    center_midi: np.ndarray
    notes: list
    hop_s: float
    diag: dict = field(default_factory=dict)

def _runs(mask: np.ndarray):
    d = np.diff(np.r_[0, mask.astype(np.int8), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))

def segment_notes(c: np.ndarray, voiced: np.ndarray, st: Settings, hop_s: float):
    cs = c.copy()
    for a, b in _runs(voiced):
        if b - a >= 5:
            cs[a:b] = median_filter(c[a:b], size=5, mode="nearest")
    segs = []
    win = int(0.15 / hop_s)
    need = max(3, int(0.02 / hop_s))
    for a, b in _runs(voiced):
        start = a; run = 0
        i = a
        while i < b:
            lo = max(start, i - win)
            anchor = np.median(cs[lo:i]) if i - lo >= 3 else cs[min(i, b - 1)]
            if i - start >= 4 and abs(cs[i] - anchor) > st.split_cents:
                run += 1
                if run >= need:
                    cut = i - need + 1
                    segs.append((start, cut)); start = cut; run = 0
            else:
                run = 0
            i += 1
        segs.append((start, b))
    merged = []
    for s in segs:
        if merged and (s[1] - s[0]) * hop_s < 0.04 and merged[-1][1] == s[0]:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append(s)
    return merged, cs

def choose_targets(center_seg_median: float, allowed_notes: np.ndarray, weights: np.ndarray, tie_cents=12.0):
    d = np.abs(allowed_notes * 100.0 - center_seg_median)
    order = np.argsort(d)
    best, second = order[0], order[1]
    if d[second] - d[best] < tie_cents:
        wb, ws = weights[int(allowed_notes[best]) % 12], weights[int(allowed_notes[second]) % 12]
        if ws > wb * 1.15:
            best = second
    return int(allowed_notes[best])

def compute_correction(f0, conf, voiced, hop_s, allowed_mask, tuning_cents, key, mode, st: Settings,
                       external_targets=None) -> Correction:
    n = len(f0)
    midi = np.where(voiced, 69 + 12 * np.log2(np.maximum(f0, 1.0) / 440.0) - tuning_cents / 100.0, np.nan)
    c = np.where(voiced, midi * 100.0, 0.0)
    notes_midi = np.array([m for m in range(24, 110) if allowed_mask[m % 12]])
    weights = theory.scale_weights(key, mode)
    segs, cs = segment_notes(c, voiced, st, hop_s)

    center = np.zeros(n); target = np.full(n, np.nan)
    note_age = np.zeros(n)
    notes = []
    sig = max(1.0, 0.10 / hop_s)
    for a, b in segs:
        w = np.zeros(n); w[a:b] = np.maximum(conf[a:b], 0.05)
        L = b - a
        on, off_ = int(0.09 / hop_s), int(0.03 / hop_s)
        if L * hop_s > 0.30:
            w[a:a + on] *= 0.02; w[b - off_:b] *= 0.2
        seg_c = np.zeros(n); seg_c[a:b] = c[a:b]
        ctr = dsp.normalized_smooth(seg_c[a:b], w[a:b], sig)
        center[a:b] = ctr
        med = float(np.median(ctr))
        tmidi = choose_targets(med, notes_midi, weights)
        lab = tmidi; labels = np.empty(b - a, dtype=int)
        for k in range(b - a):
            cur = lab * 100.0
            if abs(ctr[k] - cur) > 50.0 + st.hysteresis_cents:
                lab = int(notes_midi[np.argmin(np.abs(notes_midi * 100.0 - ctr[k]))])
            labels[k] = lab
        if external_targets is not None:
            labels[:] = external_targets(a, b, med, labels)
        target[a:b] = labels + st.transpose_semitones + st.detune_cents / 100.0
        note_age[a:b] = np.arange(b - a) * hop_s
        notes.append(Note(a, b, med, int(labels[len(labels) // 2]), float(labels[len(labels) // 2] * 100.0 - med), float(np.mean(conf[a:b]))))

    e = np.where(voiced, target * 100.0 - center, 0.0)
    flex = max(st.flex_cents, 0.1)
    knee = dsp.smoothstep(np.abs(e), 0.45 * flex, 1.6 * flex)
    D = st.amount * knee * e
    slope = np.zeros(n)
    for a, b in segs:
        if b - a >= 5:
            slope[a:b] = np.abs(np.gradient(gaussian_filter1d(center[a:b], 1.5))) / hop_s
    D *= 1.0 - dsp.smoothstep(slope, *st.glide_slope)
    gate = dsp.smoothstep(conf, *st.conf_gate)
    D[~voiced] = 0.0

    sust = dsp.smoothstep(note_age, 0.20, 1.20)
    tau = np.maximum(st.retune_ms * 1e-3, 1e-4) * (1.0 + 3.0 * st.humanize * sust)
    alpha = 1.0 - np.exp(-hop_s / tau)
    corr = np.zeros(n); prev = 0.0
    for t in range(n):
        if not voiced[t]:
            prev = 0.0; corr[t] = 0.0; continue
        want = D[t] * (1.0 - 0.5 * st.humanize * sust[t])
        prev += alpha[t] * (gate[t] * want + (1.0 - gate[t]) * prev - prev)
        corr[t] = prev
    micro = np.where(voiced, c - center, 0.0)
    micro_s = gaussian_filter1d(micro, max(1.0, 0.018 / hop_s))
    shift = corr - (1.0 - st.vibrato_keep) * micro_s
    if st.add_vibrato_cents > 0:
        rng = np.random.default_rng(7)
        for (a, b), nt in zip(segs, notes):
            dur = (b - a) * hop_s
            if dur < 0.55:
                continue
            m = micro[a:b]
            seg = m - m.mean(); F = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 1024)) / max(len(seg), 1)
            fr = np.fft.rfftfreq(1024, hop_s); band = (fr > 4.0) & (fr < 8.0)
            existing = 4.0 * F[band].max() if band.any() else 0.0
            if existing > 0.6 * st.add_vibrato_cents:
                continue
            t_s = np.arange(b - a) * hop_s
            rate = st.vibrato_rate_hz * (1 + 0.05 * rng.normal())
            env = dsp.smoothstep(t_s, st.vibrato_delay_s, st.vibrato_delay_s + 0.25) * dsp.smoothstep(dur - t_s, 0.03, 0.15)
            shift[a:b] += st.add_vibrato_cents * env * np.sin(2 * np.pi * rate * t_s + rng.uniform(0, 6.28))
    shift = st.max_shift_cents * np.tanh(shift / st.max_shift_cents)
    fade = np.ones(n)
    nf = max(2, int(0.025 / hop_s))
    for a, b in _runs(voiced):
        L = b - a
        r = np.minimum(np.arange(L) + 1, np.arange(L)[::-1] + 1)
        fade[a:b] = dsp.smoothstep(r, 0, nf)
    shift = shift * fade
    shift = gaussian_filter1d(shift, max(1.0, 0.012 / hop_s))
    shift[~voiced] = 0.0
    return Correction(shift, np.where(voiced, target, np.nan), np.where(voiced, center / 100.0, np.nan), notes, hop_s,
                      {"error_center_cents": e, "D": D, "corr": corr, "micro": micro, "segments": segs})
