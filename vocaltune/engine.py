"""High-level API:  VocalTuner().process(audio, sr, genre=..., beat=...) -> TuneResult"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
import numpy as np
from . import dsp, theory, quality as Q, rescue as R
from .pitch import track_pitch, PitchTrack
from .control import Settings, compute_correction, Correction
from .presets import make_settings
from .psola import psola_correct, spectral_restore
from .resplice import resplice_correct

@dataclass
class TuneResult:
    audio: np.ndarray
    sr: int
    quality: Q.Quality
    key: str
    scale_notes: list
    tuning_cents: float
    settings: Settings
    notes: list
    track: PitchTrack
    correction: Correction
    warnings: list = field(default_factory=list)
    info: dict = field(default_factory=dict)

def _adapt(st: Settings, q: Q.Quality, voiced_conf_mean: float, singer_err: float, warnings: list):
    s = replace(st)
    if q.profile == "poor":
        s.amount *= 0.70; s.retune_ms = max(s.retune_ms, 45); s.humanize = max(s.humanize, 0.5)
        s.vibrato_keep = max(s.vibrato_keep, 0.9); s.conf_gate = (0.60, 0.88); s.max_shift_cents = min(s.max_shift_cents, 120)
    elif q.profile == "phone":
        s.amount *= 0.88; s.retune_ms = max(s.retune_ms, 22); s.conf_gate = (0.52, 0.84)
        s.max_shift_cents = min(s.max_shift_cents, 160)
    elif q.profile == "good":
        s.conf_gate = (0.48, 0.82)
    if voiced_conf_mean < 0.75:
        s.conf_gate = (s.conf_gate[0] + 0.06, s.conf_gate[1] + 0.04)
        warnings.append(f"pitch tracker confidence is low ({voiced_conf_mean:.2f}); correction is being held back on uncertain frames")
    if singer_err < 10:
        s.flex_cents = max(s.flex_cents, 14.0)
    return s

class VocalTuner:
    def __init__(self, hop_ms: float = 5.0):
        self.hop_ms = hop_ms

    def analyze(self, audio, sr, beat=None, beat_sr=None, key=None, mode=None, scale=None,
                tuning_cents=None, vocal_range=(65.0, 1000.0)):
        x = np.asarray(audio, dtype=np.float64)
        mono = dsp.to_mono(x)
        qual = Q.analyze_quality(mono, sr)
        an = dsp.zero_phase(mono, dsp.butter_sos("highpass", 70.0, sr, 4))
        if qual.profile in ("phone", "poor") or qual.snr_db < 26:
            an = R.rescue(mono, sr, qual, strength=0.8 if qual.profile != "good" else 0.5)
        track = track_pitch(an, sr, fmin=vocal_range[0], fmax=vocal_range[1], hop_ms=self.hop_ms)
        f0, conf, voiced = track.f0.copy(), track.conf.copy(), track.voiced.copy()
        if voiced.sum() > 50:
            med = np.median(f0[voiced & (conf > 0.8)]) if np.any(voiced & (conf > 0.8)) else np.median(f0[voiced])
            far = voiced & ((f0 > med * 3.2) | (f0 < med / 2.4)) & (conf < 0.8)
            voiced &= ~far; f0[~voiced] = 0.0; conf[~voiced] = 0.0
        track = PitchTrack(track.hop, track.sr, f0, conf, voiced)
        self._analysis_signal = an
        return mono, qual, track

    def process(self, audio, sr, genre="afrobeats", beat=None, beat_sr=None, key=None, mode=None, scale=None,
                tuning_cents=None, adaptive=True, key_map=None, restore_spectrum=False, shifter='resplice', **overrides) -> TuneResult:
        warnings: list = []
        x = np.asarray(audio, dtype=np.float64)
        mono, qual, track = self.analyze(audio, sr)
        hop_s = track.hop / sr
        v = track.voiced
        if v.sum() < 30:
            warnings.append("almost no voiced content detected; returning audio unchanged")
            return TuneResult(x.astype(np.float32), sr, qual, "n/a", [], 0.0, make_settings(genre), [], track,
                              Correction(np.zeros(len(track.f0)), np.full(len(track.f0), np.nan), np.full(len(track.f0), np.nan), [], hop_s), warnings)
        info = {}
        if tuning_cents is None:
            if beat is not None:
                bsr = beat_sr or sr
                bm = dsp.to_mono(beat)
                tuning_cents, tconf = theory.estimate_tuning_cents(bm, bsr)
                info["beat_tuning_conf"] = tconf
                if tconf < 0.25:
                    warnings.append("beat tuning estimate is weak; falling back to A=440")
                    tuning_cents = 0.0
            else:
                tuning_cents = 0.0
        vhist = theory.pitchclass_hist_from_f0(track.f0, weights=track.conf, tuning_cents=tuning_cents)
        key_src = "user"
        if key is None:
            ke_v = theory.detect_key(vhist)
            ke = ke_v; key_src = "vocal"
            if beat is not None:
                ch = theory.chroma_from_audio(dsp.to_mono(beat), beat_sr or sr, tuning_cents)
                ke_b = theory.detect_key(ch)
                info["key_beat"] = ke_b.name; info["key_vocal"] = ke_v.name
                info["key_beat_score"] = ke_b.score; info["key_beat_margin"] = ke_b.margin
                if ke_b.score >= 0.60 and ke_b.margin >= 0.04:
                    ke = ke_b; key_src = "beat"
                else:
                    warnings.append("beat key is ambiguous; using the vocal's own pitch-class profile")
            else:
                info["key_vocal"] = ke_v.name
                if ke_v.margin < 0.03:
                    warnings.append("key estimated from the vocal alone and is ambiguous - supply `key`/`mode` or a beat")
            key, mode = ke.key, ke.mode
        mode = mode or "major"
        base = scale or mode
        allowed = theory.adaptive_allowed(key, mode, None, base_scale=base)
        if scale is None:
            c = 1200 * np.log2(np.maximum(track.f0, 1) / 440.0) - tuning_cents
            steady = v & (track.conf > 0.85)
            dev = (c - 100 * np.round(c / 100.0))
            pcs = (np.round(c / 100.0).astype(int) + 9) % 12
            tight = steady & (np.abs(dev) < 14)
            for pc in range(12):
                if allowed[pc]:
                    continue
                if np.sum(tight & (pcs == pc)) > 0.07 * max(np.sum(steady), 1):
                    allowed[pc] = True; info.setdefault("blue_notes", []).append(theory.NOTE_NAMES[pc])
        st = make_settings(genre, **overrides)
        probe = compute_correction(track.f0, track.conf, v, hop_s, allowed, tuning_cents, key, mode,
                                   replace(st, amount=0.0))
        errs = np.array([abs(nt.deviation_cents) for nt in probe.notes if (nt.end - nt.start) * hop_s > 0.12]) if probe.notes else np.array([0.0])
        singer_err = float(np.median(errs)) if len(errs) else 0.0
        if adaptive:
            st = _adapt(st, qual, float(track.conf[v].mean()), singer_err, warnings)
        if singer_err > 42:
            warnings.append(f"vocal sits ~{singer_err:.0f} c from the chosen grid on average; check key / reference or expect heavy correction")
        corr = compute_correction(track.f0, track.conf, v, hop_s, allowed, tuning_cents, key, mode, st)
        fr = 2.0 ** (st.formant_shift_semitones / 12.0)
        big_run = np.zeros(len(v), bool)
        d = np.diff(np.r_[0, v.astype(np.int8), 0])
        for a, b in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            if shifter != "resplice" or abs(st.formant_shift_semitones) > 0 or np.max(np.abs(corr.shift_cents[a:b])) > 160.0:
                big_run[a:b] = True
        out = x.copy(); pd = {}
        if (v & ~big_run).any():
            out, pd = resplice_correct(out, sr, track.f0, v & ~big_run, corr.shift_cents, track.hop, min_shift=st.min_shift_to_process,
                                       return_diag=True, mark_signal=self._analysis_signal)
        if (v & big_run).any():
            out, pd2 = psola_correct(out, sr, track.f0, v & big_run, corr.shift_cents, track.hop, formant_ratio=fr,
                                     min_shift=st.min_shift_to_process, return_diag=True, mark_signal=self._analysis_signal)
            pd = {**pd2, **{k: pd.get(k, 0) for k in ("splices",)}, "mask": np.maximum(pd.get("mask", 0), pd2["mask"])} if pd else pd2
        if restore_spectrum:
            out = spectral_restore(x, out, sr, pd['mask'])
        pd = {k: v for k, v in pd.items() if k != 'mask'}
        info.update({"key_source": key_src, "psola": pd, "singer_median_error_cents": singer_err})
        scale_notes = [theory.NOTE_NAMES[i] for i in range(12) if allowed[i]]
        return TuneResult(out.astype(np.float32), sr, qual, f"{theory.NOTE_NAMES[key]} {mode}", scale_notes, float(tuning_cents),
                          st, corr.notes, track, corr, warnings, info)
