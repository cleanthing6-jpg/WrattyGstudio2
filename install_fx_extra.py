#!/usr/bin/env python3
"""Adds short-gap reverb/delay detection to vocal_fx_detect + logs raw detector numbers. Touches NO engine code."""
import re, sys, time, shutil, py_compile, os, json
A = "fx-api/api/auto.py"; D = "fx-api/api/vocal_fx_detect.py"; X = "fx-api/api/fx_detect_extra.py"
def die(m): print("ABORT (nothing changed):", m); sys.exit(1)
if not os.path.exists("fx_detect_extra.py"): die("put fx_detect_extra.py next to this script")
for p in (A, D):
    if not os.path.exists(p): die(p + " missing - run from ~/WrattyGstudio2")
auto = open(A).read(); det = open(D).read()
if not re.search(r"(?m)^def analyze\(", det): die("no module-level analyze() in " + D)
rx = re.compile(r"(?m)^([ \t]*)rep\.setdefault\('fx_detect', \{\}\)\[r\] = _plan[ \t]*$")
n = len(rx.findall(auto)); print("log anchors found:", n, "(expect 2)")
if "fx_detect_raw" not in auto and n == 0: die("log anchor not found in auto.py")
ts = time.strftime("%Y%m%d_%H%M%S")
shutil.copy(A, A + ".bak." + ts); shutil.copy(D, D + ".bak." + ts)
had_x = os.path.exists(X)
if had_x: shutil.copy(X, X + ".bak." + ts)
shutil.copy("fx_detect_extra.py", X)
HOOK = '''

# --- short-gap reverb/delay detection (fx_detect_extra) ---
try:
    import fx_detect_extra as _fxx
    _analyze_base = analyze
    def analyze(voc, sr, bpm=None):
        a = _analyze_base(voc, sr, bpm)
        try:
            return _fxx.augment(a, voc, sr, bpm)
        except Exception as _e:
            a["extra_error"] = str(_e)[:80]
            return a
except Exception:
    pass
'''
new_det = det if "fx_detect_extra" in det else det.rstrip("\n") + "\n" + HOOK
LOG = "rep.setdefault('fx_detect_raw', {})[r] = __import__('json').loads(__import__('json').dumps({k: _det.get(k) for k in ('reverb','delay','stereo','pitch','extra')}, default=str))"
new_auto = auto if "fx_detect_raw" in auto else rx.sub(lambda m: m.group(0) + "\n" + m.group(1) + LOG, auto)
open(D, "w").write(new_det); open(A, "w").write(new_auto)
try:
    for p in (A, D, X): py_compile.compile(p, doraise=True)
except Exception as e:
    shutil.copy(A + ".bak." + ts, A); shutil.copy(D + ".bak." + ts, D)
    if had_x: shutil.copy(X + ".bak." + ts, X)
    else: os.remove(X)
    die("compile failed, rolled back: %s" % e)
print("OK  backups: *.bak." + ts)
print("auto.py: only added the fx_detect_raw log line (report only). Engine untouched.")
