from pathlib import Path
import ast, sys

# ── 1. Add tune_vocal to adaptive_ambience.py ──
M = Path('adaptive_ambience.py')
m = M.read_text(encoding='utf-8')

TUNE_FN = '''

# ── Adaptive vocal tone: lowmid measurement -> body/mud adjustment ──
VOCAL_NEUTRAL_LOWMID = 0.25
VOCAL_LOWMID_MUD_SLOPE = 10.0
VOCAL_LOWMID_BODY_SLOPE = 7.0


def tune_vocal(voc, sr, role="lead"):
    """Return adaptive body_db and mud_cap from the vocal's low-mid content.

    Muddy vocal  -> deeper mud cut, thinner body shelf
    Thin vocal   -> shallower mud cut, more body shelf
    Neutral      -> preset defaults (body 2.0 dB, mud 2.5 dB)
    All values in dB. Ratio-based, so level-independent -> multi-user safe.
    """
    try:
        a = analyze_vocal(voc, sr)
        lowmid = float(a["lowmid"])
    except Exception:
        return None

    delta = lowmid - VOCAL_NEUTRAL_LOWMID       # + muddy, - thin
    mud_extra  = float(np.clip(delta * VOCAL_LOWMID_MUD_SLOPE,  -1.5, +3.0))
    body_delta = float(np.clip(-delta * VOCAL_LOWMID_BODY_SLOPE, -2.0, +1.0))

    return {
        "body_db": float(np.clip(2.0 + body_delta, 0.0, 4.0)),
        "mud_cap": float(np.clip(2.5 + mud_extra, 1.0, 6.0)),
        "lowmid": lowmid,
    }
'''

if 'def tune_vocal(' in m:
    print('  tune_vocal already present — skip')
else:
    m = m.rstrip() + TUNE_FN + '\n'
    M.write_text(m, encoding='utf-8')
    ast.parse(m)
    print('  tune_vocal added to adaptive_ambience.py')

# ── 2. Wire into _role_chain in auto.py ──
A = Path('auto.py')
s = A.read_text(encoding='utf-8')

old = 'def _role_chain(voc, sr, st, role):\n    t = _treat_for(role)\n'
new = '''def _role_chain(voc, sr, st, role):
    t = _treat_for(role)
    # Adaptive vocal tone — measure lowmid, adjust body_db / mud cap per user
    if role == "lead":
        try:
            import adaptive_ambience as _aa
            _vt = _aa.tune_vocal(voc, sr, role)
            if _vt is not None:
                t = dict(t)
                t["body_db"] = _vt["body_db"]
                t["mud"] = _vt["mud_cap"]
        except Exception:
            pass
'''
n = s.count(old)
if n != 1:
    sys.exit('ABORT: _role_chain anchor matched %d' % n)
s = s.replace(old, new, 1)
A.write_text(s, encoding='utf-8')
ast.parse(s)
print('  _role_chain wired')
print('ALL PATCHED + COMPILES OK')
