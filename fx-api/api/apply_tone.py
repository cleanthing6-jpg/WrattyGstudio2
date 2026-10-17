from pathlib import Path
import ast, sys
P = Path('auto.py')
s = P.read_text(encoding='utf-8')

old = '''def _role_chain(voc, sr, st, role):
    t = _treat_for(role)'''
new = '''def _role_chain(voc, sr, st, role):
    t = _treat_for(role)
    _tone_plan = None
    if role == "lead":
        try:
            import adaptive_tone as _at
            voc, _tone_plan = _at.tone_correct(voc, sr, return_plan=True)
        except Exception:
            _tone_plan = None'''
n = s.count(old)
print('  anchor:', n)
if n != 1: sys.exit('ABORT')
s = s.replace(old, new, 1)

# Log the plan in moves right after hp (which starts the moves list)
old = '    moves = [["role", role], ["highpass", t["hpf"]]]'
new = '''    moves = [["role", role], ["highpass", t["hpf"]]]
    if _tone_plan is not None:
        moves.append(["tone-hpf", _tone_plan["hpf_hz"]])
        if _tone_plan["low_shelf_db"] < -0.2:
            moves.append(["tone-low", round(_tone_plan["low_shelf_db"], 2)])
        if _tone_plan["dip_db"] < -0.2:
            moves.append(["tone-dip", round(_tone_plan["dip_db"], 2)])
        if _tone_plan["hi_shelf_db"] > 0.2:
            moves.append(["tone-hi", round(_tone_plan["hi_shelf_db"], 2)])'''
n = s.count(old)
print('  moves anchor:', n)
if n != 1: sys.exit('ABORT moves')
s = s.replace(old, new, 1)

P.write_text(s, encoding='utf-8')
ast.parse(s)
print('SYNTAX OK')
