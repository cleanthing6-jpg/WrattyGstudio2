from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''    parts, moves, _pre = [], {}, {}
    for r in list(ro_map.keys()):
        y, mv = _role_chain(ro_map[r], sr, st, r)'''
new = '''    parts, moves, _pre = [], {}, {}
    for r in list(ro_map.keys()):
        if r in ("beat", "other"):
            continue
        y, mv = _role_chain(ro_map[r], sr, st, r)'''
n = s.count(old)
if n != 1:
    sys.exit("ABORT: matched %d (need 1)" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  beat/other excluded from vocal chain")
print("SYNTAX OK")
