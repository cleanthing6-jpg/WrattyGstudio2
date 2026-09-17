from pathlib import Path
import ast, sys
A = Path("fx-api/api/auto.py")
s = A.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want: sys.exit("ABORT: '%s' matched %d times (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

s = rep(s,
'''    "afrobeats": {
        "target_lufs": -12.0, "glue_ratio": 1.5, "glue_gr_db": 0.8,
        "width": 1.12, "plate_db": -15.0, "slap_db": -18.0,
    },
}''',
'''    "afrobeats": {
        "target_lufs": -12.0, "glue_ratio": 1.5, "glue_gr_db": 0.8,
        "width": 1.12, "plate_db": -15.0, "slap_db": -18.0,
    },
    "pop": {
        "target_lufs": -11.5, "glue_ratio": 1.6, "glue_gr_db": 1.0,
        "width": 1.10, "plate_db": -16.0, "slap_db": -20.0,
    },
    "rnb": {
        "target_lufs": -14.0, "glue_ratio": 1.4, "glue_gr_db": 0.5,
        "width": 1.08, "plate_db": -13.0, "slap_db": -16.0,
    },
    "rap": {
        "target_lufs": -10.5, "glue_ratio": 1.8, "glue_gr_db": 1.2,
        "width": 1.06, "plate_db": -18.0, "slap_db": -22.0,
    },
}''', 1, "pop/rnb/rap preset rows")

s = rep(s,
'''ROLE_DELTAS = {
    "afrobeats": {"lead": {"air": 0.5, "sat": 0.4}, "backing": {"pres": -0.2}},
}''',
'''ROLE_DELTAS = {
    "afrobeats": {"lead": {"air": 0.5, "sat": 0.4}, "backing": {"pres": -0.2}},
    "pop": {"lead": {"air": 1.0, "sat": 0.2}},
    "rnb": {"lead": {"air": 0.5, "sat": -0.1}},
    "rap": {"lead": {"air": -0.5, "sat": 0.6}, "backing": {"pres": -0.2}},
}''', 1, "role deltas pop/rnb/rap")

A.write_text(s, encoding="utf-8")
ast.parse(s)
print("SYNTAX OK - revert: git checkout -- fx-api/api/auto.py")
