from pathlib import Path
import ast, sys
P = Path("dsp_pro.py")
s = P.read_text(encoding="utf-8")

old = '''    ir = ir[:max_len]
    fade = int(0.05 * sr_target)
    if len(ir) > fade:
        w = np.ones(len(ir), dtype=np.float32)
        w[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        ir *= w
    _IR_CACHE[key] = ir
    return ir'''

new = '''    ir = ir[:max_len]
    fade = int(0.05 * sr_target)
    if len(ir) > fade:
        w = np.ones(len(ir), dtype=np.float32)
        w[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        ir *= w
    # Energy-normalize so convolution yields ~unity gain (conventional
    # reverb IR prep — without this, wet output is +20-25 dB above dry).
    energy = float(np.sum(ir.astype(np.float64) ** 2))
    if energy > 1e-12:
        ir = (ir / np.sqrt(energy)).astype(np.float32)
    _IR_CACHE[key] = ir
    return ir'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: _load_ir anchor matched %d" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  _load_ir: energy-normalized")
print("SYNTAX OK")
