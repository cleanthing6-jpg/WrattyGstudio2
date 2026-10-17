from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")
old = '_fet_thr = float(np.clip(_fet_rms + 3.0, -30.0, -8.0))'
new = '_fet_thr = float(np.clip(_fet_rms + 7.0, -30.0, -6.0))'
n = s.count(old)
if n != 1:
    sys.exit("ABORT: anchor matched %d times (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  FET threshold: rms+3 -> rms+7  (targets peaks only)")
print("SYNTAX OK")
