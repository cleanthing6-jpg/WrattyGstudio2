#!/usr/bin/env python3
"""
patch_corr_guard.py  -  adds ONE small adaptive stage to your deployed master_bus.py:

  stage_corr_guard: if (and only if) the FINISHED master (after clipper + limiter) is wider than the reference correlation floor
  (default 0.865, reference range 0.86-0.91), the side channel is narrowed by the MINIMUM amount that reaches the floor.
  It never narrows more than 1.2 dB, never takes the side level below -9.0 dB (reference range -9.4 to -6.9), does nothing
  for genres that have no measured reference, and does nothing when the correlation is already fine.

Usage:   python3 patch_corr_guard.py ~/WrattyGstudio2/fx-api/api/master_bus.py
Safe:    checks anchors, keeps a .bak copy, compiles the result, restores the backup if anything fails. Re-running is harmless.
Off:     pass corr_floor=0.0 in the master() call (or preset) to disable.
"""
import sys, shutil, py_compile

FUNC = '''def stage_corr_guard(x, sr, floor, rep, max_db=1.2, side_min_db=-9.0):
    """Narrow the side channel only as much as needed to bring L/R correlation up to `floor`."""
    L, R = x[0].astype(np.float64), x[1].astype(np.float64)
    M, S = (L + R) / 2.0, (L - R) / 2.0
    Pm, Ps, Cms = float(np.mean(M * M)), float(np.mean(S * S)), float(np.mean(M * S))

    def corr(f):
        plr = Pm - f * f * Ps
        pl, pr = Pm + f * f * Ps + 2 * f * Cms, Pm + f * f * Ps - 2 * f * Cms
        return plr / np.sqrt(max(pl * pr, 1e-30))

    c0 = corr(1.0)
    info = {"before": round(c0, 3), "floor": floor}
    if c0 >= floor or Ps <= 0:
        info["action"] = "none (correlation already at or above the floor)"
        rep["corr_guard"] = info
        return x
    f_min = 10 ** (-max_db / 20.0)
    try:
        s0 = _side_db(x, sr)
        f_min = max(f_min, 10 ** ((side_min_db - s0) / 20.0))            # never push the side level below side_min_db
    except Exception:
        pass
    lo, hi = min(f_min, 1.0), 1.0
    if corr(lo) < floor:
        f, info["limited_by"] = lo, "max narrowing / side-level floor"
    else:
        for _ in range(30):                                              # largest f (least narrowing) that still reaches the floor
            mid = (lo + hi) / 2.0
            lo, hi = (mid, hi) if corr(mid) >= floor + 0.002 else (lo, mid)
        f = lo
    out = np.stack([M + f * S, M - f * S])
    info.update(action="narrowed", side_cut_db=round(20 * np.log10(f), 2), after=round(corr(f), 3),
                lufs_change_db=round(lufs(out, sr) - lufs(x, sr), 2))
    rep["corr_guard"] = info
    return out


'''
CALL = '''    if prof is not None and float(p.get("corr_floor", 0.865)) > 0:      # reference-genre only; adaptive, usually a no-op
        y = stage_corr_guard(y, sr, float(p.get("corr_floor", 0.865)), rep)
        _tp = true_peak_db(y, sr)
        if _tp > p["ceil"]:                                              # narrowing can move peaks by a hair: keep the ceiling
            y = y * 10 ** ((p["ceil"] - _tp - 0.01) / 20)
'''
def main(path):
    src = open(path).read()
    if "def stage_corr_guard" in src:
        print("already patched - nothing to do"); return 0
    a1, a2 = "def master(", "    rep[\"output\"] = qc(y, sr"
    if src.count(a1) != 1 or src.count(a2) < 1 or "prof" not in src or "_side_db" not in src or "def true_peak_db" not in src:
        print("ABORT: expected anchors not found (def master / rep[\"output\"] = qc / prof / _side_db / true_peak_db). Nothing was changed."); return 1
    shutil.copy(path, path + ".bak")
    i = src.index(a1)
    out = src[:i] + FUNC + src[i:]
    j = out.index(a2, out.index(a1, i + len(FUNC)))
    out = out[:j] + CALL + out[j:]
    open(path, "w").write(out)
    try:
        py_compile.compile(path, doraise=True)
    except Exception as e:
        shutil.copy(path + ".bak", path); print("ABORT: patched file did not compile, original restored:", e); return 1
    print("PATCHED OK (backup: %s.bak)" % path); return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv) > 1 else print(__doc__) or 1)
