from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''def _parallel(x, sr):
    """Gentle parallel vocal density; keeps the dry vocal intact."""
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        crushed = Pedalboard([
            Compressor(threshold_db=-24.0, ratio=6.0,
                       attack_ms=8.0, release_ms=90.0),
            Gain(gain_db=3.0),
        ])(a, int(sr)).astype(np.float32)
        y = (a * 0.70 + crushed * 0.30).astype(np.float32)
        out = _headroom(y, -1.0).astype(np.float32)
        _PAR_LAST["ran"] = True
        return out
    except Exception as _e:
        _PAR_LAST["error"] = str(_e)[:200]
        return x'''

new = '''def _parallel(x, sr):
    """NY parallel — 12:1 smash, HPF 120 sidechain, additive blend."""
    try:
        import parallel_comp
        out = parallel_comp.industry_parallel_compressor(x, sr, blend_amount=0.30)
        _PAR_LAST["ran"] = True
        _PAR_LAST["mode"] = "ny 12:1 0.5ms hpf120 add30"
        return out
    except Exception as _e:
        _PAR_LAST["error"] = str(_e)[:200]
        return x'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: matched %d (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  _parallel upgraded (NY smash), same call site")
print("SYNTAX OK")
