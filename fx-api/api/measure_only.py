import pathlib, sys

# ============ auto.py ============
auto = pathlib.Path("auto.py")
a_text = auto.read_text()
a_changes = 0

# --- Widen: measure side/mid, log, then widen normally (audio unchanged) ---
OLD_W = '    mixed = _widen(mixed, sr, float(_PRESET.get("width") or 1.0))'
NEW_W = '''    _w = float(_PRESET.get("width") or 1.0)
    try:
        if mixed.shape[0] >= 2:
            _m = (mixed[0] + mixed[1]) * 0.5
            _s = (mixed[0] - mixed[1]) * 0.5
            _rm = float(np.sqrt(np.mean(_m**2)))
            _rs = float(np.sqrt(np.mean(_s**2)))
            _sm = 20.0 * np.log10(max(1e-9, _rs) / max(1e-9, _rm))
            rep["widen_probe"] = {"width_wanted": _w, "sm_db": round(_sm, 2),
                                  "gate_would_fire": bool(_sm < -14.0)}
    except Exception as _we:
        rep["widen_probe_error"] = str(_we)[:120]
    mixed = _widen(mixed, sr, _w)   # AUDIO PATH UNCHANGED'''

if a_text.count(OLD_W) == 1:
    a_text = a_text.replace(OLD_W, NEW_W); a_changes += 1
    print("OK: widen probe inserted")
elif a_text.count(OLD_W) == 0:
    print("SKIP: widen anchor not found")
else:
    print("SKIP: widen anchor matched %d times" % a_text.count(OLD_W))

if a_changes:
    auto.with_suffix(".py.bak2").write_text(pathlib.Path("auto.py").read_text())
    auto.write_text(a_text)
    print("auto.py: %d change(s) applied (measurement only)" % a_changes)
else:
    print("auto.py: no changes")

# ============ mix.py ============
mx = pathlib.Path("mix.py")
m_text = mx.read_text()
m_changes = 0

# --- Master pre-check: measure input peak + clipping, log only ---
OLD_P = '''        report["mid_cut_db"] = _mc
        report["mid_cut_hz"] = 250.0
        if mode == "master":'''
NEW_P = '''        report["mid_cut_db"] = _mc
        report["mid_cut_hz"] = 250.0
        try:
            _in_peak = peakdb(mixed)
            _in_clip = int(np.count_nonzero(np.abs(mixed) >= 0.999))
            _would_reduce = 0.0
            if _in_peak > -1.0:
                _would_reduce = -1.0 - _in_peak
            if _in_clip > 0 and _would_reduce > -0.5:
                _would_reduce = -0.5
            report["precheck_probe"] = {"peak_db_in": round(_in_peak, 2),
                                        "clipped_in": _in_clip,
                                        "would_reduce_db": round(_would_reduce, 2),
                                        "would_fire": bool(_would_reduce < -0.05)}
        except Exception as _pce:
            report["precheck_probe_error"] = str(_pce)[:120]
        if mode == "master":'''

if m_text.count(OLD_P) == 1:
    m_text = m_text.replace(OLD_P, NEW_P); m_changes += 1
    print("OK: master precheck probe inserted")
elif m_text.count(OLD_P) == 0:
    print("SKIP: master precheck anchor not found")
else:
    print("SKIP: master precheck anchor matched %d times" % m_text.count(OLD_P))

# --- Limiter GR: measure pre/post loudness delta, log only ---
OLD_L = '''        _dyn_pre = _dyn9010(mixed, sr)
        mixed, tp, brick = auto.limit(mixed, sr, auto.CEILING_DB)
        _fin = lufs(mixed, sr)
        _dyn_post = _dyn9010(mixed, sr)'''
NEW_L = '''        _dyn_pre = _dyn9010(mixed, sr)
        _lufs_before_limit = lufs(mixed, sr)
        _peak_before_limit = peakdb(mixed)
        mixed, tp, brick = auto.limit(mixed, sr, auto.CEILING_DB)
        _fin = lufs(mixed, sr)
        _dyn_post = _dyn9010(mixed, sr)
        try:
            _gr_lufs = None if (_lufs_before_limit is None or _fin is None) else round(_lufs_before_limit - _fin, 2)
            _gr_peak = round(_peak_before_limit - peakdb(mixed), 2)
            report["limiter_probe"] = {"lufs_before": _lufs_before_limit,
                                       "lufs_after": _fin,
                                       "peak_before": round(_peak_before_limit, 2),
                                       "peak_after": round(peakdb(mixed), 2),
                                       "gr_lufs": _gr_lufs,
                                       "gr_peak": _gr_peak}
        except Exception as _le:
            report["limiter_probe_error"] = str(_le)[:120]'''

if m_text.count(OLD_L) == 1:
    m_text = m_text.replace(OLD_L, NEW_L); m_changes += 1
    print("OK: limiter probe inserted")
elif m_text.count(OLD_L) == 0:
    print("SKIP: limiter anchor not found")
else:
    print("SKIP: limiter anchor matched %d times" % m_text.count(OLD_L))

if m_changes:
    mx.with_suffix(".py.bak2").write_text(pathlib.Path("mix.py").read_text())
    mx.write_text(m_text)
    print("mix.py: %d change(s) applied (measurement only)" % m_changes)
else:
    print("mix.py: no changes")

print("done")
