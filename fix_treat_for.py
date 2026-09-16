from pathlib import Path
import ast, sys
A = Path("fx-api/api/auto.py")
s = A.read_text(encoding="utf-8")
old = '''def _treat_for(role):
    t = _treat_for(role)'''
new = '''def _treat_for(role):
    t = ROLE_TREAT.get(role, ROLE_TREAT["other"])'''
if s.count(old) != 1:
    sys.exit("ABORT: broken line found %d times (need 1)" % s.count(old))
s = s.replace(old, new, 1)
A.write_text(s, encoding="utf-8")
ast.parse(s)
print("OK - _treat_for no longer self-calls")
