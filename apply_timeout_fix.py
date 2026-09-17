from pathlib import Path
import sys
P = Path("src/app/api/mix/route.ts")
if not P.exists():
    sys.exit("ABORT: src/app/api/mix/route.ts missing")

s = P.read_text(encoding="utf-8")

def rep(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        sys.exit("ABORT: '%s' matched %d times (need 1)" % (label, n))
    s = s.replace(old, new, 1)
    print("  ok  " + label)

rep("signal: AbortSignal.timeout(120000),",
    "signal: AbortSignal.timeout(20000),",
    "mixer poll timeout 120s -> 20s")

rep("}, 3, [502, 503])", "}, 1, [502, 503])", "POST tries 3 -> 1")
rep("}, 4, [502, 503, 504])", "}, 2, [502, 503, 504])", "GET tries 4 -> 2")

P.write_text(s, encoding="utf-8")
print("PATCHED - revert: git checkout -- src/app/api/mix/route.ts")
