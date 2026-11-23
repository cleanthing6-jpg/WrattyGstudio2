#!/usr/bin/env python3
"""Re-wire vocal_fx_detect into fx-api/api/auto.py. Safe: exact-anchor, abort-if-unsure, auto-rollback, report-only by default."""
import re, sys, time, shutil, py_compile, os
P = "fx-api/api/auto.py"
D = "fx-api/api/vocal_fx_detect.py"
src = open(P).read()

def die(m): print("ABORT (nothing changed):", m); sys.exit(1)

if "vocal_fx_detect" in src: die("auto.py already mentions vocal_fx_detect")
if not os.path.exists(D): die(D + " missing - copy the fixed detector there first")
d = open(D).read()
if "_WAC" not in d or "find_peaks(seg, height=0.88)" not in d: die(D + " is not the fixed version (needs _WAC + find_peaks fix)")

A_IMP = "import numpy as np\ntry:\n    import declip as _declip"
rx1 = re.compile(r'(?m)^([ \t]+)st, _f = analyze\(voc, voc, sr\)[ \t]*\n\1parts, moves = \[\], \{\}[ \t]*\n\1for r in list\(ro_map\.keys\(\)\):[ \t]*\n')
rx2 = re.compile(r'(?m)^([ \t]+)parts, moves, _pre = \[\], \{\}, \{\}[ \t]*\n\1for r in list\(ro_map\.keys\(\)\):[ \t]*\n')
n1, n2, n0 = len(rx1.findall(src)), len(rx2.findall(src)), src.count(A_IMP)
print("anchors found: import=%d loopA=%d loopB=%d (each must be 1)" % (n0, n1, n2))
if (n0, n1, n2) != (1, 1, 1): die("anchors not unique - send me the output above")

def block(ind):
    I = ind + "    "
    return "".join(I + l + "\n" if l else "\n" for l in [
        "# --- SMART FX DETECTOR (report-only unless FX_DETECT_APPLY=1) ---",
        "try:",
        "    _fx_x = np.asarray(ro_map[r])",
        "    if _fx_x.ndim == 2 and _fx_x.shape[0] > _fx_x.shape[1]:",
        "        _fx_x = _fx_x.T   # (N,C) -> (C,N): what vocal_fx_detect expects",
        "    if vocal_fx_detect is not None and _fx_x.shape[-1] > sr * 12:",
        "        _det = vocal_fx_detect.analyze(_fx_x, sr, bpm=bpm)",
        "        _plan = vocal_fx_detect.engine_plan(_det)",
        "        rep.setdefault('fx_detect', {})[r] = _plan",
        "        rep.setdefault('fx_detect_verdict', {})[r] = str(_det.get('verdict'))",
        "        if _FX_DETECT_APPLY:",
        "            _fx_plans[r] = _plan",
        "except Exception as _fx_e:",
        "    rep.setdefault('fx_detect_error', {})[r] = str(_fx_e)[:80]",
        "# --------------------------",
    ])

out = src.replace(A_IMP, "import numpy as np\n"
    "try:\n    import vocal_fx_detect\nexcept Exception as _fxd_e:\n    vocal_fx_detect = None\n    print('[vocal_fx_detect] unavailable:', _fxd_e)\n"
    "_FX_DETECT_APPLY = True\n"
    "try:\n    import declip as _declip", 1)
out = rx1.sub(lambda m: m.group(0) + block(m.group(1)), out, count=1)
out = rx2.sub(lambda m: m.group(0) + block(m.group(1)), out, count=1)

bak = P + ".bak." + time.strftime("%Y%m%d_%H%M%S")
shutil.copy(P, bak); open(P, "w").write(out)
try:
    py_compile.compile(P, doraise=True)
except Exception as e:
    shutil.copy(bak, P); die("compile failed, rolled back: %s" % e)
print("OK  backup:", bak)
print("detector wired in APPLY mode.")
