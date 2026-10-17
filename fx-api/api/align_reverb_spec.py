from pathlib import Path
import ast, sys

P = Path("dsp_pro.py")
s = P.read_text(encoding="utf-8")

# ── 1. Decay: cap IR at 1.8 s
old = 'def _load_ir(path, sr_target=44100, max_len=6*48000):'
new = 'def _load_ir(path, sr_target=44100, max_len=int(1.8*48000)):'
if s.count(old) != 1:
    sys.exit("ABORT: _load_ir signature mismatch")
s = s.replace(old, new, 1)
print("  ok  _load_ir decay cap: 6 s -> 1.8 s")

# ── 2. HPF 250 -> 150 (anchor matches current state after coeff_hpf fix)
old = 'a_hp       = np.float32(coeff_hpf(250.0, sr))'
new = 'a_hp       = np.float32(coeff_hpf(150.0, sr))'
if s.count(old) != 1:
    sys.exit("ABORT: HPF anchor mismatch (current: %d)" % s.count(old))
s = s.replace(old, new, 1)
print("  ok  plate HPF: 250 Hz -> 150 Hz")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
