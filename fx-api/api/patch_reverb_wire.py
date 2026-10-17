from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = "    plate = _plate(voc, sr)"
new = '''    plate = None
    try:
        import dsp_pro
        plate = dsp_pro.plate_wet(voc, sr, mix=0.089, duck_depth=0.5)
    except Exception as _pr:
        _REVERB_LAST["error"] = str(_pr)[:200]
        plate = None
    if plate is None:
        plate = _plate(voc, sr)'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: matched %d (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  _ambience now calls dsp_pro.plate_wet (falls back to _plate on error)")
print("SYNTAX OK")
