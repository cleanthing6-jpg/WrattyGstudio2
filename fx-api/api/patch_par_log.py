from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")
old = '_PAR_LAST["mode"] = "ny 12:1 0.5ms hpf120 add30"'
new = '_PAR_LAST["mode"] = "ny 6:1 8ms hpf120 sub30"'
n = s.count(old)
if n != 1:
    sys.exit("ABORT: matched %d (need 1)" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  parallel log updated to live values")
print("SYNTAX OK")
