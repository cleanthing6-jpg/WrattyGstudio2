import numpy as np
from vocal_dsp import PitchCorrector
PREP = dict(retune_ms=55, strength=0.85, drift_fix=0.70, vibrato_keep=1.0, tol_cents=8)
def fix_flat(x, sr, ref_cents=0.0, key="auto", sharp_ratio=0.5, bypass_below=0.15, progress_cb=None):
    x = np.asarray(x, dtype=np.float64); pc = PitchCorrector(preset="studio", key=key, ref_a_auto_dev=ref_cents, **PREP)
    pc.progress_cb = progress_cb; A = pc.analyse(x, sr); shift, target = pc.plan_corrections(A)
    fl, wt = [], []
    for a, b in A["segs"]:
        if b - a >= 10:
            core = pc._core(A["midi"][a:b]); fl.append(100.0 * (np.nanmedian(target[a:b]) - core) > 12.0); wt.append(b - a)
    flat_frac = float(np.average(fl, weights=wt)) if fl else 0.0; info = dict(pc.info, flat_fraction=round(flat_frac, 3), bypassed=False)
    if flat_frac < bypass_below and info.get("singer_bias_cents", 0.0) > -8.0:
        info.update(bypassed=True, avg_lift_cents=0.0); return x, info
    shift = np.where(shift > 0, shift, shift * sharp_ratio); y = pc.psola(x, sr, A["midi"], A["v"], shift)
    info["avg_lift_cents"] = round(float(np.mean(shift[A["v"]])) * 100, 1) if A["v"].any() else 0.0
    if progress_cb: progress_cb(1.0, "Done")
    return y, info
