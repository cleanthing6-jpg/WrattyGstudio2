"""Noise-robust monophonic pitch tracker: YIN difference function + Viterbi (pYIN-style)."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from . import dsp


@dataclass
class PitchTrack:
    hop: int
    sr: int
    f0: np.ndarray
    conf: np.ndarray
    voiced: np.ndarray

    @property
    def times(self):
        return np.arange(len(self.f0)) * self.hop / self.sr


def _cmnd(frames: np.ndarray, W: int, L: int) -> np.ndarray:
    B = frames.shape[0]
    nfft = 1 << int(np.ceil(np.log2(W + L)))
    a = frames[:, :W]
    X = np.fft.rfft(frames, nfft, axis=1)
    A = np.fft.rfft(a, nfft, axis=1)
    cc = np.fft.irfft(np.conj(A) * X, nfft, axis=1)[:, : L + 1]
    csq = np.concatenate([np.zeros((B, 1)), np.cumsum(frames ** 2, axis=1)], axis=1)
    e0 = (csq[:, W] - csq[:, 0])[:, None]
    taus = np.arange(L + 1)
    et = csq[:, W + taus] - csq[:, taus]
    d = e0 + et - 2.0 * cc
    d = np.maximum(d, 0.0)
    d[:, 0] = 0.0
    cum = np.cumsum(d[:, 1:], axis=1)
    dn = np.ones_like(d)
    dn[:, 1:] = d[:, 1:] * taus[1:] / np.maximum(cum, 1e-12)
    return dn


def track_pitch(
    x: np.ndarray, sr: int, fmin: float = 65.0, fmax: float = 1000.0, hop_ms: float = 5.0,
    analysis_sr: int = 16000, bins_per_octave: int = 120, energy_gate_db: float = 6.0,
    noise_floor_db: float | None = None,
) -> PitchTrack:
    hop = int(round(hop_ms * 1e-3 * sr))
    xa = dsp.resample(x, sr, analysis_sr)
    xa = dsp.zero_phase(xa, dsp.butter_sos("bandpass", [max(fmin * 0.8, 40.0), 2400.0], analysis_sr, 3))
    ahop = analysis_sr * hop_ms * 1e-3
    n_frames = int(np.ceil(len(x) / hop))
    W = int(round(analysis_sr / fmin * 2.0))
    L = int(np.ceil(analysis_sr / fmin)) + 2
    pad = W + L
    xp = np.concatenate([np.zeros(W // 2), xa, np.zeros(pad + W)])
    starts = np.round(np.arange(n_frames) * ahop).astype(np.int64)
    
    nb = int(np.floor(np.log2(fmax / fmin) * bins_per_octave)) + 1
    fbins = fmin * 2.0 ** (np.arange(nb) / bins_per_octave)
    lags = analysis_sr / fbins
    li = np.floor(lags).astype(np.int64)
    lw = lags - li
    obs = np.zeros((n_frames, nb), dtype=np.float32)
    octpen = np.zeros((n_frames, nb), dtype=np.float32)
    NF = 2048
    win = np.hanning(W + L)
    fidx = fbins * NF / analysis_sr
    hidx = fbins * 0.5 * NF / analysis_sr
    from scipy.ndimage import maximum_filter1d
    def _mag_at(mags, idx):
        i0 = np.floor(idx).astype(int); w = idx - i0
        return (1 - w) * mags[:, i0] + w * mags[:, np.minimum(i0 + 1, mags.shape[1] - 1)]
    rms = np.zeros(n_frames)
    B = 1500
    for s in range(0, n_frames, B):
        idx = starts[s:s + B, None] + np.arange(W + L)[None, :]
        fr = xp[idx]
        dn = _cmnd(fr, W, L)
        per = 1.0 - ((1 - lw) * dn[:, li] + lw * dn[:, np.minimum(li + 1, L)])
        obs[s:s + B] = np.clip(per, 0.0, 1.0)
        rms[s:s + B] = np.sqrt(np.mean(fr[:, :W] ** 2, axis=1))
        mags = np.abs(np.fft.rfft(fr * win[None, :], NF, axis=1))
        mags = maximum_filter1d(mags, 5, axis=1)
        mh = _mag_at(mags, hidx)
        r = mh / (_mag_at(mags, fidx) + 1e-9)
        floor = 0.5 * (_mag_at(mags, hidx * 0.72) + _mag_at(mags, hidx * 1.38)) + 1e-9
        prom = mh / floor
        octpen[s:s + B] = dsp.smoothstep(r, 0.12, 0.35) * dsp.smoothstep(prom, 2.0, 5.0)
    rms_db = 20 * np.log10(rms + 1e-9)
    if noise_floor_db is None:
        noise_floor_db = float(np.percentile(rms_db, 3))
    gate = (rms_db < (noise_floor_db + energy_gate_db)) & (obs.max(axis=1) < 0.80)

    obs = obs * (1.0 - 0.7 * octpen).astype(np.float32)
    obs_v = np.log(obs + 0.06)
    unv_score = np.full(n_frames, np.log(0.45 + 0.06), dtype=np.float32)
    unv_score[gate] = 2.0
    obs_v[gate] -= 3.0
    maxj = int(round(bins_per_octave * 0.14))
    lam = 0.05 * (120.0 / bins_per_octave)
    switch = 1.4
    delta = obs_v[0].copy()
    du = unv_score[0]
    bp = np.zeros((n_frames, nb), dtype=np.int16)
    bu = np.zeros((n_frames, 2), dtype=np.int8)
    SENT = 32000
    big = -1e9
    vargs = np.zeros(n_frames, dtype=np.int32)
    
    for t in range(1, n_frames):
        cand = np.full(nb, big, dtype=np.float64)
        arg = np.zeros(nb, dtype=np.int16)
        for j in range(-maxj, maxj + 1):
            if j >= 0:
                sh = np.full(nb, big); sh[j:] = delta[:nb - j] if j else delta
            else:
                sh = np.full(nb, big); sh[:nb + j] = delta[-j:]
            sh = sh - lam * abs(j)
            m = sh > cand
            cand = np.where(m, sh, cand); arg = np.where(m, j, arg).astype(np.int16)
        from_u = du - switch
        v_best = delta.max(); v_arg = int(delta.argmax())
        use_u = from_u > cand
        newdelta = np.where(use_u, from_u, cand) + obs_v[t]
        bp[t] = np.where(use_u, SENT, arg)
        cu_from_v = v_best - switch
        if cu_from_v > du:
            newdu = cu_from_v + unv_score[t]; bu[t, 0] = 1; bu[t, 1] = 0
            bu_arg = v_arg
        else:
            newdu = du + unv_score[t]; bu[t, 0] = 0
            bu_arg = 0
        vargs[t] = bu_arg
        delta, du = newdelta, newdu
        mx = max(delta.max(), du)
        delta = delta - mx; du = du - mx
        
    state_voiced = delta.max() >= du
    k = int(delta.argmax())
    path = np.full(n_frames, -1, dtype=np.int32)
    for t in range(n_frames - 1, -1, -1):
        if state_voiced:
            path[t] = k
            if t == 0:
                break
            off = bp[t, k]
            if off == SENT:
                state_voiced = False
            else:
                k = k - int(off)
        else:
            if t == 0:
                break
            if bu[t, 0] == 1:
                state_voiced = True
                k = int(vargs[t])
    voiced = path >= 0
    f0 = np.zeros(n_frames)
    f0[voiced] = fbins[path[voiced]]
    conf = np.where(voiced, obs[np.arange(n_frames), np.maximum(path, 0)], 0.0).astype(np.float64)
    
    vi = np.where(voiced & (path > 0) & (path < nb - 1))[0]
    if len(vi):
        a = obs[vi, path[vi] - 1].astype(np.float64); b = obs[vi, path[vi]].astype(np.float64); c = obs[vi, path[vi] + 1].astype(np.float64)
        den = (a - 2 * b + c)
        off = np.where(np.abs(den) > 1e-9, 0.5 * (a - c) / den, 0.0)
        off = np.clip(off, -1.0, 1.0)
        f0[vi] = fbins[path[vi]] * 2.0 ** (off / bins_per_octave)
        
    from scipy.ndimage import binary_opening, binary_closing
    v2 = binary_closing(voiced, structure=np.ones(4, bool))
    v2 = binary_opening(v2, structure=np.ones(5, bool))
    
    if v2.any():
        idx = np.arange(n_frames)
        good = f0 > 0
        if good.sum() > 1:
            lf = np.interp(idx, idx[good], np.log2(f0[good]))
            f0 = np.where(v2, 2.0 ** lf, 0.0)
    f0[~v2] = 0.0
    conf = np.where(v2, np.maximum(conf, 0.05), 0.0)
    return PitchTrack(hop=hop, sr=sr, f0=f0, conf=conf, voiced=v2)
