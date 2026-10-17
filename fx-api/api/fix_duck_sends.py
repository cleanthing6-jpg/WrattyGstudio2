from pathlib import Path
import ast, sys

# 1. Revert send bump
P1 = Path("auto.py")
s1 = P1.read_text(encoding="utf-8")
old_send = '"lead":    {"glue": None,          "plate": 0.50, "delay": 0.60,'
new_send = '"lead":    {"glue": None,          "plate": 0.35, "delay": 0.50,'
if s1.count(old_send) != 1:
    sys.exit("ABORT: send anchor mismatch")
s1 = s1.replace(old_send, new_send, 1)
P1.write_text(s1, encoding="utf-8"); ast.parse(s1)
print("  ok  sends: plate 0.50->0.35, delay 0.60->0.50")

# 2. Lower delay internal duck 10 -> 6 dB
P2 = Path("dsp_delay.py")
s2 = P2.read_text(encoding="utf-8")
old_dd = 'duck_depth=0.5, tape=True):'
new_dd = 'duck_depth=0.3, tape=True):'
if s2.count(old_dd) != 1:
    sys.exit("ABORT: delay duck anchor mismatch")
s2 = s2.replace(old_dd, new_dd, 1)
P2.write_text(s2, encoding="utf-8"); ast.parse(s2)
print("  ok  delay duck_depth 0.5 -> 0.3")

# 3. Lower plate internal duck 0.5 -> 0.25
P3 = Path("dsp_pro.py")
s3 = P3.read_text(encoding="utf-8")
old_pd = 'def plate_wet(voc, sr, mix=1.0, duck_depth=0.5,'
new_pd = 'def plate_wet(voc, sr, mix=1.0, duck_depth=0.25,'
if s3.count(old_pd) != 1:
    sys.exit("ABORT: plate duck anchor mismatch")
s3 = s3.replace(old_pd, new_pd, 1)
P3.write_text(s3, encoding="utf-8"); ast.parse(s3)
print("  ok  plate duck_depth 0.5 -> 0.25")

# 4. _ambience call
s1 = P1.read_text(encoding="utf-8")
old_call = 'plate = dsp_pro.plate_wet(voc, sr, mix=1.0, duck_depth=0.5)'
new_call = 'plate = dsp_pro.plate_wet(voc, sr, mix=1.0, duck_depth=0.25)'
if s1.count(old_call) != 1:
    sys.exit("ABORT: plate_wet call anchor mismatch")
s1 = s1.replace(old_call, new_call, 1)
P1.write_text(s1, encoding="utf-8"); ast.parse(s1)
print("  ok  _ambience plate_wet call updated")

print("SYNTAX OK")
