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

# 1) FET — medium-fast attack, 3-6 dB GR
s = rep(s, "attack_ms=3.0,", "attack_ms=5.0,", 1, "FET attack 3 -> 5 ms")
s = rep(s, "_fet_thr = float(np.clip(_fet_rms + 9.0, -30.0, -6.0))",
           "_fet_thr = float(np.clip(_fet_rms + 6.0, -30.0, -6.0))",
           1, "FET threshold rms+9 -> rms+6")

# 1) LA-2A — 2-4 dB GR (T4-cell hardware values)
s = rep(s, "attack_ms=25.0,", "attack_ms=10.0,", 1, "LA-2A attack 25 -> 10 ms")
s = rep(s, "release_fast_ms=150.0,", "release_fast_ms=60.0,", 1, "LA-2A fast 150 -> 60 ms")
s = rep(s, "release_slow_ms=900.0,", "release_slow_ms=1500.0,", 1, "LA-2A slow 900 -> 1500 ms")

# 3) Air high-shelf to 10 kHz (script: 8-10 kHz)
s = rep(s, "HighShelfFilter(cutoff_frequency_hz=11000.0", "HighShelfFilter(cutoff_frequency_hz=10000.0", 1, "air shelf 11k -> 10k")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
