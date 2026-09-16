from pathlib import Path
import ast, sys
A = Path("fx-api/api/auto.py")
s = A.read_text(encoding="utf-8")
old = '''def _treat_for(role):
    t = ROLE_TREAT.get(role, ROLE_TREAT["other"])
    d = _PRESET.get("_deltas", {}).get(role)
    if d:
        t = dict(t)
        t.update(d)
    return t'''
new = '''def _treat_for(role):
    t = dict(ROLE_TREAT.get(role, ROLE_TREAT["other"]))
    d = _PRESET.get("_deltas", {}).get(role)
    if d:
        for _k, _v in d.items():
            t[_k] = t.get(_k, 0.0) + float(_v)
    return t'''
if s.count(old) != 1:
    sys.exit("ABORT: found %d (need 1)" % s.count(old))
s = s.replace(old, new, 1)
A.write_text(s, encoding="utf-8")
ast.parse(s)
print("OK - deltas additive: lead air 2.5+0.5=3.0, sat 0.6+0.4=1.0")
