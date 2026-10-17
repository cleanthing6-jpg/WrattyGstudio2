from pathlib import Path
import ast, sys

P = Path("delay_spec.py")
s = P.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d times (need %d) - NOTHING written" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

s = rep(s, "send_db=-14.0,", "send_db=-8.0,",  1, "afrobeats send_db -14 -> -8")
s = rep(s, "send_db=-20.0,", "send_db=-14.0,", 1, "neutral   send_db -20 -> -14")
s = rep(s, "duck_db=6.0,",   "duck_db=3.0,",   2, "duck_db 6 -> 3 (both presets)")

P.write_text(s, encoding="utf-8")
ast.parse(s)
print("SYNTAX OK")
print("afrobeats effective: -20 dB -> -11 dB under vocal")
print("revert: git checkout -- delay_spec.py")
