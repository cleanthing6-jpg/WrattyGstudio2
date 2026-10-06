import re, sys
from pathlib import Path
p = Path("/data/data/com.termux/files/home/WrattyGstudio2/fx-api/api/auto.py")
s = p.read_text()
frac = float(sys.argv[1])
new, n = re.subn(r"min\(int\(sr \* beat_s \* [0-9.]+\)",
                "min(int(sr * beat_s * %g)" % frac, s, count=1)
if n != 1: raise SystemExit("anchor = %d" % n)
p.write_text(new)
print("delay fraction -> %g  (~%.0f ms at 99.4 BPM)" % (frac, frac * 603.6))
