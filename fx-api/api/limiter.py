"""Pro limiter. Replaces pedalboard.Limiter.

Bass preserved via sidechain HPF on detector path.
Two-stage envelope (transient + sustain). Auto-release curve.
Stereo-linked detector. Lookahead. Peak safety net.
"""
import numpy as np
try:
    from numba import njit
except ImportError:
    def njit(*a, **k):
        if a and callable(a[0]): return a[0]
        def wrap(f): return f
        return wrap


@njit(cache=False)
def _kernel(L, R, ceil, look_n, bufL, bufR,
            b0, b1, b2, a1, a2,
            c_trans, c_sust, r_slow, r_fast, state):
    t = state[0]; s = state[1]; m = state[2]
    v1L = state[3]; v2L = state[4]
    v1R = state[5]; v2R = state[6]
    idx = 0
    n = len(L)
    outL = np.empty(n, dtype=np.float32)
    outR = np.empty(n, dtype=np.float32)
    for i in range(n):
        l = L[i]; r = R[i]
        fL = b0 * l + v1L
        v1L = b1 * l - a1 * fL + v2L
        v2L = b2 * l - a2 * fL
        fR = b0 * r + v1R
        v1R = b1 * r - a1 * fR + v2R
        v2R = b2 * r - a2 * fR
        aL = abs(fL); aR = abs(fR)
        det = max(aL, aR)
        if det > t: t = det
        else: t = det + c_trans * (t - det)
        if det > s: s = det + c_sust * (s - det)
        else: s = det + r_slow * (s - det)
        cr = r_fast if t > (s * 1.65) else r_slow
        tg = max(t, s)
        if tg > m: m = tg
        else: m = tg + cr * (m - tg)
        g = ceil / m if m > ceil else 1.0
        outL[i] = bufL[idx] * g
        outR[i] = bufR[idx] * g
        bufL[idx] = l
        bufR[idx] = r
        idx = (idx + 1) % look_n
    state[0] = t; state[1] = s; state[2] = m
    state[3] = v1L; state[4] = v2L
    state[5] = v1R; state[6] = v2R
    return outL, outR


class Limiter:
    def __init__(self, threshold_db=-10.0, release_ms=100.0,
                 lookahead_ms=2.0, sc_hpf_hz=120.0):
        self.t = float(threshold_db)
        self.r = float(release_ms)
        self.l = float(lookahead_ms)
        self.f = float(sc_hpf_hz)
        self.sr = None
        self._init(44100)

    def _init(self, sr):
        self.sr = sr
        self.n = max(1, int(self.l / 1000.0 * sr))
        self.bufL = np.zeros(self.n, dtype=np.float32)
        self.bufR = np.zeros(self.n, dtype=np.float32)
        self.state = np.zeros(7, dtype=np.float32)
        self.c_trans = np.float32(np.exp(-1.0 / (0.002 * sr)))
        self.c_sust = np.float32(np.exp(-1.0 / (0.025 * sr)))
        self.r_slow = np.float32(np.exp(-1.0 / ((self.r / 1000.0) * sr)))
        self.r_fast = np.float32(np.exp(-1.0 / ((self.r / 1000.0) * 0.15 * sr)))
        w = 2 * np.pi * self.f / sr
        cw = np.cos(w)
        al = np.sin(w) / (2 * 0.707)
        a0 = 1 + al
        self.b0 = np.float32((1 + cw) / 2 / a0)
        self.b1 = np.float32(-(1 + cw) / a0)
        self.b2 = np.float32((1 + cw) / 2 / a0)
        self.a1 = np.float32(-2 * cw / a0)
        self.a2 = np.float32((1 - al) / a0)

    def process(self, audio, sample_rate, buffer_size=None):
        if sample_rate != self.sr:
            self._init(int(sample_rate))
        a = np.ascontiguousarray(audio, dtype=np.float32)
        mono = a.ndim == 1
        if mono:
            a = np.stack([a, a])
        elif a.shape[0] == 1:
            a = np.stack([a[0], a[0]])
        ceil = np.float32(10.0 ** (self.t / 20.0))
        L, R = _kernel(a[0].copy(), a[1].copy(), ceil, self.n,
                       self.bufL, self.bufR,
                       self.b0, self.b1, self.b2, self.a1, self.a2,
                       self.c_trans, self.c_sust, self.r_slow, self.r_fast,
                       self.state)
        out = np.stack([L, R])
        pk = max(float(np.max(np.abs(out[0]))), float(np.max(np.abs(out[1]))))
        if pk > ceil:
            out = out * (float(ceil) / pk)
        if mono:
            out = out.mean(axis=0, keepdims=True)
        return out

    def reset(self):
        self.bufL[:] = 0
        self.bufR[:] = 0
        self.state[:] = 0

    def __call__(self, audio, sample_rate):
        return self.process(audio, sample_rate)
