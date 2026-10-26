"""
Flat-vocal corrector: a gentle pre-stage that runs BEFORE your own auto-tune.
It does NOT snap notes to a scale. It only brings flat notes back up to where the singer meant them:
  - locks the vocal to the track's tuning (beat reference, else A=440), not to the singer's own flat centre
  - reads each note from its stable middle (ignores scoop-in / sag-out) and leans the note choice upward for flat singers
  - lifts flat notes and removes end-of-note sag; sharp notes are only touched lightly (your auto-tune handles those)
  - bypasses itself (returns the input untouched) when the take isn't actually flat
"""
import numpy as np
from vocal_dsp import PitchCorrector

PREP = dict(retune_ms=55, strength=0.85, drift_fix=0.70, vibrato_keep=1.0, tol_cents=8)


def fix_flat(x, sr, ref_cents=0.0, key="auto", sharp_ratio=0.5, bypass_below=0.15, progress_cb=None):
    """x: mono float array. ref_cents: beat tuning vs A=440 (0 if unknown). key: beat key like "C minor" or "auto".
    returns (y, info). info["bypassed"] is True when nothing was changed."""
    x = np.asarray(x, dtype=np.float64)
    pc = PitchCorrector(preset="studio", key=key, ref_a_auto_dev=ref_cents, **PREP)
    pc.progress_cb = progress_cb
    A = pc.analyse(x, sr)
    shift, target = pc.plan_corrections(A)

    # how many notes are really flat (target above the sung core by more than 12 cents), weighted by length
    fl, wt = [], []
    for a, b in A["segs"]:
        if b - a >= 10:
            core = pc._core(A["midi"][a:b])
            fl.append(100.0 * (np.nanmedian(target[a:b]) - core) > 12.0)
            wt.append(b - a)
    flat_frac = float(np.average(fl, weights=wt)) if fl else 0.0
    info = dict(pc.info, flat_fraction=round(flat_frac, 3), bypassed=False)
    if flat_frac < bypass_below and info.get("singer_bias_cents", 0.0) > -8.0:
        info.update(bypassed=True, avg_lift_cents=0.0)
        return x, info

    shift = np.where(shift > 0, shift, shift * sharp_ratio)        # lift flat notes fully, touch sharp ones lightly
    y = pc.psola(x, sr, A["midi"], A["v"], shift)
    info["avg_lift_cents"] = round(float(np.mean(shift[A["v"]])) * 100, 1) if A["v"].any() else 0.0
    if progress_cb:
        progress_cb(1.0, "Done")
    return y, info
