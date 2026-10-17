from pathlib import Path
import ast, sys
P = Path("dsp_pro.py")
s = P.read_text(encoding="utf-8")
old = '''        il = np.clip(idx + lfo, 0.0, float(n - 1))
        ir_ = np.clip(idx - lfo, 0.0, float(n - 1))
        rev_l = np.interp(il, idx, rev_l).astype(np.float32)
        rev_r = np.interp(ir_, idx, rev_r).astype(np.float32)'''
new = '''        shift = np.clip(idx + lfo, 0.0, float(n - 1))
        rev_l = np.interp(shift, idx, rev_l).astype(np.float32)
        rev_r = np.interp(shift, idx, rev_r).astype(np.float32)'''
n = s.count(old)
if n != 1:
    sys.exit("ABORT: mod anchor matched %d" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  plate mod: same-phase L/R (no anti-correlation)")
print("SYNTAX OK")
