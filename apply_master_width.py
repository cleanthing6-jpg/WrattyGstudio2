from pathlib import Path
import ast, re, sys
P = Path("fx-api/api/auto.py")
s = P.read_text(encoding="utf-8")

m = re.search(r'^WIDEN_MASTER\s*=\s*([0-9.]+)', s, re.M)
if not m:
    sys.exit("ABORT: 'WIDEN_MASTER = <number>' not found - NOTHING written")
print("current WIDEN_MASTER =", m.group(1))
s = s[:m.start(1)] + "1.0" + s[m.end(1):]
P.write_text(s, encoding="utf-8")
ast.parse(s)
print("  ok  WIDEN_MASTER -> 1.0  (master widen removed)")
print("--- paste these lines so I can reduce the side boost next ---")
for i, ln in enumerate(s.splitlines(), 1):
    low = ln.lower()
    if "side" in low or "5 kHz" in ln:
        print("%4d| %s" % (i, ln.strip()[:110]))
print("SYNTAX OK")
