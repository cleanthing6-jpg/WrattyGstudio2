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

# FET: raise threshold so it catches PEAKS ONLY (not continuous).
# Currently rms+6 -> -4.88 dB GR (constant squeeze on every consonant).
# rms+10 -> ~2-3 dB GR, only on the loudest syllables. Stops the smear.
s = rep(s, "_fet_thr = float(np.clip(_fet_rms + 6.0, -30.0, -6.0))",
           "_fet_thr = float(np.clip(_fet_rms + 10.0, -30.0, -6.0))",
           1, "FET threshold rms+6 -> rms+10 (peaks-only, kills continuous compression)")

# Exciter: reduce wet mix from 0.18 to 0.08.
# 18% of a distorted 5-10k signal stacked on de-ess + FET is what combs the S.
# 8% keeps the air without fighting the de-esser on the same band.
s = rep(s, "y = (a + air * 0.18).astype(np.float32)",
           "y = (a + air * 0.08).astype(np.float32)",
           1, "exciter wet mix 0.18 -> 0.08 (stops S-band comb with de-ess)")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
