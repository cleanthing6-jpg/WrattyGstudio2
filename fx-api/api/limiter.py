"""Minimal limiter. Replaces pedalboard.Limiter. Bass preserved via sidechain HPF."""
import numpy as np
try:
    from numba import njit
except ImportError:
    def njit(*a, **k):
        if a and callable(a[0]): return a[0]
        def wrap(f): return f
        return wrap


@njit(cache=False)
def _run(x, ceil, look_n, buf, env, s1, s2, b0, b1, b2, a1, a2, c_rel):
    out = np.empty_like(x)
    idx = 0
    for i in range(len(x)):
        s = x[i]
        f = b0 * s + s1
        s1 = b1 * s - a1 * f + s2
        s2 = b2 * s - a2 * f
        a = abs(f)
        if a > env:
            env = a
        else:
            env = a + c_rel * (env - a)
        g = ceil / env if env > ceil else 1.0
        out[i] = buf[idx] * g
        buf[idx] = s
        idx = (idx + 1) % look_n
    return out, env, s1, s2


class Limiter:
    def __init__(self, threshold_db=-10.0, release_ms=100.0, lookahead_ms=2.0,
                 sc_hpf_hz=120.0):
        self.t = float(threshold_db)
        self.r = float(release_ms)
        self.l = float(lookahead_ms)
        self.f = float(sc_hpf_hz)
        self.sr = None
        self._init(44100)

    def _init(self, sr):
        self.sr = sr
        self.n = max(1, int(self.l / 1000.0 * sr))
        self.buf_L = np.zeros(self.n, dtype=np.float32)
        self.buf_R = np.zeros(self.n, dtype=np.float32)
        self.env = 0.0
        self.s1 = 0.0
        self.s2 = 0.0
        w = 2.0 * np.pi * self.f / sr
        cw = np.cos(w)
        al = np.sin(w) / (2.0 * 0.707)
        a0 = 1.0 + al
        self.b0 = np.float32((1.0 + cw) / 2.0 / a0)
        self.b1 = np.float32(-(1.0 + cw) / a0)
        self.b2 = np.float32((1.0 + cw) / 2.0 / a0)
        self.a1 = np.float32(-2.0 * cw / a0)
        self.a2 = np.float32((1.0 - al) / a0)
        self.c_rel = np.float32(np.exp(-1.0 / ((self.r / 1000.0) * sr)))

    def process(self, audio, sample_rate, buffer_size=None):
        if sample_rate != self.sr:
            self._init(int(sample_rate))
        a = np.ascontiguousarray(audio, dtype=np.float32)
        mono = a.ndim == 1
        if mono:
            a = np.stack([a, a])
        elif a.shape[0] == 1:
            a = np.stack([a[0], a[0]])
        self.buf_L[:] = 0
        self.buf_R[:] = 0
        ceil = np.float32(10.0 ** (self.t / 20.0))
        L, _, _, _ = _run(
            a[0].copy(), ceil, self.n, self.buf_L, 0.0,
            0.0, 0.0, self.b0, self.b1, self.b2, self.a1, self.a2,
            self.c_rel)
        R, _, _, _ = _run(
            a[1].copy(), ceil, self.n, self.buf_R, 0.0,
            0.0, 0.0, self.b0, self.b1, self.b2, self.a1, self.a2,
            self.c_rel)
        out = np.stack([L, R])
        pk = max(float(np.max(np.abs(out[0]))), float(np.max(np.abs(out[1]))))
        if pk > ceil:
            out = out * (float(ceil) / pk)
        if mono:
            out = out.mean(axis=0, keepdims=True)
        return out

    def reset(self):
        self.buf_L[:] = 0
        self.buf_R[:] = 0
        self.env = 0.0
        self.s1 = 0.0
        self.s2 = 0.0

    def __call__(self, audio, sample_rate):
        return self.process(audio, sample_rate)
