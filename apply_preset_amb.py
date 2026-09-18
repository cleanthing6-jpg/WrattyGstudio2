from pathlib import Path
import ast, sys
P = Path("fx-api/api/auto.py")
s = P.read_text(encoding="utf-8")

old = '"width": 1.12, "plate_db": -15.0, "slap_db": -18.0,'
new = '"width": 1.20, "plate_db": -12.0, "slap_db": -13.0,'
lines = s.splitlines()
hit = [i for i, ln in enumerate(lines) if old in ln]
if len(hit) != 1:
    for i, ln in enumerate(lines):
        if 'plate_db' in ln:
            print("%4d| %s" % (i + 1, ln))
    sys.exit("ABORT: anchor matched %d - NOTHING written" % len(hit))

i = hit[0]
print("--- context (confirm this is afrobeats) ---")
for j in range(max(0, i - 8), min(len(lines), i + 2)):
    print("%4d| %s" % (j + 1, lines[j]))

s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8")
ast.parse(s)
print("--- applied ---")
print("  ok  afrobeats: width 1.12 -> 1.20, plate -15 -> -12, slap -18 -> -13")
print("SYNTAX OK")
