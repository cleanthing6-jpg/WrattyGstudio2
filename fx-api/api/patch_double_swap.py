from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''def _double(voc, sr):
    # PitchShift is optional - without it the two copies still differ
    # by delay (14/22 ms) and pan, which combs and widens on its own.
    try:
        out = np.zeros_like(voc)
        for cents, ms, pan in ((7.0, 14.0, 0.30), (-6.0, 22.0, -0.30)):
            ch = ([] if PitchShift is None else [PitchShift(semitones=cents / 100.0)]) + [
                  HighpassFilter(cutoff_frequency_hz=150.0),
                  LowpassFilter(cutoff_frequency_hz=10000.0)]
            _opt(ch, Chorus, rate_hz=0.4, depth=0.06, mix=0.25)
            ch.append(Delay(delay_seconds=ms / 1000.0, feedback=0.0, mix=1.0))
            y = Pedalboard(ch)(voc, sr).astype(np.float32)
            y[0] *= float(np.sqrt(max(0.0, (1.0 - pan) * 0.5)) * 1.414)
            y[1] *= float(np.sqrt(max(0.0, (1.0 + pan) * 0.5)) * 1.414)
            out += y
        out *= 10.0 ** (DOUBLE_DB / 20.0)
        _DBL["kind"] = "adt (detune+delay+pan)" if PitchShift is not None else "delays+pan only (no PitchShift)"
        return out
    except Exception as _e:
        _DBL["error"] = repr(_e)
        return None'''

new = '''def _double(voc, sr):
    """Tier-1 LFO ADT doubler (cubic Hermite, polyphase, live taps 14/22 ms)."""
    try:
        import dsp_tier1
        blend = 10.0 ** (DOUBLE_DB / 20.0)
        out = dsp_tier1.adt_double(
            voc, sr,
            depth_ms=14.0,
            rate_hz=0.5,
            right_offset_ms=8.0,
            pan=0.30,
            blend=blend,
        )
        _DBL["kind"] = "adt (LFO+cubic, 14/22ms, +/-0.30pan)"
        return out
    except Exception as _e:
        _DBL["error"] = repr(_e)
        return None'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: _double body matched %d (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  _double swapped to dsp_tier1.adt_double")
print("SYNTAX OK")
