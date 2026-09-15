"""BS.1770-4 integrated loudness in pure NumPy. No SciPy. Memory-safe."""
import numpy as np

_KW = {
    48000: ((1.53512485958697, -2.69169618940638, 1.19839281085285,
             -1.69065929318241, 0.73248077421585),
            (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)),
    44100: ((1.530841230050348, -2.650979995154729, 1.169079079921587,
             -1.663655113256020, 0.712595428073225),
            (0.999560064542514, -1.999120129085029, 0.999560064542514,
             -1.989169673629796, 0.989199035787039)),
}


def _ir(c, n=16384):
    b0, b1, b2, a1, a2 = c
    out = np.zeros(n)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        x0 = 1.0 if i == 0 else 0.0
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x0
        y2, y1 = y1, y0
        out[i] = y0
    return out.astype(np.float32)


def _fftconv(x, ir, blk=1 << 15):
    n, m = len(x), len(ir)
    nfft = 1 << (blk + m - 1).bit_length()
    H = np.fft.rfft(ir, nfft)
    out = np.zeros(n + m, dtype=np.float64)
    for p in range(0, n, blk):
        seg = np.fft.irfft(np.fft.rfft(x[p:p + blk], nfft) * H, nfft)
        q = min(p + nfft, out.size)
        out[p:q] += seg[:q - p]
    return out[:n]


def _blockpow(y2, n, hop):
    c = np.concatenate(([0.0], np.cumsum(y2)))
    s = np.arange(0, len(y2) - n + 1, hop)
    return (c[s + n] - c[s]) / n


def lufs(x, sr):
    """Integrated loudness (LUFS). x: (channels, samples) float32."""
    fs = int(round(sr))
    key = min(_KW, key=lambda k: abs(k - fs))
    a, b = _KW[key]
    ir1, ir2 = _ir(a), _ir(b)
    n, hop = int(0.4 * fs), int(0.1 * fs)

    z = None
    for ch in x:
        y = _fftconv(_fftconv(np.asarray(ch, np.float64), ir1), ir2)
        zs = _blockpow(y * y, n, hop)
        z = zs if z is None else z + zs
        del y
    if z is None or z.size == 0:
        return None

    lj = -0.691 + 10.0 * np.log10(np.maximum(z, 1e-12))
    keep = lj >= -70.0
    if not keep.any():
        return None
    rel = -0.691 + 10.0 * np.log10(z[keep].mean()) - 10.0
    keep &= lj > rel
    return float(-0.691 + 10.0 * np.log10(z[keep].mean())) if keep.any() else None
