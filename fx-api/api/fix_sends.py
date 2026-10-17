from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

# 1. Apply delay_scale to dly_wet (was ignored)
old1 = '''    if role is not None:
        _DELAY_LAST[role] = dly_info
    base = (voc + wet) if dly_wet is None else (voc + wet + dly_wet)
    return base.astype(np.float32), 0, "plate"'''
new1 = '''    if role is not None:
        _DELAY_LAST[role] = dly_info
    if dly_wet is not None:
        _dsc = float(delay_scale) if delay_scale is not None else 1.0
        dly_wet = (dly_wet * _dsc).astype(np.float32)
        try:
            import numpy as _np
            _dry_rms = float(_np.sqrt(_np.mean(np.asarray(voc, np.float32)**2)) + 1e-12)
            _wet_rms = float(_np.sqrt(_np.mean(np.asarray(dly_wet, np.float32)**2)) + 1e-12)
            dly_info["wet_db_rel_dry"] = round(20.0*_np.log10(_wet_rms/_dry_rms + 1e-12), 2)
        except Exception:
            pass
        _DELAY_LAST[role] = dly_info
    try:
        import numpy as _np
        _dry_rms_p = float(_np.sqrt(_np.mean(np.asarray(voc, np.float32)**2)) + 1e-12)
        _wet_rms_p = float(_np.sqrt(_np.mean(np.asarray(wet, np.float32)**2)) + 1e-12)
        _REVERB_LAST["plate_db_rel_dry"] = round(20.0*_np.log10(_wet_rms_p/_dry_rms_p + 1e-12), 2)
    except Exception:
        pass
    base = (voc + wet) if dly_wet is None else (voc + wet + dly_wet)
    return base.astype(np.float32), 0, "plate"'''

n = s.count(old1)
if n != 1:
    sys.exit("ABORT: send anchor matched %d (need 1)" % n)
s = s.replace(old1, new1, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  delay_scale now applied + wet level logged")
print("SYNTAX OK")
