from pathlib import Path
import ast, sys

A = Path("auto.py")
F = Path("fet_comp.py")
a = A.read_text(encoding="utf-8")
f = F.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

# --- 1) FET: medium-fast attack (3 ms), peaks-only (rms+9)
a = rep(a,
    "attack_ms=0.100,",
    "attack_ms=3.0,",
    1, "FET attack 0.1ms -> 3ms (medium-fast, anti-smear)")
a = rep(a,
    "_fet_thr = float(np.clip(_fet_rms + 7.0, -30.0, -6.0))",
    "_fet_thr = float(np.clip(_fet_rms + 9.0, -30.0, -6.0))",
    1, "FET threshold rms+7 -> rms+9 (targets 3-6 dB GR)")

# --- 3) TOP END: de-ess 3.5 -> 2.5, air 0.3 -> 2.0
a = rep(a, '"deess_offset_db": 2.5,', '"deess_offset_db": 2.5,', 1, "deess offset (no change, marker)")
a = rep(a, '"air": 0.3, "ratio": 2.5, "atk": 5.0, "rel": 100.0,',
           '"air": 2.0, "ratio": 2.5, "atk": 5.0, "rel": 100.0,',
           1, "lead air 0.3 -> 2.0 (list: +1.5 to +3)")
a = rep(a, '"max_deess": 3.5,', '"max_deess": 2.5,', 1, "de-ess cap 3.5 -> 2.5 (list: 1-3)")

# --- 2) TONE: body boost 200-300 Hz, +2.0 dB on lead
a = rep(a,
'''        "role_treat_lead": {
            "gain": 0.0, "hpf": 95.0,''',
'''        "role_treat_lead": {
            "gain": 0.0, "hpf": 95.0, "body_db": 2.0,''',
1, "lead body_db 0 -> +2.0 (list: warm at 200-300 Hz)")

# --- 3) EXCITER band: 9-14k -> 5-10k (list target)
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
1, "exciter band 9-14k -> 5-10k (list target)")

A.write_text(a, encoding="utf-8")
ast.parse(a)
print("SYNTAX OK")
print("revert: git checkout -- auto.py")
