from pathlib import Path
import ast, sys
P = Path("fx-api/api/mix.py")
s = P.read_text(encoding="utf-8")

ANCHOR = '''        mode = report.get("mode")
        n = mixed.shape[1]
        want = str(loud or "MEDIUM").upper()
'''
INSERT = '''        # Low-mid stereo narrowing. Against two commercial references our
        # side energy was 6-8 dB high at 80-600 Hz while 0-80 Hz and
        # 1.5-4 kHz already matched. Halving the side below ~600 Hz puts the
        # kick/bass body back on centre and restores mono compatibility.
        # Skipped on master: its input is already a narrowed mix.
        if mode not in ("master", "passthrough") and mixed.shape[0] >= 2:
            _mid = (mixed[0] + mixed[1]) * 0.5
            _side = (mixed[0] - mixed[1]) * 0.5
            _hi = Pedalboard([HighpassFilter(cutoff_frequency_hz=600.0)])(
                _side[None, :], sr)[0]
            _side = (_hi + 0.5 * (_side - _hi)).astype(np.float32)
            mixed = np.stack([_mid + _side, _mid - _side]).astype(np.float32)
            report["low_mid_guard_hz"] = 600.0
            report["low_mid_side_trim_db"] = -6.0
'''
if s.count(ANCHOR) != 1:
    sys.exit("ABORT: anchor matched %d times - NOTHING written" % s.count(ANCHOR))
s = s.replace(ANCHOR, ANCHOR + "\n" + INSERT, 1)
P.write_text(s, encoding="utf-8")
ast.parse(s)
print("  ok  low-mid side narrowed -6 dB below 600 Hz (skipped on master)")
print("SYNTAX OK")
