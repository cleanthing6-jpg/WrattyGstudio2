from __future__ import annotations
import math
from dataclasses import dataclass, replace
import numpy as np
from scipy import signal, ndimage
from scipy.special import exp1
from scipy.stats import gamma as _gamma

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def read_audio(path, mono=True):
    import subprocess, tempfile, os
    from scipy.io import wavfile
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "x.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-c:a", "pcm_f32le", tmp], check=True)
        sr, x = wavfile.read(tmp)
    x = x.astype(np.float64)
    if x.ndim == 2 and mono: x = x.mean(axis=1)
    return x, sr

def write_audio(path, x, sr, channels=1, bits=24):
    import subprocess, tempfile, os
    from scipy.io import wavfile
    x = np.asarray(x, dtype=np.float32)
    if channels == 2: x = np.stack([x, x], axis=1)
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "x.wav")
        wavfile.write(tmp, sr, x)
        fmt = ["-c:a", "flac", "-sample_fmt", "s32"] if path.endswith(".flac") else ["-c:a", "pcm_s24le"] if bits == 24 else ["-c:a", "pcm_s16le"]
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp] + fmt + [path], check=True)

@dataclass
class CleanerConfig:
    hp_hz: float = 70.0; hp_order: int = 4; auto_hum: bool = True; reduction_db: float = 16.0
    gap_reduction_db: float = 30.0; noise_window_s: float = 3.0; noise_percentile: float = 12.0
    oversub: float = 1.0; n_fft: int = 2048; hop: int = 512; dd_alpha: float = 0.97

