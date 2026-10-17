from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

# 1. Restore clip-gain
n1 = s.count("max_gain_db=0.0,")
if n1 != 1:
    sys.exit("ABORT: clip-gain anchor matched %d" % n1)
s = s.replace("max_gain_db=0.0,", "max_gain_db=1.5,", 1)

# 2. TEST: bypass the duck completely (commented reference shows the real call)
old_duck = "    ducked_stft, plan, vpres, post = _duck(beat, _dry_voc, freq, st)"
new_duck = """    # TEST: duck bypassed to isolate breathing
    ducked_stft, plan, vpres, post = beat.copy(), {}, 0.0, None
    # ducked_stft, plan, vpres, post = _duck(beat, _dry_voc, freq, st)"""

n2 = s.count(old_duck)
if n2 != 1:
    sys.exit("ABORT: duck call anchor matched %d - NOTHING written" % n2)
s = s.replace(old_duck, new_duck, 1)

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  clip-gain restored (max=1.5)")
print("  ok  TEST: _duck bypassed")
print("SYNTAX OK")
print("REVERT: git checkout -- fx-api/api/auto.py")
