from pathlib import Path
import re, ast, sys

M = Path("fx-api/api/mix.py")
A = Path("fx-api/api/auto.py")
for p in (M, A):
    if not p.exists(): sys.exit("ABORT: %s missing" % p)
m = M.read_text(encoding="utf-8")
a = A.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d times (need %d)" % (label, n, want))
    print("  ok  %s (%d)" % (label, n))
    return t.replace(old, new)

m = rep(m, 'if mode not in ("two_track", "passthrough", "vocal_only"):',
        'if mode != "passthrough":', 2, "master guards relaxed")

m, n1 = re.subn(r"PeakFilter\(cutoff_frequency_hz=250,\s*gain_db=[-0-9.]+",
                "PeakFilter(cutoff_frequency_hz=250, gain_db=0.0", m)
if n1 != 1: sys.exit("ABORT: 250Hz filter x%d" % n1)
m, n2 = re.subn(r"PeakFilter\(cutoff_frequency_hz=3000,\s*gain_db=[-0-9.]+",
                "PeakFilter(cutoff_frequency_hz=3000, gain_db=0.0", m)
if n2 != 1: sys.exit("ABORT: 3kHz filter x%d" % n2)
print("  ok  BUS EQ boosts -> 0 dB")

m = rep(m, "min(2.5, tgt - cur)", "max(-9.0, min(9.0, tgt - cur))", 1, "lift cap pass 1")
m = rep(m, "min(2.5, tgt - f)", "max(-9.0, min(9.0, tgt - f))", 1, "lift cap correction")
m = rep(m, "for _ in range(1):", "for _ in range(4):", 1, "correction passes 1 -> 4")

a = rep(a, "Clipping(threshold_db=-2.0)", "Clipping(threshold_db=-1.0)", 1, "clipper -2 -> -1")

M.write_text(m, encoding="utf-8"); A.write_text(a, encoding="utf-8")
ast.parse(m); ast.parse(a)
print("SYNTAX OK - revert: git checkout -- fx-api/api/mix.py fx-api/api/auto.py")
