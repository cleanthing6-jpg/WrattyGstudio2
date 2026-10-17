from pathlib import Path
import ast, sys

A = Path("auto.py")
a = A.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

# 1) FET: 4:1, medium-fast attack, fast release, 3-6 dB GR
a = rep(a, "attack_ms=0.100,",  "attack_ms=5.0,",  1, "FET attack -> 5 ms")
a = rep(a, "attack_ms=3.0,",    "attack_ms=5.0,",  0 if "attack_ms=3.0," not in a else 1, "FET attack (already 3) -> 5 ms") if "attack_ms=3.0," in a else a
a = rep(a, "release_ms=250.0,", "release_ms=80.0,", 1, "FET release -> 80 ms")
a = rep(a, "_fet_thr = float(np.clip(_fet_rms + 7.0, -30.0, -6.0))",
           "_fet_thr = float(np.clip(_fet_rms + 9.0, -30.0, -6.0))",
           1, "FET threshold -> rms+9")

# 2) HPF 90, body +2 @ 250, box -2.5 @ 600
a = rep(a, '"gain": 0.0, "hpf": 95.0,', '"gain": 0.0, "hpf": 90.0,', 1, "HPF 95 -> 90")
a = rep(a, '"box": 1.5, "box_hz": 600.0, "box_q": 1.0,\n            "pres": 0.8,',
           '"box": 2.5, "box_hz": 600.0, "box_q": 1.0,\n            "pres": 0.8,',
           1, "box 1.5 -> 2.5")

# 3) de-ess 2.5, air 2.0, exciter 5-10k
a = rep(a, '"max_deess": 3.5,', '"max_deess": 2.5,', 1, "de-ess cap -> 2.5")
a = rep(a, '"air": 0.3, "ratio": 2.5, "atk": 5.0, "rel": 100.0,',
           '"air": 2.0, "ratio": 2.5, "atk": 5.0, "rel": 100.0,',
           1, "air 0.3 -> 2.0")
a = rep(a,
'''        air = Pedalboard([
            HighpassFilter(cutoff_frequency_hz=9000.0),
            Distortion(drive_db=0.8),
            LowpassFilter(cutoff_frequency_hz=14000.0),
            Gain(gain_db=-9.0),
        ])(a, int(sr)).astype(np.float32)''',
'''        air = Pedalboard([
            HighpassFilter(cutoff_frequency_hz=5000.0),
            Distortion(drive_db=0.8),
            LowpassFilter(cutoff_frequency_hz=10000.0),
            Gain(gain_db=-9.0),
        ])(a, int(sr)).astype(np.float32)''',
1, "exciter 9-14k -> 5-10k")

A.write_text(a, encoding="utf-8")
ast.parse(a)
print("SYNTAX OK")