class AdaptiveNoiseCleaner:
    def __init__(self, cfg: CleanerConfig | None = None, **kw):
        self.cfg = replace(cfg or CleanerConfig(), **kw)
        self.report = {}
    def _notch_hum(self, y, sr):
        f, p = signal.welch(y[np.abs(y) > 0], sr, nperseg=16384) if np.any(y) else (None, None)
        if f is None: return y
        pd = 10 * np.log10(p + 1e-30)
        found = []
        for base in (50.0, 60.0):
            hits = 0
            for h in range(1, 6):
                fc = base * h
                if fc > 1000: break
                band = (f > fc - 2) & (f < fc + 2)
                around = ((f > fc - 12) & (f < fc - 5)) | ((f > fc + 5) & (f < fc + 12))
                if band.any() and around.any() and pd[band].max() - np.median(pd[around]) > 12:
                    hits += 1; found.append(fc)
            if hits >= 2: break
            found = [] if hits < 2 else found
        for fc in found:
            b, a = signal.iirnotch(fc, Q=40, fs=sr); y = signal.filtfilt(b, a, y)
        self.report["hum_notches_hz"] = found
        return y
    def process(self, x, sr):
        c = self.cfg; x = np.asarray(x, dtype=np.float64); y = x - np.mean(x)
        sos = signal.butter(c.hp_order, c.hp_hz, "hp", fs=sr, output="sos"); y = signal.sosfiltfilt(sos, y)
        if c.auto_hum: y = self._notch_hum(y, sr)
        n, hop = c.n_fft, c.hop
        _, _, X = signal.stft(y, sr, window="hann", nperseg=n, noverlap=n - hop, boundary="zeros", padded=True)
        F, T = X.shape; P = np.abs(X) ** 2; freqs = np.fft.rfftfreq(n, 1 / sr)
        bm = np.zeros(T + 4); nb = len(y) // hop + 1
        blk = np.abs(np.pad(y, (0, nb * hop - len(y))))[: nb * hop].reshape(nb, hop).max(1)
        Lb = min(nb, T + 2); bm[2: 2 + Lb] = blk[:Lb]
        valid = np.maximum.reduce([bm[i: i + T] for i in range(4)]) > 10 ** (-100 / 20)
        Msm = 5; Ps = ndimage.uniform_filter1d(P, size=Msm, axis=1); E = Ps.sum(0)
        if valid.sum() < 10: return y
        q = valid & (E <= np.percentile(E[valid], 10)); glob = np.median(Ps[:, q], axis=1)
        Pf = Ps.copy(); Pf[:, ~valid] = glob[:, None]; sub = 4; Pd = Pf[:, ::sub]
        win = max(3, int(c.noise_window_s * sr / hop / sub) | 1)
        Nd = ndimage.percentile_filter(Pd, c.noise_percentile, size=(1, win), mode="nearest")
        m_eff = max(1.0, Msm / 2.5); bias = m_eff / _gamma.ppf(c.noise_percentile / 100.0, m_eff)
        tt = np.arange(T) / sub; N = np.empty_like(P); xs = np.arange(Nd.shape[1])
        for k in range(F): N[k] = np.interp(tt, xs, Nd[k])
        N = N * bias * c.oversub; N = ndimage.uniform_filter1d(N, size=7, axis=0); N = ndimage.gaussian_filter1d(N, sigma=6, axis=1); N = np.maximum(N, 1e-20)
        b1, b2 = np.searchsorted(freqs, [150, 5000])
        snr_db = 10 * np.log10((Ps[b1:b2].sum(0) + 1e-20) / (N[b1:b2].sum(0) + 1e-20))
        vp = np.clip((snr_db - 3.0) / 6.0, 0, 1); vp = ndimage.maximum_filter1d(vp, size=9); vp = ndimage.uniform_filter1d(vp, size=15)
        floor_db = c.gap_reduction_db + (c.reduction_db - c.gap_reduction_db) * vp; floor = 10 ** (-floor_db / 20.0)
        G = np.ones_like(P); Gprev = np.ones(F); gprev = np.ones(F); xi_min = 10 ** (-25 / 10); a = c.dd_alpha; release = 10 ** (-9 / 20)
        for t in range(T):
            if not valid[t]:
                Gprev[:] = floor[t]; gprev[:] = 1.0; G[:, t] = 0.0; continue
            gamma_ = P[:, t] / N[:, t]; xi = a * (Gprev ** 2) * gprev + (1 - a) * np.maximum(gamma_ - 1, 0)
            xi = np.maximum(xi, xi_min); v = xi / (1 + xi) * gamma_
            g = xi / (1 + xi) * np.exp(0.5 * exp1(np.maximum(v, 1e-8)))
            g = np.minimum(g, 1.0); g = ndimage.uniform_filter1d(g, size=3)
            g = np.maximum(g, floor[t]); g = np.maximum(g, Gprev * release)
            G[:, t] = g; Gprev = g; gprev = gamma_
        Y = X * G; _, out = signal.istft(Y, sr, window="hann", nperseg=n, noverlap=n - hop, boundary=True)
        out = out[: len(y)]
        if len(out) < len(y): out = np.pad(out, (0, len(y) - len(out)))
        return out

SCALES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "harmonic_minor": [0, 2, 3, 5, 7, 8, 11], "major_pent": [0, 2, 4, 7, 9], "minor_pent": [0, 3, 5, 7, 10], "blues": [0, 3, 5, 6, 7, 10], "chromatic": list(range(12))}
_KMAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KMIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

PRESETS = {
    "transparent": dict(retune_ms=90, strength=0.65, drift_fix=0.35, vibrato_keep=1.0, tol_cents=12),
    "natural":     dict(retune_ms=40, strength=0.90, drift_fix=0.60, vibrato_keep=1.0, tol_cents=5),
    "studio":      dict(retune_ms=30, strength=0.95, drift_fix=0.70, vibrato_keep=1.0, tol_cents=3),
    "pop":         dict(retune_ms=12, strength=1.00, drift_fix=0.90, vibrato_keep=0.85, tol_cents=0),
    "hard":        dict(retune_ms=3,  strength=1.00, drift_fix=1.00, vibrato_keep=0.0, tol_cents=0),
}

