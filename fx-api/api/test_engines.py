import numpy as np
try:
    import numba  # noqa
except ImportError:
    print("numba not installed locally — cannot test engines here")
    raise SystemExit

import dsp_delay
import dsp_pro

sr = 44100
dur = 5.0
n = int(sr * dur)
t = np.arange(n) / sr
x = (0.3 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2 * t))).astype(np.float32)
xs = np.stack([x, x])

wet, info = dsp_delay.delay_render(xs, sr, bpm=99.4, note_div=0.25)
print("── DELAY ──")
print("  dry rms: %.6f" % np.sqrt(np.mean(xs ** 2)))
print("  wet rms: %.6f" % np.sqrt(np.mean(wet ** 2)))
print("  rel dB: %.2f" % (20 * np.log10(np.sqrt(np.mean(wet ** 2)) / np.sqrt(np.mean(xs ** 2)) + 1e-12)))
print("  info:", info)

plate = dsp_pro.plate_wet(xs, sr, mix=1.0, duck_depth=0.25)
print("── PLATE ──")
if plate is None:
    print("  returned None")
else:
    print("  dry rms: %.6f" % np.sqrt(np.mean(xs ** 2)))
    print("  wet rms: %.6f" % np.sqrt(np.mean(plate ** 2)))
    print("  rel dB: %.2f" % (20 * np.log10(np.sqrt(np.mean(plate ** 2)) / np.sqrt(np.mean(xs ** 2)) + 1e-12)))
