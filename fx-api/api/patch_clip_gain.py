from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = "    out = Pedalboard(ch)(voc, sr).astype(np.float32)"
new = '''    # --- Clip-gain ride: level-neutral pre-stage (relative to own average).
    if role in ("lead", "adlib", "backing"):
        try:
            import clip_gain
            _cg_in = _rms_db(voc)
            voc = clip_gain.clip_gain_ride(voc, sr, window_ms=100.0,
                                           max_gain_db=3.0,
                                           silence_threshold_db=-42.0)
            _cg_out = _rms_db(voc)
            moves.append(["clip-gain", "linked +/-3dB  100ms  mean shift %.2f dB" % (_cg_out - _cg_in)])
        except Exception as _cge:
            moves.append(["clip-gain-error", str(_cge)[:80]])

    out = Pedalboard(ch)(voc, sr).astype(np.float32)'''
n = s.count(old)
if n != 1:
    sys.exit("ABORT: matched %d (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  clip-gain wired before pedalboard")
print("SYNTAX OK")
