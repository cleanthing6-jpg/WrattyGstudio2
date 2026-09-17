from pathlib import Path
import ast, sys
A = Path("fx-api/api/auto.py"); M = Path("fx-api/api/mix.py")
a = A.read_text(encoding="utf-8"); m = M.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want: sys.exit("ABORT: '%s' matched %d (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

a = rep(a,
'''    "rap": {
        "target_lufs": -10.5, "glue_ratio": 1.8, "glue_gr_db": 1.2,
        "width": 1.06, "plate_db": -18.0, "slap_db": -22.0,
    },''',
'''    "rap": {
        "target_lufs": -10.5, "glue_ratio": 1.8, "glue_gr_db": 1.2,
        "width": 1.06, "plate_db": -18.0, "slap_db": -22.0, "clip": True,
    },''', 1, "rap row gets clip:True")

m = rep(m,
'''        if mode not in ("passthrough", "two_track"):
            mixed = auto.clip(mixed, sr)''',
'''        if mode != "passthrough" and (
            mode != "two_track" or bool(cfg.get("clip"))
        ):
            mixed = auto.clip(mixed, sr)''', 1, "clipper gated by preset flag")

A.write_text(a, encoding="utf-8"); M.write_text(m, encoding="utf-8")
ast.parse(a); ast.parse(m)
print("SYNTAX OK - revert: git checkout -- fx-api/api/auto.py fx-api/api/mix.py")
