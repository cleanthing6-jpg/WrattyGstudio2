from pathlib import Path
import ast, sys
P = Path("fx-api/api/mix.py")
s = P.read_text(encoding="utf-8")

OLD = '''            if mode != "passthrough":
                mixed = mixed * (10.0 ** ((-6.0 - peakdb(mixed)) / 20.0))
                setjob(jid, "glue bus")'''
OLD_IND = '''        if mode != "passthrough":
            mixed = mixed * (10.0 ** ((-6.0 - peakdb(mixed)) / 20.0))
            setjob(jid, "glue bus")
            _gr = float(cfg.get("glue_gr_db", 1.0))
            _rat = float(cfg.get("glue_ratio", 1.5))
            _over = _gr * _rat / max(0.1, _rat - 1.0)
            _thr = float(np.clip(rmsdb(mixed) - _over, -40.0, -6.0))
            mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                                Compressor(threshold_db=_thr, ratio=_rat,
                                           attack_ms=30.0, release_ms=130.0)])(mixed, sr).astype(np.float32)
            report["glue_thr_db"] = round(_thr, 2)'''

NEW = '''        if mode != "passthrough":
            mixed = mixed * (10.0 ** ((-6.0 - peakdb(mixed)) / 20.0))
            setjob(jid, "glue bus")
            if mode == "two_track":
                # beat is already mastered - keep 30 Hz rumble guard, skip the compressor
                mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30)])(mixed, sr).astype(np.float32)
                report["glue_thr_db"] = "off (two_track)"
            else:
                _gr = float(cfg.get("glue_gr_db", 1.0))
                _rat = float(cfg.get("glue_ratio", 1.5))
                _over = _gr * _rat / max(0.1, _rat - 1.0)
                _thr = float(np.clip(rmsdb(mixed) - _over, -40.0, -6.0))
                mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                                    Compressor(threshold_db=_thr, ratio=_rat,
                                               attack_ms=30.0, release_ms=130.0)])(mixed, sr).astype(np.float32)
                report["glue_thr_db"] = round(_thr, 2)'''

if s.count(OLD_IND) != 1:
    sys.exit("ABORT glue block: matched %d times - NOTHING written" % s.count(OLD_IND))
s = s.replace(OLD_IND, NEW, 1)

OLD_LOOP = '''        for _ in range(8):
            f = lufs(mixed, sr)'''
NEW_LOOP = '''        for _ in range(2):
            f = lufs(mixed, sr)'''
if s.count(OLD_LOOP) != 1:
    sys.exit("ABORT limit loop: matched %d times - NOTHING written" % s.count(OLD_LOOP))
s = s.replace(OLD_LOOP, NEW_LOOP, 1)

P.write_text(s, encoding="utf-8")
ast.parse(P.read_text(encoding="utf-8"))
print("OK: glue off for two_track (30 Hz guard kept); limit loop 8 -> 2")
