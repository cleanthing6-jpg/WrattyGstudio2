from pathlib import Path
import ast, sys

# ── 1. plate_wet: default mix=1.0 (role_bus scales)
P1 = Path("dsp_pro.py")
s1 = P1.read_text(encoding="utf-8")
old1 = 'def plate_wet(voc, sr, mix=0.089, duck_depth=0.5,'
new1 = 'def plate_wet(voc, sr, mix=1.0, duck_depth=0.5,'
if s1.count(old1) != 1:
    sys.exit("ABORT: plate_wet signature mismatch")
s1 = s1.replace(old1, new1, 1)
P1.write_text(s1, encoding="utf-8"); ast.parse(s1)
print("  ok  plate_wet default mix 0.089 -> 1.0")

# ── 2. _ambience: pass mix=1.0 explicitly (unchanged default, but explicit)
P2 = Path("auto.py")
s2 = P2.read_text(encoding="utf-8")
old2 = '            plate = dsp_pro.plate_wet(voc, sr, mix=0.089, duck_depth=0.5)'
new2 = '            plate = dsp_pro.plate_wet(voc, sr, mix=1.0, duck_depth=0.5)'
if s2.count(old2) != 1:
    sys.exit("ABORT: _ambience plate call mismatch")
s2 = s2.replace(old2, new2, 1)

# ── 3. delay_render: default mix=1.0 (role_bus scales)
P3 = Path("dsp_delay.py")
s3 = P3.read_text(encoding="utf-8")
old3 = 'note_div=0.25, feedback=0.25, mix=0.20, width=0.80,'
new3 = 'note_div=0.25, feedback=0.25, mix=1.0, width=0.80,'
if s3.count(old3) != 1:
    sys.exit("ABORT: delay_render signature mismatch")
s3 = s3.replace(old3, new3, 1)
P3.write_text(s3, encoding="utf-8"); ast.parse(s3)
print("  ok  delay_render default mix 0.20 -> 1.0")

P2.write_text(s2, encoding="utf-8"); ast.parse(s2)
print("  ok  _ambience plate call uses mix=1.0")
print("SYNTAX OK")
print()
print("The role_bus sends (0.22 plate / 0.40 delay on lead) now control the")
print("audible wet level, same as they did with the old _plate/_delay_tree.")
