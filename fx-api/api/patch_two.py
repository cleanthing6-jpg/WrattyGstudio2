from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

s = rep(s, "release_ms=250.0,", "release_ms=80.0,", 1, "FET release 250 -> 80 ms")
s = rep(s, '"box": 1.5, "box_hz": 600.0, "box_q": 1.0,\n            "pres": 0.8,',
           '"box": 2.5, "box_hz": 600.0, "box_q": 1.0,\n            "pres": 0.8,',
           1, "box 1.5 -> 2.5")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
