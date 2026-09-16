from pathlib import Path
import ast, sys
M = Path("fx-api/api/mix.py")
m = M.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d times (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

# 1. glue threshold tracks the mix -> ~1 dB GR at 1.5:1, never over-squeezes
m = rep(m,
'''            setjob(jid, "glue bus")
            mixed = BUS(mixed, sr).astype(np.float32)''',
'''            setjob(jid, "glue bus")
            _thr = float(np.clip(rmsdb(mixed) - 3.0, -40.0, -6.0))
            mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                                Compressor(threshold_db=_thr, ratio=1.5,
                                           attack_ms=30.0, release_ms=130.0)])(mixed, sr).astype(np.float32)
            report["glue_thr_db"] = round(_thr, 2)''',
1, "adaptive glue threshold (was fixed -16 dB)")

# 2. no clipper on ready-made beats - brickwall limiter is enough
m = rep(m,
'''        if mode != "passthrough":
            mixed = auto.clip(mixed, sr)''',
'''        if mode not in ("passthrough", "two_track"):
            mixed = auto.clip(mixed, sr)''',
1, "clipper bypassed for two_track")

M.write_text(m, encoding="utf-8")
ast.parse(m)
print("SYNTAX OK - revert: git checkout -- fx-api/api/mix.py")
