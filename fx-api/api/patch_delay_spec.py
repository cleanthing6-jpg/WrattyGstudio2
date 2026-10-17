from pathlib import Path
import ast, sys

P = Path("delay_spec.py")
s = P.read_text(encoding="utf-8")

old = "if 100.0 <= d_ms <= 600.0:"
new = "if 100.0 <= d_ms <= 300.0:"

n = s.count(old)
if n != 1:
    sys.exit("ABORT: anchor matched %d times (need 1) - NOTHING written" % n)

s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8")
ast.parse(s)

print("  ok  accept window narrowed: [100, 600] -> [100, 300]")
print("  picks note value that lands in pro slapback zone, any BPM")
print("SYNTAX OK")
print("revert: git checkout -- delay_spec.py")
