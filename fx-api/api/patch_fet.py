from pathlib import Path
import ast, sys

P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''    out = Pedalboard(ch)(voc, sr).astype(np.float32)

    # LA-2A style opto compression — program-dependent, two-stage release.'''

new = '''    out = Pedalboard(ch)(voc, sr).astype(np.float32)

    # --- 1176-style FET stage (UREI Rev D topology, feedback, near-instant attack).
    #     Runs BEFORE the LA-2A: FET catches peaks, LA-2A glues the body.
    if role in ("lead", "adlib", "backing"):
        try:
            import fet_comp
            _fet_rms = _rms_db(out)
            _fet_thr = float(np.clip(_fet_rms + 3.0, -30.0, -8.0))
            _fet_out, _fet_info = fet_comp.fet_compress(
                out, sr,
                threshold_db=_fet_thr,
                ratio=4.0,
                attack_ms=0.100,
                release_ms=250.0,
                sidechain_hpf_hz=90.0,
                sat_drive=0.10,
            )
            out = _fet_out
            moves.append(["fet", "1176 4:1 @ %.1f  gr %.2f" % (
                _fet_thr, _fet_info.get("max_gr_db", 0.0))])
            moves.append(["fet-model", _fet_info.get("model", "")])
        except Exception as _fe:
            moves.append(["fet-error", str(_fe)[:80]])

    # LA-2A style opto compression — program-dependent, two-stage release.'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: anchor matched %d times (need 1) - NOTHING written" % n)

s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8")
ast.parse(s)
print("  ok  1176 FET stage inserted before LA-2A")
print("SYNTAX OK")