@dataclass
class TunerConfig:
    preset: str = "natural"; key: str | None = None; scale: str | None = None; bpm: float | None = None
    ref_a: float = 440.0; fmin: float = 70.0; fmax: float = 900.0; max_correction_semitones: float = 1.5
    retune_ms: float | None = None; strength: float | None = None; drift_fix: float | None = None
    vibrato_keep: float | None = None; tol_cents: float | None = None; ref_a_auto_dev: float | None = None
    allowed_pcs: list[int] | None = None
    adaptive_speed: bool = True; tuning_mode: str = 'follow'

class PitchCorrector:
    HOP16 = 80; FS16 = 16000
    def __init__(self, preset="natural", **kw):
        self.cfg = TunerConfig(preset=preset, **kw); p = dict(PRESETS[preset])
        for k in p:
            if getattr(self.cfg, k) is not None: p[k] = getattr(self.cfg, k)
        self.p = p; self.info = {}; self.progress_cb = None
    def _prog(self, frac, stage):
        if self.progress_cb:
            try: self.progress_cb(float(min(max(frac, 0.0), 1.0)), stage)
            except Exception: pass
    def track_pitch(self, x, sr):
        c = self.cfg; FS, hop, W, MAXLAG = self.FS16, self.HOP16, 512, 256; g = math.gcd(FS, int(sr))
        x16 = signal.resample_poly(x, FS // g, int(sr) // g); n = len(x16) // hop + 1; xp = np.pad(x16, (320, 448 + hop))
        cm = np.zeros((n, MAXLAG + 2), dtype=np.float32); rms = np.zeros(n); nfft = 1024; CH = 3000
        for s in range(0, n, CH):
            e = min(n, s + CH); idx = (np.arange(s, e) * hop)[:, None] + np.arange(W + MAXLAG)[None, :]
            seg = xp[idx]; a = seg[:, :W]
            R = np.fft.irfft(np.conj(np.fft.rfft(a, nfft, axis=1)) * np.fft.rfft(seg, nfft, axis=1), nfft, axis=1)[:, : MAXLAG + 1]
            E1 = (a ** 2).sum(1)[:, None]; cs = np.concatenate([np.zeros((e - s, 1)), np.cumsum(seg ** 2, axis=1)], axis=1)
            tau = np.arange(MAXLAG + 1); E2 = cs[:, W + tau] - cs[:, tau]; d = E1 + E2 - 2 * R; d[:, 0] = 0
            cum = np.cumsum(d[:, 1:], axis=1); cmn = np.ones_like(d); cmn[:, 1:] = d[:, 1:] * tau[None, 1:] / np.maximum(cum, 1e-12)
            cm[s:e, : MAXLAG + 1] = np.clip(cmn, 0, 2); cm[s:e, MAXLAG + 1] = 1.0; rms[s:e] = np.sqrt(E1[:, 0] / W)
            self._prog(0.15 * e / n, "Analysing pitch")
        bpo = 48; K = int(math.log2(c.fmax / c.fmin) * bpo) + 1; fk = c.fmin * 2 ** (np.arange(K) / bpo)
        tk = FS / fk; lo = np.floor(tk).astype(int); fr = (tk - lo).astype(np.float32)
        cost_v = cm[:, lo] * (1 - fr) + cm[:, lo + 1] * fr; cost_v = cost_v + 0.10 * (tk / MAXLAG)[None, :]
        gate = rms < 10 ** (-58 / 20); cost_v[gate] += 1.0; cost_u = np.full(n, 0.40); cost_u[gate] = 0.0
        J, lam, vu = 8, 0.006, 0.08; pen = lam * np.abs(np.arange(-J, J + 1))
        delta = np.concatenate([cost_v[0], [cost_u[0]]]); bp = np.zeros((n, K + 1), dtype=np.int16); pad = np.full(J, 1e9)
        for t in range(1, n):
            if t % 300 == 0: self._prog(0.15 + 0.45 * t / n, "Tracking pitch")
            pv, pu = delta[:K], delta[K]; win = np.lib.stride_tricks.sliding_window_view(np.concatenate([pad, pv, pad]), 2 * J + 1)
            tot = win + pen[None, :]; am = tot.argmin(1); bv = tot[np.arange(K), am]; prev_idx = np.arange(K) + am - J
            from_u = pu + vu; use_u = from_u < bv; bv = np.where(use_u, from_u, bv); prev_idx = np.where(use_u, K, prev_idx)
            kmin = int(pv.argmin()); to_u_v = pv[kmin] + vu
            if to_u_v < pu: bu, bu_i = to_u_v, kmin
            else: bu, bu_i = pu, K
            new = np.empty(K + 1); new[:K] = bv + cost_v[t]; new[K] = bu + cost_u[t]
            bp[t, :K] = prev_idx; bp[t, K] = bu_i; delta = new
        st = np.zeros(n, dtype=np.int32); st[-1] = int(delta.argmin())
        for t in range(n - 1, 0, -1): st[t - 1] = bp[t, st[t]]
        voiced = st < K; f0 = np.full(n, np.nan); conf = np.zeros(n)
        for t in np.where(voiced)[0]:
            t0 = tk[st[t]]; a_, b_ = int(max(2, t0 * 0.96)), int(min(MAXLAG - 1, t0 * 1.04 + 1))
            seg = cm[t, a_: b_ + 1]; j = int(seg.argmin()) + a_
            if 2 <= j < MAXLAG:
                y0, y1, y2 = cm[t, j - 1], cm[t, j], cm[t, j + 1]; den = y0 - 2 * y1 + y2
                off = 0.5 * (y0 - y2) / den if abs(den) > 1e-9 else 0.0
                f0[t] = FS / (j + np.clip(off, -1, 1)); conf[t] = 1 - cm[t, j]
        v = ~np.isnan(f0); runs = _runs(v); midi = np.full(n, np.nan)
        for s, e in runs:
            if e - s < 8: v[s:e] = False; continue
            m = 69 + 12 * np.log2(f0[s:e] / c.ref_a)
            if e - s >= 5: m = signal.medfilt(m, 5); m[:2], m[-2:] = m[2], m[-3]
            midi[s:e] = m
        runs = _runs(~np.isnan(midi)); meds = [float(np.median(midi[s:e])) for s, e in runs]
        gmed = float(np.median(midi[~np.isnan(midi)])) if runs else 0.0
        for i, (s, e) in enumerate(runs):
            if e - s >= 30: continue
            nb = []
            if i > 0 and s - runs[i - 1][1] <= 60: nb.append(meds[i - 1])
            if i + 1 < len(runs) and runs[i + 1][0] - e <= 60: nb.append(meds[i + 1])
            if (nb and all(abs(meds[i] - m_) > 4.0 for m_ in nb)) or (not nb and abs(meds[i] - gmed) > 7.0): midi[s:e] = np.nan
        v = ~np.isnan(midi); return midi, v, conf, rms
    def estimate_tuning_and_key(self, midi, voiced, conf, segs):
        cen, wt = [], []
        for a_, b_ in segs:
            if b_ - a_ >= 10: cen.append(float(np.median(midi[a_:b_]))); wt.append(math.sqrt(b_ - a_))
        cen, wt = np.array(cen), np.array(wt)
        if len(cen) < 8: cen, wt = midi[voiced], np.ones(voiced.sum())
        z = (wt * np.exp(2j * np.pi * cen)).sum() / wt.sum(); R = abs(z); dev = np.angle(z) / (2 * np.pi)
        n_eff = wt.sum() ** 2 / (wt ** 2).sum(); rayleigh_p = math.exp(-n_eff * R * R)
        use_dev = rayleigh_p < 0.05 and abs(dev) > 0.08; dev_used = dev if use_dev else 0.0
        pc = np.zeros(12); np.add.at(pc, np.round(cen - dev_used).astype(int) % 12, wt); pc = pc / pc.sum()
        scores = []
        for tonic in range(12):
            for mode, prof in (("major", _KMAJ), ("minor", _KMIN)): scores.append((np.corrcoef(pc, np.roll(prof, tonic))[0, 1], tonic, mode))
        scores.sort(reverse=True)
        return dict(tuning_dev_cents=dev * 100, tuning_used_cents=dev_used * 100, tuning_R=float(R), tuning_p=float(rayleigh_p), tonic=scores[0][1], mode=scores[0][2], key_corr=float(scores[0][0]), key_margin=float(scores[0][0] - scores[1][0]), pitch_class_profile=pc.tolist(), runner_up=f"{NOTE_NAMES[scores[1][1]]} {scores[1][2]}")
    def estimate_bpm(self, rms, voiced):
        env = ndimage.uniform_filter1d(np.log(rms + 1e-5), 3); on = np.maximum(np.diff(env, prepend=env[0]), 0)
        on = on - ndimage.uniform_filter1d(on, 100); fps = self.FS16 / self.HOP16; ac = np.correlate(on, on, "full")[len(on) - 1:]
        best, bs = None, -1
        for bpm in np.arange(60, 181, 0.5):
            per = 60 / bpm; s = 0
            for k in (1, 2, 4):
                i = int(round(per * k * fps))
                if i < len(ac): s += ac[i] / (k ** 0.5)
            if s > bs: bs, best = s, bpm
        return float(best), float(bs / (ac[0] + 1e-9))
    def _scale_set(self, tonic, mode_name):
        c = self.cfg; sc = c.scale or mode_name; return sorted({(tonic + d) % 12 for d in SCALES[sc]})
    def _parse_key(self, s):
        parts = s.strip().replace("♯", "#").replace("♭", "b").split(); name = parts[0].capitalize()
        flats = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}; name = flats.get(name, name)
        return NOTE_NAMES.index(name), (parts[1].lower() if len(parts) > 1 else "major")
    def _segment(self, midi, v, bpm):
        sec_per_frame = self.HOP16 / self.FS16; min_note_s = float(np.clip(60.0 / bpm / 8.0, 0.055, 0.12))
        minsep = max(4, int(min_note_s / sec_per_frame)); segs = []
        for s, e in _runs(v):
            m = midi[s:e]; n = len(m); w = 8; cuts = [0]
            if n >= 2 * w + 2:
                cs = np.concatenate([[0], np.cumsum(m)]); t = np.arange(w, n - w + 1)
                before = (cs[t] - cs[t - w]) / w; after = (cs[t + w] - cs[t]) / w; d = after - before
                ad = np.abs(d); pk, _ = signal.find_peaks(ad, height=0.65); order = pk[np.argsort(-ad[pk])]
                acc = []
                for p in order:
                    if all(abs(p - q) >= minsep for q in acc): acc.append(p)
                cuts += sorted(int(t[p]) for p in acc)
            cuts.append(n)
            for a, b in zip(cuts[:-1], cuts[1:]):
                if b - a >= 2: segs.append((s + a, s + b))
        return segs, min_note_s
    def analyse(self, x, sr):
        c = self.cfg; midi, v, conf, rms = self.track_pitch(x, sr)
        bpm, bconf = (c.bpm, 1.0) if c.bpm else self.estimate_bpm(rms, v)
        segs, min_note_s = self._segment(midi, v, bpm); kt = self.estimate_tuning_and_key(midi, v, conf, segs)
        if c.ref_a_auto_dev is not None: kt["tuning_used_cents"] = c.ref_a_auto_dev
        if c.allowed_pcs: tonic, mode = kt["tonic"], kt["mode"]; kt["key_source"] = "mask"; pen = 0.50
        elif c.key and c.key.lower() not in ("auto", "unsure", "unknown", "none", "safe-chromatic"): tonic, mode = self._parse_key(c.key); kt["key_source"] = "user"; pen = 0.40
        else: tonic, mode = kt["tonic"], kt["mode"]; kt["key_source"] = "auto"; pen = float(np.clip((kt["key_margin"] - 0.05) / 0.15, 0.0, 1.0) * 0.40)
        scale_pcs = c.allowed_pcs if c.allowed_pcs else self._scale_set(tonic, mode)
        self.info.update(key=f"{NOTE_NAMES[tonic]} {mode}", scale_notes=[NOTE_NAMES[i] for i in scale_pcs], bpm=round(bpm, 1), bpm_conf=round(bconf, 2), min_note_ms=round(min_note_s * 1000), offscale_penalty_cents=round(pen * 100), voiced_fraction=round(float(v.mean()), 3), runner_up_key=kt["runner_up"], **{k: (round(kt[k], 3) if isinstance(kt[k], float) else kt[k]) for k in ("tuning_dev_cents", "tuning_used_cents", "tuning_p", "key_corr", "key_margin", "key_source")})
        return dict(midi=midi, v=v, conf=conf, rms=rms, segs=segs, scale_pcs=scale_pcs, dev=kt["tuning_used_cents"] / 100.0, bpm=bpm, pen=pen, singer_dev=kt["tuning_dev_cents"] / 100.0, singer_sig=bool(kt["tuning_p"] < 0.05))
    @staticmethod
    def _core(m):
        n = len(m)
        return float(np.median(m[int(0.25 * n):int(0.90 * n)])) if n >= 12 else float(np.median(m))
    def plan_corrections(self, A):
        p, c = self.p, self.cfg; midi, v, segs, scale_pcs, dev, pen = A["midi"], A["v"], A["segs"], A["scale_pcs"], A["dev"], A["pen"]
        n = len(midi); grid = np.arange(20, 110, dtype=float); offscale = np.array([(int(m) % 12) not in scale_pcs for m in grid], dtype=float) * pen
        dt = self.HOP16 / self.FS16; sigma_loc = max(1.0, 0.10 / dt); c_note = np.zeros(n); vib = np.zeros(n); target = np.full(n, np.nan); tau_scale = np.ones(n)
        tol = p["tol_cents"] / 100.0; maxc = c.max_correction_semitones; bias, consist = 0.0, 0.0
        cores = np.array([self._core(midi[a_:b_]) - dev for a_, b_ in segs if b_ - a_ >= 10])
        if len(cores) >= 8:
            w_ = np.array([math.sqrt(b_ - a_) for a_, b_ in segs if b_ - a_ >= 10]); z_ = (w_ * np.exp(2j * np.pi * cores)).sum() / w_.sum()
            consist = float(abs(z_)); b0 = float(np.angle(z_) / (2 * np.pi) * 100.0)
            if b0 > 35.0: b0 -= 100.0
            if consist >= 0.5 and abs(b0) >= 8: bias = float(np.clip(b0, -60.0, 35.0))
        lean = 0.85 * bias / 100.0; drift = min(1.0, p["drift_fix"] + (0.15 if bias < -10 else 0.0))
        self.info["singer_bias_cents"] = round(bias, 1); self.info["singer_consistency"] = round(consist, 2)
        for a, b in segs:
            m = midi[a:b]; c0 = self._core(m); T = grid[np.argmin(np.abs(grid - (c0 - dev - lean)) + offscale)]
            T_abs = T + (dev if c.tuning_mode == 'follow' else 0.0); e = T_abs - c0; e_eff = math.copysign(max(abs(e) - tol, 0.0), e)
            L = ndimage.gaussian_filter1d(m, sigma_loc, mode="nearest") if len(m) > 3 else np.full(len(m), c0)
            c_note[a:b] = np.clip(p["strength"] * (e_eff - drift * (L - c0)), -maxc, maxc); vib[a:b] = m - L; target[a:b] = T_abs
            tau_scale[a:b] = 1.0 + 0.8 * float(np.clip((abs(e_eff) - 0.25) / 0.75, 0.0, 1.0))
        retune_ms = p["retune_ms"]
        if c.adaptive_speed:
            durs = np.array([(b - a) * dt * 1000 for a, b in segs if b - a >= 10])
            if len(durs): med = float(np.median(durs)); retune_ms *= float(np.clip(med / 180.0, 0.5, 1.5)); self.info["median_note_ms"] = round(med)
        self.info["retune_ms_used"] = round(retune_ms, 1); tau = max(retune_ms, 0.5) / 1000.0; alpha = 1 - np.exp(-dt / (tau * tau_scale))
        cs = np.zeros(n)
        for s_, e_ in _runs(v):
            cur = c_note[s_]
            for i in range(s_, e_): cur += (c_note[i] - cur) * alpha[i]; cs[i] = cur
        shift = cs - (1 - p["vibrato_keep"]) * vib; shift = np.clip(shift, -maxc - 0.5, maxc + 0.5); shift[~v] = 0.0
        return shift, target
    def psola(self, x, sr, midi, v, shift):
        sps = sr * self.HOP16 / self.FS16; N = len(x); out = x.copy()
        lp = signal.sosfiltfilt(signal.butter(4, 1200, "lp", fs=sr, output="sos"), x)
        ft = np.arange(len(midi)) * sps; f0 = 440 * 2 ** ((midi - 69) / 12); pad = int(sr * 0.06); xpad = np.pad(x, (pad, pad)); vm = np.zeros(N)
        all_runs = _runs(v); total = max(1, sum(e - s for s, e in all_runs)); done = 0
        for s, e in all_runs:
            self._prog(0.70 + 0.30 * done / total, "Retuning"); done += e - s
            if e - s < 8: continue
            a_, b_ = int(s * sps), min(N - 1, int(e * sps)); per_fr = sr / f0[s:e]; tfr = ft[s:e]
            period = lambda pos: np.interp(pos, tfr, per_fr); T0 = period(a_); seg0 = lp[a_: a_ + int(T0) + 1]; m0 = a_ + int(np.argmax(seg0)); marks = [m0]
            while True:
                m = marks[-1]; T = period(m); h = int(T / 2)
                if m - h < 0 or m + int(1.25 * T) + h + 2 >= N: break
                ref = lp[m - h: m + h + 1]; c0_, c1_ = int(m + 0.78 * T), int(m + 1.22 * T); segc = lp[c0_ - h: c1_ + h + 1]
                if len(segc) < len(ref): break
                cc = np.correlate(segc, ref, "valid"); en = np.cumsum(np.concatenate([[0], segc ** 2])); L = len(ref)
                den = np.sqrt(np.maximum(en[L:] - en[:-L], 1e-18) * max((ref ** 2).sum(), 1e-18)); score = cc / den
                cand = np.arange(c0_, c0_ + len(score)); score = score - 0.15 * np.abs(cand - (m + T)) / T
                nm = int(cand[int(np.argmax(score))])
                if nm <= m: nm = m + int(T)
                marks.append(nm)
                if nm > b_: break
            marks = np.array(marks)
            if len(marks) < 3: continue
            gap = np.diff(marks); lh = np.concatenate([[gap[0]], gap]).astype(int); rh = np.concatenate([gap, [gap[-1]]]).astype(int); span = int(max(lh.max(), rh.max())) + 4
            wet = np.zeros(b_ - a_ + 4 * span + 8); ws = np.zeros_like(wet); base = a_ - 2 * span; ts = float(marks[0]); sh_t = lambda pos: np.interp(pos, tfr, shift[s:e])
            while ts <= b_:
                j = int(np.searchsorted(marks, ts))
                if j >= len(marks): j = len(marks) - 1
                elif j > 0 and abs(marks[j - 1] - ts) <= abs(marks[j] - ts): j -= 1
                Lh, Rh, mk = int(lh[j]), int(rh[j]), int(marks[j]); g = xpad[mk - Lh + pad: mk + Rh + 1 + pad]
                if len(g) != Lh + Rh + 1: break
                win = np.concatenate([np.sin(0.5 * np.pi * np.arange(Lh) / Lh) ** 2, np.cos(0.5 * np.pi * np.arange(Rh + 1) / Rh) ** 2])
                tsi = int(round(ts)); lo = tsi - Lh - base
                if lo >= 0 and lo + Lh + Rh + 1 <= len(wet): wet[lo: lo + Lh + Rh + 1] += g * win; ws[lo: lo + Lh + Rh + 1] += win
                ratio = 2 ** (sh_t(ts) / 12.0); ts += Rh / ratio
            seg_len = b_ - a_; w = wet[a_ - base: a_ - base + seg_len]; ww = ws[a_ - base: a_ - base + seg_len]; ok = ww > 0.25
            wet_n = np.where(ok, w / np.maximum(ww, 0.25), x[a_:b_]); ramp = int(0.010 * sr); mask = np.ones(seg_len); r = min(ramp, seg_len // 2)
            mask[:r] = 0.5 - 0.5 * np.cos(np.pi * np.arange(r) / r); mask[-r:] = mask[:r][::-1]; mask = mask * ok
            out[a_:b_] = x[a_:b_] * (1 - mask) + wet_n * mask; vm[a_ + int(0.012 * sr): max(a_ + int(0.012 * sr), b_ - int(0.012 * sr))] = 1.0
        hp = signal.butter(4, 4000, "hp", fs=sr, output="sos"); xh = signal.sosfiltfilt(hp, x); oh = signal.sosfiltfilt(hp, out); w = max(3, int(0.030 * sr))
        ex = ndimage.uniform_filter1d(xh ** 2, w) + 1e-14; eo = ndimage.uniform_filter1d(oh ** 2, w) + 1e-14
        g = np.clip(np.sqrt(ex / eo), 0.9, 1.8); g = ndimage.uniform_filter1d(g, int(0.020 * sr)); vm = ndimage.uniform_filter1d(vm, int(0.008 * sr))
        return out + oh * (g - 1.0) * vm
    def process(self, x, sr):
        self._prog(0.0, "Analysing pitch"); A = self.analyse(x, sr); self._prog(0.65, "Finding notes"); shift, target = self.plan_corrections(A); self._prog(0.70, "Retuning")
        y = self.psola(np.asarray(x, dtype=np.float64), sr, A["midi"], A["v"], shift); self.info.update(n_notes=len(A["segs"]), avg_lift_cents=round(float(np.mean(shift[A["v"]])) * 100, 1) if A["v"].any() else 0.0)
        self._prog(1.0, "Done"); self._dbg = dict(A, shift=shift, target=target); return y, self.info

def peak_limit(x, sr, ceiling_db=-0.3, look_ms=2.0):
    ceil = 10 ** (ceiling_db / 20); need = np.minimum(1.0, ceil / np.maximum(np.abs(x), 1e-9))
    if need.min() >= 1.0: return x
    w = max(3, int(look_ms * 1e-3 * sr)) | 1; g = ndimage.minimum_filter1d(need, w); g = ndimage.uniform_filter1d(g, w); return x * np.minimum(g, 1.0)
def _runs(mask):
    m = np.concatenate([[0], mask.astype(np.int8), [0]]); d = np.diff(m); return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))
def midi_cents_error(midi, v, scale_pcs, dev=0.0):
    grid = np.array([m for m in range(20, 110) if (m % 12) in scale_pcs], dtype=float); mm = midi[v]; return 100 * (mm - grid[np.abs(grid[None, :] - mm[:, None]).argmin(1)])
