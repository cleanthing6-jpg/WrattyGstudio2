from pathlib import Path
import json, re

p = Path("fx-api/api/auto.py")
s = p.read_text()
lines = s.splitlines()

def block(start, end=None):
    a = next((i for i,x in enumerate(lines) if x.startswith(start)), None)
    if a is None:
        print("NOT FOUND:", start); return
    b = next((i for i in range(a+1, len(lines))
              if end and lines[i].startswith(end)), len(lines))
    print("\n===== %s =====" % start)
    print("\n".join("%4d %s" % (i+1, lines[i]) for i in range(a,b)))

block("ROLE_TREAT =", "ROLE_VOCALS")
block("def _role_chain(", "def vocal_process")
block("def _match_role_levels(", "def ")

print("\n===== REPORTS =====")
mf = Path("mrs.txt")
if mf.exists():
    for n, line in enumerate(mf.read_text().splitlines(), 1):
        k = line.find("MIXREPORT ")
        if k < 0: continue
        try:
            d = json.loads(line[k + 10:])
            r = d.get("report", {})
            print("\nREPORT", n)
            print("arrived:", json.dumps(r.get("arrived", {}), separators=(",",":")))
            print("bus_diag:", json.dumps(r.get("bus_diag", {}), separators=(",",":")))
        except Exception as e:
            print("REPORT", n, "parse error:", e)
else:
    print("mrs.txt missing")
