from pathlib import Path
import ast, sys
P, A = Path("fx-api/api/polish.py"), Path("fx-api/api/auto.py")
for p in (P, A):
    if not p.exists(): sys.exit("ABORT: %s missing" % p)

s = P.read_text(encoding="utf-8")
if s.count("harsh_off=9.0") == 1:
    P.write_text(s.replace("harsh_off=9.0", "harsh_off=12.0", 1), encoding="utf-8")
    print("[1] harsh 9.0 -> 12.0")
elif s.count("harsh_off=12.0") == 1:
    print("[1] already 12.0")
else:
    sys.exit("ABORT: harsh_off value unrecognised")
ast.parse(P.read_text(encoding="utf-8"))

a = A.read_text(encoding="utf-8")
if "import polish" not in a:
    if a.count("import numpy as np\n") != 1: sys.exit("ABORT: numpy import anchor")
    a = a.replace("import numpy as np\n",
                  "import numpy as np\n\ntry:\n    import polish\nexcept Exception:\n    polish = None\n", 1)
    print("[2a] guarded import polish added")
else:
    print("[2a] import present")

old = '    core = _sum(parts)\n    rep["vocal_chain"] = moves\n'
if a.count(old) != 1: sys.exit("ABORT: bus anchor matched %d" % a.count(old))
new = ('    core = _sum(parts)\n'
'    if polish is not None:\n'
'        try:\n'
'            _sh = core.shape\n'
'            _y, _pst = polish.dynamic_eq(core, sr, get_stats=True)\n'
'            if _y.shape != _sh or not np.isfinite(_y).all(): raise ValueError("bad audio")\n'
'            core = _y\n'
'            rep["dynamic_eq"] = [{"band": "%g-%g" % (float(b[0]), float(b[1])),\n'
'                "avg_db": round(float(b[4]), 2), "max_db": round(float(b[5]), 2),\n'
'                "active_pct": round(float(b[6]), 1)} for b in _pst]\n'
'        except Exception as _e:\n'
'            rep["dynamic_eq_error"] = str(_e)[:200]\n'
'    rep["vocal_chain"] = moves\n')
a = a.replace(old, new, 1)
print("[2b] dynamic_eq wired on the vocal bus (before _glue)")
A.write_text(a, encoding="utf-8"); ast.parse(a)
print("SYNTAX OK")
