#!/usr/bin/env python3
import sys, os
import numpy as np
import vocal_probe as vp

BANDS = [(0,80),(80,250),(250,600),(1500,4000),(5500,9000)]

def bp(x, sr, lo, hi):
    n = len(x); f = np.fft.rfftfreq(n, 1.0 / sr)
    Z = np.fft.rfft(x)
    Z = np.where((f >= lo) & (f < hi), Z, 0.0)
    return np.fft.irfft(Z, n)

def probe(path):
    if not os.path.exists(path):
        print("=== MISSING: %s" % path); return
    x, sr = vp.load(path)
    if x.shape[0] < 2:
        print("=== %s (mono)" % os.path.basename(path)); return
    L, R = x[0], x[1]
    win = max(1024, int(sr * 0.05))
    chunk = int(sr * 20)
    cs = {b: [] for b in BANDS}; sm = {b: [] for b in BANDS}
    for c0 in range(0, len(L) - win * 8, chunk):
        Lc = L[c0:c0 + chunk]; Rc = R[c0:c0 + chunk]
        for lo, hi in BANDS:
            a = bp(Lc, sr, lo, hi); b = bp(Rc, sr, lo, hi)
            for s in range(0, len(a) - win, win):
                p = a[s:s + win]; q = b[s:s + win]
                if np.std(p) < 1e-7 or np.std(q) < 1e-7: continue
                d = float(np.corrcoef(p, q)[0, 1])
                if np.isfinite(d): cs[(lo, hi)].append(d)
                rm = vp.rms((p + q) * 0.5); rs = vp.rms((p - q) * 0.5)
                if rm > 1e-9: sm[(lo, hi)].append(20.0 * np.log10(rs / rm))
    print("=== %s" % os.path.basename(path))
    print("     band              corr   side-mid")
    for lo, hi in BANDS:
        c = np.median(cs[(lo, hi)]) if cs[(lo, hi)] else 0.0
        m = np.median(sm[(lo, hi)]) if sm[(lo, hi)] else -120.0
        print("  %6d-%-7d %6.3f  %+7.2f dB" % (lo, hi, c, m))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python3 stereo_probe.py file1 [file2 ...]")
    for p in sys.argv[1:]:
        probe(p); print()
