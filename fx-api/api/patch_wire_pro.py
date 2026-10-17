from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

# ── 1. LA-2A: opto_comp.opto_compress → dsp_pro.la2a_compress
s = rep(s, "opto_comp.opto_compress(", "dsp_pro.la2a_compress(", 1, "LA-2A call site → dsp_pro")
s = rep(s, "        import opto_comp\n", "        import dsp_pro\n        import opto_comp\n", 1, "import dsp_pro alongside opto_comp")

# ── 2. _saturate body → pro_saturator
old_sat = '''def _saturate(x, sr, drive_db):
    """Tube-style saturation. Asymmetric bias generates even harmonics
    (2nd, 4th) — warm, musical character, not the odd-harmonic grit of a
    generic distortion. Level-matched so mix balance stays the same."""
    if drive_db is None or drive_db <= 0.001:
        return x
    try:
        import numpy as _np
        a = _np.asarray(x, dtype=_np.float32)
        d = 1.0 + float(drive_db) * 2.0
        b = 0.15 * float(drive_db)
        y = _np.tanh(a * d + b) - _np.tanh(b)
        y = y + 0.15 * float(drive_db) * (y ** 2) * _np.sign(y)
        ri = _np.sqrt(_np.mean(a ** 2)) + 1e-9
        ro = _np.sqrt(_np.mean(y ** 2)) + 1e-9
        return (y * (ri / ro)).astype(_np.float32)
    except Exception:
        return x'''

new_sat = '''def _saturate(x, sr, drive_db):
    """Tier-1 C2-continuous saturator, 4x polyphase OS, Numba'd."""
    if drive_db is None or drive_db <= 0.001:
        return x
    try:
        import dsp_pro
        return dsp_pro.pro_saturator(x, sr, drive_db=float(drive_db))
    except Exception:
        return x'''
s = rep(s, old_sat, new_sat, 1, "_saturate → pro_saturator")

# ── 3. _deess body → pro_deesser (returns tuple preserved)
old_de = '''def _deess(voc, sr, st):
    """Sibilance control calibrated off the band's own level so it fires when
    sibilance is actually present. Runs BEFORE the air shelf in _role_chain."""
    freq = np.fft.rfftfreq(N, 1.0 / sr)
    k = (freq >= 5500) & (freq < 9000)
    if not np.any(k):
        return voc, 0.0
    out = np.empty_like(voc)
    mx = 0.0
    for c in range(voc.shape[0]):
        S = _stft(voc[c])
        lev = _level_db(S, k)
        thr = float(np.median(lev)) + DEESS_OFFSET_DB
        red = _smooth(np.clip(lev - thr, 0.0, MAX_DEESS), atk=DEESS_ATK, rel=DEESS_REL)
        mx = max(mx, float(np.max(red)))
        S[:, k] *= (10.0 ** (-red / 20.0))[:, None]
        out[c] = _istft(S, voc.shape[1])
        del S
    return out, round(mx, 2)'''

new_de = '''def _deess(voc, sr, st):
    """Tier-1 split-band lookahead de-esser (5.5kHz crossover, 5ms lookahead)."""
    try:
        import dsp_pro
        return dsp_pro.deess_drop_in(voc, sr, st, ratio=4.0)
    except Exception as _de:
        return voc, 0.0'''
s = rep(s, old_de, new_de, 1, "_deess → pro_deesser")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
