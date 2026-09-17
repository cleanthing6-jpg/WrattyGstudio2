"""WrattyG chains - Afrobeats / Suno-like polish. Additive file."""
import numpy as np
from pedalboard import (
    Pedalboard, Mix, Gain, Compressor, Limiter,
    HighpassFilter, LowpassFilter, PeakFilter,
    Clipping, Chorus, Reverb, Convolution, Delay, PitchShift,
)
try:
    from pedalboard import HighShelfFilter as HighshelfFilter
except ImportError:
    from pedalboard import HighshelfFilter
try:
    from pedalboard import LowShelfFilter as LowshelfFilter
except ImportError:
    from pedalboard import LowshelfFilter

BPM = 120.0


def _plug(cls, **kw):
    try:
        return cls(**kw)
    except TypeError:
        for d in ("q", "mix", "width", "dry_level", "wet_level", "freeze_mode"):
            kw.pop(d, None)
            try:
                return cls(**kw)
            except TypeError:
                continue
        raise


def plate(ir=None):
    if ir is not None:
        return _plug(Convolution, impulse_response=np.asarray(ir, dtype=np.float32))
    return _plug(Reverb, room_size=0.35, damping=0.65,
                 wet_level=1.0, dry_level=0.0, width=1.0)


def _send(effects, level_db, hpf=250.0, lpf=8000.0):
    return Pedalboard([HighpassFilter(cutoff_frequency_hz=hpf), *effects,
                       LowpassFilter(cutoff_frequency_hz=lpf),
                       _plug(Gain, gain_db=level_db)])


def _sends(insert, ir, bpm, reverb_db, delay_db):
    return Pedalboard([
        insert,
        Mix([
            Gain(gain_db=0.0),
            _send([plate(ir)], reverb_db),
            _send([_plug(Delay, delay_seconds=60.0 / bpm, feedback=0.30, mix=1.0)],
                  delay_db, hpf=300.0, lpf=6000.0),
        ]),
    ])


def lead_board(ir=None, bpm=BPM, reverb_db=-16.0, delay_db=-24.0):
    return _sends(Pedalboard([
        HighpassFilter(cutoff_frequency_hz=90.0),
        PeakFilter(cutoff_frequency_hz=300.0, gain_db=-2.5, q=0.9),
        LowshelfFilter(cutoff_frequency_hz=180.0, gain_db=1.0, q=0.7),
        PeakFilter(cutoff_frequency_hz=3000.0, gain_db=1.5, q=1.2),
        Compressor(threshold_db=-22.0, ratio=3.0, attack_ms=12.0, release_ms=80.0),
        Clipping(threshold_db=-3.0),
        Compressor(threshold_db=-14.0, ratio=2.0, attack_ms=25.0, release_ms=120.0),
        HighshelfFilter(cutoff_frequency_hz=10000.0, gain_db=3.0, q=0.7),
        Gain(gain_db=-1.5),
    ]), ir, bpm, reverb_db, delay_db)


def autotuned_lead_board(ir=None, bpm=BPM, reverb_db=-16.0, delay_db=-24.0):
    return _sends(Pedalboard([
        HighpassFilter(cutoff_frequency_hz=90.0),
        PeakFilter(cutoff_frequency_hz=300.0, gain_db=-2.5, q=0.9),
        LowshelfFilter(cutoff_frequency_hz=180.0, gain_db=1.0, q=0.7),
        PeakFilter(cutoff_frequency_hz=3000.0, gain_db=1.0, q=1.2),
        Compressor(threshold_db=-22.0, ratio=3.0, attack_ms=12.0, release_ms=80.0),
        Clipping(threshold_db=-3.0),
        Compressor(threshold_db=-14.0, ratio=2.0, attack_ms=25.0, release_ms=120.0),
        HighshelfFilter(cutoff_frequency_hz=10000.0, gain_db=1.5, q=0.7),
        Gain(gain_db=-1.5),
    ]), ir, bpm, reverb_db, delay_db)


def processed_lead_board(ir=None, bpm=BPM, **kw):
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=80.0),
        PeakFilter(cutoff_frequency_hz=280.0, gain_db=-1.5, q=0.9),
        Compressor(threshold_db=-18.0, ratio=1.7, attack_ms=25.0, release_ms=120.0),
    ])


