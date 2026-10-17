from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")
old = '"hpf_min": 135.0, "hpf_max": 165.0,'
new = '"hpf_min": 80.0, "hpf_max": 100.0,'
n = s.count(old)
if n != 1:
    sys.exit("ABORT: matched %d (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  HPF clamp 135-165 -> 80-100 (script: 80-100)")
print("SYNTAX OK")
