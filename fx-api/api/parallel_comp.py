"""NY-style parallel compression. Additive blend, no dry attenuation."""
import numpy as np
from pedalboard import Pedalboard, Compressor, Gain, HighpassFilter


def industry_parallel_compressor(x, sr, blend_amount=0.30):
    dry = np.asarray(x, dtype=np.float32).copy()
    if dry.ndim != 2 or dry.shape[1] == 0:
        return x

    smash = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=120.0),
        Compressor(threshold_db=-32.0, ratio=12.0,
                   attack_ms=0.5, release_ms=60.0),
        Gain(gain_db=14.0),
    ])
    wet = smash(dry, int(sr)).astype(np.float32)

    out = (dry + wet * float(blend_amount)).astype(np.float32)
    pk = float(np.max(np.abs(out)))
    if pk > 0.95:
        out = (out * (0.95 / pk)).astype(np.float32)
    return out
