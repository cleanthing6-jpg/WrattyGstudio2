from pathlib import Path
import ast, sys
P = Path("dsp_pro.py")
s = P.read_text(encoding="utf-8")

# Find the reverb section marker
marker = "# ══════════════════════════════════════════════════════════════\n# PLATE REVERB"
i1 = s.find(marker)
i2 = s.find(marker, i1 + 1)
if i1 == -1:
    sys.exit("ABORT: reverb marker not found")
if i2 == -1:
    print("  no duplicate marker — nothing to strip")
    sys.exit(0)

# Keep everything up to and including the first reverb block.
# The block ends right before the second marker at i2.
# So: keep s[:i2] — that's got one copy.
s = s[:i2].rstrip() + "\n"
P.write_text(s, encoding="utf-8")
ast.parse(s)
print("  ok  removed duplicate reverb block")
print("SYNTAX OK")
