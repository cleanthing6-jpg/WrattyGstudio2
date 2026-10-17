from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

# ── _exciter: keep function signature, swap body to tier-1 engine
old_e = '''def _exciter(x, sr):
    """Low-level high-frequency harmonic air without distorting the body."""
    from pedalboard import Pedalboard, HighpassFilter, LowpassFilter, Distortion, Gain
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        air = Pedalboard([
            HighpassFilter(cutoff_frequency_hz=5000.0),
            Distortion(drive_db=0.8),
            LowpassFilter(cutoff_frequency_hz=10000.0),
            Gain(gain_db=-9.0),
        ])(a, int(sr)).astype(np.float32)
        y = (a + air * 0.08).astype(np.float32)
        try:
            _EXC_LAST["ran"] = True
        except Exception:
            pass
        return _headroom(y, -1.0).astype(np.float32)
    except Exception as _e:
        try:
            _EXC_LAST["error"] = str(_e)[:200]
        except Exception:
            pass
        return x'''

new_e = '''def _exciter(x, sr):
    """Tier-1 asymmetric 5-10k exciter (Numba + polyphase 2x)."""
    try:
        import dsp_tier1
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[1] == 0:
            return x
        y = dsp_tier1.exciter(a, int(sr), drive_db=8.0, blend=0.08)
        _EXC_LAST["ran"] = True
        return _headroom(y, -1.0).astype(np.float32)
    except Exception as _e:
        try:
            _EXC_LAST["error"] = str(_e)[:200]
        except Exception:
            pass
        return x'''

n = s.count(old_e)
if n != 1:
    sys.exit("ABORT: _exciter body matched %d (need 1) - NOTHING written" % n)
s = s.replace(old_e, new_e, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  _exciter swapped to dsp_tier1.exciter")
print("SYNTAX OK")
