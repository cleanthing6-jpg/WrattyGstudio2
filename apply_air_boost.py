from pathlib import Path
import ast, sys
P = Path("fx-api/api/polish.py")
s = P.read_text(encoding="utf-8")

OLD = "def ms_width(x, sr, mono_below=120.0, air_hz=5000.0, air_boost=1.35):"
NEW = "def ms_width(x, sr, mono_below=120.0, air_hz=5000.0, air_boost=1.15):"
if s.count(OLD) != 1:
    sys.exit("ABORT: ms_width signature matched %d - NOTHING written" % s.count(OLD))
s = s.replace(OLD, NEW, 1)
P.write_text(s, encoding="utf-8")
ast.parse(s)
print("  ok  ms_width air_boost 1.35 (+35%) -> 1.15 (+15%)")
print("--- CHECK: does any caller override air_boost? ---")
for f in ["fx-api/api/auto.py", "fx-api/api/mix.py", "fx-api/api/polish.py"]:
    for i, ln in enumerate(Path(f).read_text(encoding="utf-8").splitlines(), 1):
        if "ms_width(" in ln:
            print("%-10s %4d| %s" % (f.split('/')[-1], i, ln.strip()[:110]))
print("SYNTAX OK")
