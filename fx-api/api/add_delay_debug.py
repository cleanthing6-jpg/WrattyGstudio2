from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''            _dy, _dinfo = _spec_render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))
                if _dy is not None:'''
new = '''            _dy, _dinfo = _spec_render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))
                if _dy is not None:
                    try:
                        import numpy as _np
                        _dry_rms = float(_np.sqrt(_np.mean(np.asarray(voc, np.float32)**2)) + 1e-12)
                        _wet_rms = float(_np.sqrt(_np.mean(np.asarray(_dy, np.float32)**2)) + 1e-12)
                        _dinfo["engine_wet_db_rel_dry"] = round(20.0*_np.log10(_wet_rms/_dry_rms + 1e-12), 2)
                    except Exception:
                        pass'''

# count spaces exactly - the original has odd indentation in pasted output
old_alt = '''                _dy, _dinfo = _spec_render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))
                if _dy is not None:'''

n = s.count(old_alt)
if n != 1:
    sys.exit("ABORT: delay call anchor matched %d" % n)
s = s.replace(old_alt, new_alt, 1)

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  delay debug added")
print("SYNTAX OK")
