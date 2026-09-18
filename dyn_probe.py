#!/usr/bin/env python3
import sys, os
import numpy as np
import vocal_probe as vp

def probe(path):
    if not os.path.exists(path):
        print("=== MISSING: %s" % path); return
    x, sr = vp.load(path)
    m = np.mean(x, axis=0)
    peak = vp.db(np.max(np.abs(x))); full = vp.db(vp.rms(m))
    w = max(1, int(sr * 0.02))
    r = np.array([vp.rms(m[i:i+w]) for i in range(0, max(1, len(m)-w), w)])
    r = r[r > 1e-8]; lv = 20*np.log10(r + 1e-12)
    b = max(1, int(sr * 0.40))
    rb = np.array([vp.rms(m[i:i+b]) for i in range(0, max(1, len(m)-b), b)])
    rb = rb[rb > 1e-8]; lb = 20*np.log10(rb + 1e-12)
    print("=== %s" % os.path.basename(path))
    print("  dur %.0fs  peak %6.2f  rms %6.2f  crest %5.2f dB  clip %.4f%%" %
          (len(m)/sr, peak, full, peak-full, 100.0*np.mean(np.abs(x) >= 0.999)))
    print("  micro 20ms   p10 %6.2f  med %6.2f  p90 %6.2f  spread %5.2f  sd %4.2f  within1.5dB %3.0f%%" % (
        vp.db(np.percentile(r, 10)), vp.db(np.percentile(r, 50)), vp.db(np.percentile(r, 90)),
        vp.db(np.percentile(r, 90)) - vp.db(np.percentile(r, 10)), float(np.std(lv)),
        100.0*np.mean(np.abs(lv - np.median(lv)) < 1.5)))
    print("  block 400ms  p10 %6.2f  med %6.2f  p90 %6.2f  spread %5.2f" % (
        vp.db(np.percentile(rb, 10)), vp.db(np.percentile(rb, 50)), vp.db(np.percentile(rb, 90)),
        vp.db(np.percentile(rb, 90)) - vp.db(np.percentile(rb, 10))))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 dyn_probe.py file1 [file2 ...]")
    for p in sys.argv[1:]:
        probe(p); print()
