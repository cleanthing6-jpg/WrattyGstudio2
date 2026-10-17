from pathlib import Path
import ast, sys

P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''def _exciter(x, sr):
    """Low-level high-frequency harmonic air without distorting the body."""
    try:'''
new = '''def _exciter(x, sr):
    """Low-level high-frequency harmonic air without distorting the body."""
    from pedalboard import Pedalboard, HighpassFilter, LowpassFilter, Distortion, Gain
    try:'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: anchor matched %d times (need 1) - NOTHING written" % n)

s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8")
ast.parse(s)

print("  ok  _exciter imports Gain locally")
print("SYNTAX OK")
print("revert: git checkout -- auto.py")