def backing_board(ir=None, bpm=BPM, reverb_db=-13.0):
    ins = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=120.0),
        PeakFilter(cutoff_frequency_hz=400.0, gain_db=-3.0, q=0.9),
        Compressor(threshold_db=-26.0, ratio=4.0, attack_ms=8.0, release_ms=70.0),
        Chorus(rate_hz=0.35, depth=0.12, centre_delay_ms=10.0, feedback=0.0, mix=0.15),
        HighshelfFilter(cutoff_frequency_hz=9000.0, gain_db=2.0, q=0.7),
        Gain(gain_db=-6.0),
    ])
    return Pedalboard([ins, Mix([Gain(gain_db=0.0),
                         _send([plate(ir)], reverb_db, hpf=300.0, lpf=7000.0)])])


def processed_backing_board(ir=None, bpm=BPM, **kw):
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=110.0),
        Compressor(threshold_db=-22.0, ratio=2.0, attack_ms=15.0, release_ms=90.0),
        Gain(gain_db=-6.0),
    ])


def adlib_board(ir=None, bpm=BPM, reverb_db=-10.0, delay_db=-16.0):
    return _sends(Pedalboard([
        HighpassFilter(cutoff_frequency_hz=140.0),
        Compressor(threshold_db=-24.0, ratio=3.0, attack_ms=10.0, release_ms=90.0),
        Clipping(threshold_db=-4.0),
        Chorus(rate_hz=0.5, depth=0.18, centre_delay_ms=8.0, feedback=0.0, mix=0.22),
        HighshelfFilter(cutoff_frequency_hz=9000.0, gain_db=2.0, q=0.7),
        Gain(gain_db=-9.0),
    ]), ir, bpm, reverb_db, delay_db)


def processed_adlib_board(ir=None, bpm=BPM, **kw):
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=130.0),
        Compressor(threshold_db=-22.0, ratio=2.0, attack_ms=12.0, release_ms=90.0),
        Gain(gain_db=-9.0),
    ])


def harmony(semitones=-12.0):
    return Pedalboard([PitchShift(semitones=float(semitones)), Gain(gain_db=-8.0)])


def beat_board(pocket_db=-1.0):
    return Pedalboard([PeakFilter(cutoff_frequency_hz=3000.0, gain_db=pocket_db, q=0.8)])


def beat_gain_db(beat_peak_dbfs, target_dbfs=-6.0):
    return min(0.0, float(target_dbfs) - float(beat_peak_dbfs))


def glue_bus():
    return Pedalboard([
        Compressor(threshold_db=-18.0, ratio=2.0, attack_ms=30.0, release_ms=120.0),
        Gain(gain_db=-1.0),
        Limiter(threshold_db=-1.0, release_ms=100.0),
    ])


BOARDS = {
    "raw": {"lead": lead_board, "backups": backing_board,
            "adlibs": adlib_board, "beat": beat_board},
    "autotuned": {"lead": autotuned_lead_board, "backups": processed_backing_board,
                  "adlibs": adlib_board, "beat": beat_board},
    "processed": {"lead": processed_lead_board, "backups": processed_backing_board,
                  "adlibs": processed_adlib_board, "beat": beat_board},
}


def classify_vocal(audio, sr):
    x = np.asarray(audio, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=0)
    peak = float(np.max(np.abs(x))) + 1e-9
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2))) + 1e-9
    crest_db = 20.0 * np.log10(peak / rms)
    n = min(len(x), sr * 20) or len(x)
    spec = np.abs(np.fft.rfft(x[:n].astype(np.float64)))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    hi = float(spec[freqs > 6000.0].sum()) / (float(spec.sum()) + 1e-9)
    return "processed" if (crest_db < 8.0 or hi > 0.06) else "autotuned"


def apply(role, audio, sr, treatment="autotuned", ir=None, bpm=BPM, **kw):
    table = BOARDS.get(treatment, BOARDS["autotuned"])
    mk = table.get(role, beat_board)
    if role == "beat":
        return mk(**kw)(audio, sr)
    return mk(ir=ir, bpm=bpm, **kw)(audio, sr)
