"""dynamics.py - the dynamics Pedalboard lacks. VOCAL BUS ONLY."""
import numpy as np
from scipy import ndimage
from scipy.signal import butter, sosfilt, lfilter


def _env(x, sr, attack_ms=5.0, release_ms=80.0):
    """Attack/release envelope. Vectorised - safe on long files."""
    a = np.abs(np.asarray(x, dtype=np.float32))
    w = max(1, int(sr * float(attack_ms) / 1000.0))
    a = ndimage.maximum_filter1d(a, size=w, mode="nearest")
    r = np.exp(-1.0 / max(1.0, sr * float(release_ms) / 1000.0))
    return lfilter([1.0 - r], [1.0, -r], a).astype(np.float32)


def _db(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-7))


def highpass(x, sr, hz=80.0, order=4):
    return sosfilt(butter(order, hz / (sr * 0.5), btype="highpass",
                          output="sos"), x).astype(np.float32)


def deess(x, sr, low=5500.0, high=8500.0, threshold_db=-24.0,
          max_reduction_db=6.0, ratio=3.0):
    """Real band-limited de-esser: only the sibilant band is attenuated."""
    nyq = sr * 0.5
    sos = butter(4, [low / nyq, min(high, nyq * 0.95) / nyq],
                 btype="bandpass", output="sos")
    band = sosfilt(sos, x).astype(np.float32)
    over = np.maximum(_db(_env(band, sr, 1.5, 55.0)) - threshold_db, 0.0)
    red_db = -np.minimum(over * (1.0 - 1.0 / ratio), max_reduction_db)
    red = (10.0 ** (red_db / 20.0)).astype(np.float32)
    return x + band * (red - 1.0)


def compress(x, sr, threshold_db=-18.0, ratio=3.0,
             attack_ms=8.0, release_ms=90.0, makeup_db=0.0):
    env_db = _db(_env(x, sr, attack_ms, release_ms))
    gain_db = -np.maximum(env_db - threshold_db, 0.0) * (1.0 - 1.0 / ratio) + makeup_db
    return (x * (10.0 ** (gain_db / 20.0))).astype(np.float32)


def duck(beat, vocal, sr, depth_db=-2.0, band=(2000.0, 5000.0),
         attack_ms=8.0, release_ms=180.0):
    """Vocal-triggered duck of the beat's vocal band ONLY - 808 untouched."""
    nyq = sr * 0.5
    sos = butter(4, [band[0] / nyq, min(band[1], nyq * 0.95) / nyq],
                 btype="bandpass", output="sos")
    key = np.asarray(vocal, dtype=np.float32)
    if key.ndim > 1:
        key = key.mean(axis=0)
    key_db = _db(_env(key, sr, attack_ms, release_ms))
    norm = np.clip((key_db - key_db.max() + 6.0) / -60.0, 0.0, 1.0)
    g = (10.0 ** ((norm * depth_db) / 20.0)).astype(np.float32)
    b = np.asarray(beat, dtype=np.float32)
    band_beat = sosfilt(sos, b).astype(np.float32)
    return b + band_beat * (g - 1.0)


def process_vocal(x, sr, hp_hz=80.0, do_deess=True, do_comp=True):
    a = np.asarray(x, dtype=np.float32)
    single = a.ndim == 1
    if single:
        a = a[None, :]
    out = np.empty_like(a)
    for ch in range(a.shape[0]):
        v = highpass(a[ch], sr, hp_hz) if hp_hz else a[ch]
        if do_deess:
            v = deess(v, sr)
        if do_comp:
            v = compress(v, sr)
        out[ch] = v
    return out[0] if single else out
