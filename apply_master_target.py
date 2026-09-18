from pathlib import Path
import ast, sys
P = Path("fx-api/api/mix.py")
s = P.read_text(encoding="utf-8")
OLD = '''        tgt = TARGET.get(want)
        if tgt is None:
            tgt = float(cfg.get("target_lufs", -14.0))
        cur = lufs(mixed, sr)'''
NEW = '''        tgt = TARGET.get(want)
        if tgt is None:
            tgt = float(cfg.get("target_lufs", -14.0))
        if mode == "master":
            tgt = tgt + float(cfg.get("master_lift_db", 2.5))
        else:
            tgt = tgt - float(cfg.get("mix_headroom_db", 2.5))
        cur = lufs(mixed, sr)'''
if s.count(OLD) != 1:
    sys.exit("ABORT: matched %d times - NOTHING written" % s.count(OLD))
P.write_text(s.replace(OLD, NEW, 1), encoding="utf-8")
ast.parse(P.read_text(encoding="utf-8"))
print("OK: master +2.5 LUFS, mix -2.5 LUFS")
