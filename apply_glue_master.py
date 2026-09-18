from pathlib import Path
import ast, sys
P = Path("fx-api/api/mix.py")
s = P.read_text(encoding="utf-8")

A = '''            if mode == "two_track":
                # beat is already mastered - keep 30 Hz rumble guard, skip the compressor'''
B = '''            if mode in ("two_track", "master"):
                # input is already a finished mix - keep 30 Hz guard, skip the compressor'''
if s.count(A) != 1:
    sys.exit("ABORT glue cond: matched %d - NOTHING written" % s.count(A))
s = s.replace(A, B, 1)

C = 'report["glue_thr_db"] = "off (two_track)"'
D = 'report["glue_thr_db"] = "off (%s)" % mode'
if s.count(C) != 1:
    sys.exit("ABORT glue label: matched %d - NOTHING written" % s.count(C))
s = s.replace(C, D, 1)

P.write_text(s, encoding="utf-8")
ast.parse(P.read_text(encoding="utf-8"))
print("OK: glue skipped for two_track AND master")
