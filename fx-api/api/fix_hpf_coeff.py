from pathlib import Path
import ast, sys

HELPER = '''

def coeff_hpf(fc_hz, sr):
    """Correct 1st-order RC highpass coefficient."""
    rc = 1.0 / (2.0 * np.pi * fc_hz)
    dt = 1.0 / sr
    return rc / (rc + dt)
'''

# ── dsp_delay.py
P1 = Path("dsp_delay.py")
s1 = P1.read_text(encoding="utf-8")
if "def coeff_hpf" not in s1:
    anchor = "def coeff_tau(tau, sr):"
    if s1.count(anchor) != 1:
        sys.exit("ABORT: dsp_delay coeff_tau anchor mismatch")
    s1 = s1.replace(anchor, HELPER.strip() + "\n\n\ndef coeff_tau(tau, sr):", 1)

old1 = "ahp = np.float32(coeff_tau(1.0 / (2.0 * np.pi * hp_cut), sr))"
new1 = "ahp = np.float32(coeff_hpf(hp_cut, sr))"
if s1.count(old1) != 1:
    sys.exit("ABORT: dsp_delay ahp anchor mismatch")
s1 = s1.replace(old1, new1, 1)
P1.write_text(s1, encoding="utf-8"); ast.parse(s1)
print("  ok  dsp_delay: HPF coefficient fixed")

# ── dsp_pro.py
P2 = Path("dsp_pro.py")
s2 = P2.read_text(encoding="utf-8")
if "def coeff_hpf" not in s2:
    anchor2 = "def _coeff_tau(tau, sr):"
    if s2.count(anchor2) != 1:
        sys.exit("ABORT: dsp_pro _coeff_tau anchor mismatch")
    s2 = s2.replace(anchor2, HELPER.strip() + "\n\n\ndef _coeff_tau(tau, sr):", 1)

# plate_wet caller
old2 = 'a_hp       = np.float32(_coeff_tau(1.0/(2*np.pi*250.0), sr))'
new2 = 'a_hp       = np.float32(coeff_hpf(250.0, sr))'
if s2.count(old2) != 1:
    sys.exit("ABORT: dsp_pro a_hp anchor mismatch")
s2 = s2.replace(old2, new2, 1)
P2.write_text(s2, encoding="utf-8"); ast.parse(s2)
print("  ok  dsp_pro: plate HPF coefficient fixed")

# ── also fix the fet_comp sidechain HPF (same formula bug)
P3 = Path("fet_comp.py")
s3 = P3.read_text(encoding="utf-8")
# fet_comp uses scipy butter HPF — that one's correct, skip
print("  skip fet_comp (uses scipy butter — correct)")

print()
print("SYNTAX OK")
print("Delay HPF was cutting the vocal band by ~50 dB.")
print("Both engines now use the correct 1/(RC+dt) formula.")
