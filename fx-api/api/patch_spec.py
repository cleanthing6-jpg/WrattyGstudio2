from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d (need %d) - NOTHING written" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

# 2) HPF at 80-100 Hz (script) — currently 135, out of spec
s = rep(s, '"gain": 0.0, "hpf": 135.0,', '"gain": 0.0, "hpf": 90.0,', 1, "HPF 135 -> 90 (script: 80-100)")

# 3) Air high-shelf from 8-10 kHz (script) — currently 11k
s = rep(s, '"air 11k"', '"air 10k"', 1, "air shelf label 11k -> 10k")
s = rep(s, "cutoff_frequency_hz=11000.0", "cutoff_frequency_hz=10000.0", 1, "air shelf 11k -> 10k")

# 1) FET GR 3-6 dB (script) — currently 2.93, nudging to hit range
s = rep(s, "_fet_thr = float(np.clip(_fet_rms + 9.0, -30.0, -6.0))",
           "_fet_thr = float(np.clip(_fet_rms + 8.0, -30.0, -6.0))",
           1, "FET threshold rms+9 -> rms+8 (GR into 3-6 range)")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
