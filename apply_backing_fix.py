from pathlib import Path
import ast, sys
p = Path("fx-api/api/auto.py")
s = p.read_text(encoding="utf-8")

def rep1(t, old, new, label):
    if t.count(old) != 1:
        sys.exit("ABORT: '%s' matched %d times" % (label, t.count(old)))
    print("  ok  " + label)
    return t.replace(old, new, 1)

s = rep1(s,
'''    "backing": {"gain": -1.5, "hpf": 90.0,  "mud": 2.0, "box": 1.0, "pres": 0.8,
                "harsh": 2.0, "air": 1.5, "ratio": 2.5, "atk": 20.0, "rel": 160.0,
                "sat": 0.6, "width": 1.4},''',
'''    "backing": {"gain": -1.5, "hpf": 140.0, "mud": 3.0, "box": 2.0, "pres": 0.0,
                "harsh": 2.0, "air": 1.0, "ratio": 2.5, "atk": 20.0, "rel": 160.0,
                "sat": 0.6, "width": 1.2},''',
"backing row: hpf 90->140, mud 2->3, box 1->2, pres off, air 1.5->1.0, width 1.4->1.2")

s = rep1(s, "-85.0", "-60.0", "silent-file guard -85 -> -60 (skips your -68 dB file)")

p.write_text(s, encoding="utf-8")
ast.parse(s)
print("SYNTAX OK - revert: git checkout -- fx-api/api/auto.py")
