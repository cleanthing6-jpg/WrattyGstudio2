from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''    try:
        from pedalboard import LowShelfFilter as _LSF
        _body_db = float(t.get("body_db", 1.5))
        if _body_db > 0.1:
            _bf = float(t.get("body_hz", 300.0))
            ch.append(_LSF(cutoff_frequency_hz=_bf, gain_db=_body_db))
            moves.append(["body %g" % _bf, round(_body_db, 2)])
    except Exception:
        pass'''

new = '''    try:
        _body_db = float(t.get("body_db", 1.5))
        if _body_db > 0.1:
            _bf = float(t.get("body_hz", 300.0))
            ch.append(LowShelfFilter(cutoff_frequency_hz=_bf, gain_db=_body_db))
            moves.append(["body %g" % _bf, round(_body_db, 2)])
    except Exception as _be:
        moves.append(["body-error", str(_be)[:80]])'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: matched %d (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  body shelf: use module-level LowShelfFilter, log errors")
print("SYNTAX OK")
