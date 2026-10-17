from pathlib import Path
import ast, sys

# ── Step 1: add tune_compressors to adaptive_ambience.py ──
M = Path('adaptive_ambience.py')
m = M.read_text(encoding='utf-8')

if 'def tune_compressors' in m:
    print('  tune_compressors already present — skip')
else:
    BLOCK = '''

# ═══════════════════════════════════════════════════════════════════════
#  Adaptive compressor thresholds — conservative
#  Goal: same gentle clamping for every user, at any input level.
# ═══════════════════════════════════════════════════════════════════════

FET_PCT        = 95.0    # top 5% of frames define the peak reference
FET_HEADROOM   = 4.0     # FET threshold sits 4 dB above that peak
OPTO_PCT       = 80.0    # top 20% for sustained content
OPTO_HEADROOM  = 3.0     # LA-2A threshold sits 3 dB above


def tune_compressors(voc, sr):
    """Return FET and LA-2A thresholds in dBFS, from the vocal's envelope.

    Multi-user safe: quiet and loud takes get proportional clamping.
    """
    a = _mono(voc)
    n = len(a)
    if n < sr:
        return None

    env_db = _frames_db(a, sr, win=0.02)
    if len(env_db) < 30:
        return None

    fet_ref  = float(np.percentile(env_db, FET_PCT))
    opto_ref = float(np.percentile(env_db, OPTO_PCT))

    fet_thr  = float(np.clip(fet_ref + FET_HEADROOM, -30.0, -6.0))
    opto_thr = float(np.clip(opto_ref + OPTO_HEADROOM, -30.0, -6.0))

    return dict(fet_thr=fet_thr, opto_thr=opto_thr,
                fet_ref=fet_ref, opto_ref=opto_ref)
'''
    m = m.rstrip() + BLOCK + '\n'
    M.write_text(m, encoding='utf-8')
    ast.parse(m)
    print('  tune_compressors added')

# ── Step 2: patch auto.py ──
A = Path('auto.py')
s = A.read_text(encoding='utf-8')

# Insert the adaptive lookup right after `t = _treat_for(role)`
old = 'def _role_chain(voc, sr, st, role):\n    t = _treat_for(role)'
if old not in s:
    sys.exit('ABORT: _role_chain header')
new = '''def _role_chain(voc, sr, st, role):
    t = _treat_for(role)
    _comp = None
    if role == "lead":
        try:
            import adaptive_ambience as _aa_c
            _comp = _aa_c.tune_compressors(voc, sr)
        except Exception:
            _comp = None'''
s = s.replace(old, new, 1)
print('  _comp lookup inserted')

# FET threshold — use adaptive
old = '            _fet_thr = float(np.clip(_fet_rms + 10.0, -30.0, -6.0))'
new = '            _fet_thr = float(_comp["fet_thr"]) if _comp else float(np.clip(_fet_rms + 10.0, -30.0, -6.0))'
n = s.count(old)
print('  FET threshold:', n)
if n != 1: sys.exit('ABORT: FET')
s = s.replace(old, new, 1)

# LA-2A threshold — use adaptive
old = '        _opto_thr_cal = float(max(-14.0, _vocal_rms + 8.0))'
new = '        _opto_thr_cal = float(_comp["opto_thr"]) if _comp else float(max(-14.0, _vocal_rms + 8.0))'
n = s.count(old)
print('  LA-2A threshold:', n)
if n != 1: sys.exit('ABORT: LA2A')
s = s.replace(old, new, 1)

A.write_text(s, encoding='utf-8')
ast.parse(s)
print()
print('PATCHED + COMPILES OK')
