from pathlib import Path
import sys

P = Path("src/app/api/roex-master/route.ts")
s = P.read_text(encoding="utf-8")

OLD1 = '  const loudness = LOUDNESS.includes(want) ? want : "HIGH";'
NEW1 = ('  const loudness = LOUDNESS.includes(want) ? want : "HIGH";\n'
        '  // default is the 30s preview; client sends preview:false for the full render\n'
        '  const preview = body?.preview !== false;')
if s.count(OLD1) != 1:
    sys.exit("ABORT: loudness line matched %d" % s.count(OLD1))
s = s.replace(OLD1, NEW1, 1)

if s.count("preview: true }),") != 1:
    sys.exit("ABORT: preview:true matched %d" % s.count("preview: true }),"))
s = s.replace("preview: true }),", "preview: preview }),", 1)

P.write_text(s, encoding="utf-8")
print("PATCHED: /api/roex-master honours body.preview (default true = 30s)")
