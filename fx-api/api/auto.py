"""Automatic mix engine v3: measures the voice, makes room for it, then applies
a professional release chain. Every stage is capped, guarded and verified, so a
mix cannot come out harsh, phasing or clipping.
"""

import os
import numpy as np

try:
    import polish
except Exception:
    polish = None
import pedalboard
from pedalboard import (
    Pedalboard, HighpassFilter, LowpassFilter, PeakFilter, HighShelfFilter,
    Compressor, Limiter, Distortion, Clipping, Delay, Reverb,
)

for _n in ("BrickwallLimiter", "Convolution", "Mix", "Chorus", "PitchShift"):
    try:
        globals()[_n] = getattr(pedalboard, _n)
    except Exception:
        globals()[_n] = None

N = 2048
HOP = 1024

BANDS = [(80, 150), (150, 300), (300, 800), (800, 2000),
         (2000, 3500), (3500, 5500), (5500, 9000), (9000, 14000)]
BODY, PRES, HARSH = (800, 2000), (2000, 3500), (3500, 5500)
SIB, AIR, MUD, BOX = (5500, 9000), (9000, 14000), (150, 300), (300, 800)

MAX_MUD_CUT, MAX_BOX_CUT = 2.5, 1.5
MAX_PRESENCE, MAX_HARSH_CUT, MAX_AIR, MAX_DEESS = 1.5, 3.0, 3.0, 2.5
DEESS_OFFSET_DB = 8.0   # trigger this far above the band's own median
DEESS_ATK, DEESS_REL = 1.0, 4.0
DUCK_CAP = {BODY: 1.5, PRES: 3.0, HARSH: 2.0}
DUCK_TARGET = {BODY: 1.0, PRES: 2.5, HARSH: 1.5}

ROLE_TREAT = {
    "lead":    {"gain": -3.5,  "hpf": 100.0, "mud": 2.0, "box": 2.0, "pres": 1.2,
                "harsh": 1.5, "air": 2.0, "ratio": 3.5, "atk": 12.0, "rel": 80.0,
                "sat": 0.6, "width": 1.0},
    "adlib":   {"gain": -8.0, "hpf": 135.0, "mud": 2.0, "box": 1.5, "pres": 0.6,
                "harsh": 2.5, "air": 2.0, "ratio": 4.0, "atk": 7.0, "rel": 90.0,
                "sat": 1.2, "width": 1.30},
    "backing": {"gain": -8.0, "hpf": 140.0, "mud": 3.0, "box": 2.0, "pres": 0.0,
                "harsh": 2.0, "air": 1.0, "ratio": 2.5, "atk": 20.0, "rel": 160.0,
                "sat": 0.6, "width": 1.2},
    "other":   {"gain": -4.0, "hpf": 100.0, "mud": 2.0, "box": 1.0, "pres": 0.8,
                "harsh": 2.5, "air": 1.5, "ratio": 3.0, "atk": 10.0, "rel": 110.0,
                "sat": 1.5, "width": 1.10},
}

# ---------- genre presets (Deploy 1: neutral + afrobeats) ----------
PRESETS = {
    "neutral": {"width": 1.0},
    "afrobeats": {
        "target_lufs": -10.5, "glue_ratio": 1.5, "glue_gr_db": 0.8,
        "width": 1.12, "plate_db": -15.0, "slap_db": -18.0,
    },
    "pop": {
        "target_lufs": -11.5, "glue_ratio": 1.6, "glue_gr_db": 1.0,
        "width": 1.10, "plate_db": -16.0, "slap_db": -20.0,
    },
    "rnb": {
        "target_lufs": -14.0, "glue_ratio": 1.4, "glue_gr_db": 0.5,
        "width": 1.08, "plate_db": -13.0, "slap_db": -16.0,
    },
    "rap": {
        "target_lufs": -11.0, "glue_ratio": 1.8, "glue_gr_db": 1.2,
        "width": 1.06, "plate_db": -18.0, "slap_db": -22.0, "clip": True,
    },
}
ROLE_DELTAS = {
    "afrobeats": {"lead": {"air": 0.5, "sat": 0.4}, "backing": {"pres": -0.2}},
    "pop": {"lead": {"air": 1.0, "sat": 0.2}},
    "rnb": {"lead": {"air": 0.5, "sat": -0.1}},
    "rap": {"lead": {"air": -0.5, "sat": 0.6}, "backing": {"pres": -0.2}},
}
_PRESET = {}


def preset_config(name):
    p = str(name or "neutral").lower()
    if p not in PRESETS:
        p = "neutral"
    return p, dict(PRESETS[p])


def apply_preset(name):
    """Activate a preset. Returns its config dict."""
    global _PRESET, SEND_PLATE, SEND_SLAP
    p, cfg = preset_config(name)
    _PRESET = dict(cfg)
    _PRESET["_deltas"] = ROLE_DELTAS.get(p, {})
    SEND_PLATE = 10.0 ** (float(cfg.get("plate_db", -14.0)) / 20.0)
    SEND_SLAP = 10.0 ** (float(cfg.get("slap_db", -14.0)) / 20.0)
    return _PRESET


def _treat_for(role):
    t = dict(ROLE_TREAT.get(role, ROLE_TREAT["other"]))
    d = _PRESET.get("_deltas", {}).get(role)
    if d:
        for _k, _v in d.items():
            t[_k] = t.get(_k, 0.0) + float(_v)
    return t

ROLE_VOCALS = ("lead", "adlib", "backing")
CLARITY_MIN = 1.8
RAISE_PER_PASS = 0.5
RAISE_CAP = 0.0
SEND_WET = 0.11
DOUBLE_DB = -15.0
WIDEN = 1.15
LOW_MONO_HZ = 120.0
CEILING_DB = -1.0
TARGETS = {"clarity": 2.0, "harsh": 2.0, "sib": 3.0, "corr": 0.20, "tp": -1.0}

BEAT_ROLES = ("beat", "instrumental", "inst", "instrument", "music",
              "2track", "two track", "backing track")
VOCAL_ROLES = ("vocal", "vox", "lead", "adlib", "backing", "harmony",
               "acapella", "acappella", "dry", "main")

_PLATE = {"ir": {}, "err": "", "kind": ""}


def role_of(role):
    r = str(role or "").lower().strip()
    for t in BEAT_ROLES:
        if t in r:
            return "beat"
    if any(t in r for t in ("adlib", "ad lib", "ad-lib", "harmon", "stack")):
        return "adlib"
    if any(t in r for t in ("back", "backup", "bvox", "b-vox", "bv", "bgv", "bg", "harm", "dub", "dbl", "double", "group", "chorus", "stack", "vocal 2", "vocal 3", "vox 2", "vox 3", "vocal-2", "vocal-3")):
        return "backing"
    if any(t in r for t in ("lead", "main", "vocal", "vox", "acap", "dry")):
        return "lead"
    return "other"


def bucket(role):
    r = role_of(role)
    return r if r in ("beat", "lead", "adlib", "backing") else "other"


def kind_of(role):
    r = role_of(role)
    return "vocal" if r in ("lead", "adlib", "backing") else r


def _opt(chain, cls, **kw):
    if cls is None:
        return chain
    try:
        chain.append(cls(**kw))
    except Exception:
        pass
    return chain


def _win():
    return np.hanning(N + 1).astype(np.float32)[:-1]


def _mono(x):
    return np.mean(x, axis=0).astype(np.float32)


def _pad(x, n):
    if x.shape[1] >= n:
        return x
    o = np.zeros((2, n), dtype=np.float32)
    o[:, :x.shape[1]] = x
    return o


def _sum(arrays):
    if not arrays:
        return np.zeros((2, 0), dtype=np.float32)
    n = max(a.shape[1] for a in arrays)
    out = np.zeros((2, n), dtype=np.float32)
    for a in arrays:
        out[:, :a.shape[1]] += a
    return out


def plain_sum(groups):
    out = np.zeros((2, 0), dtype=np.float32)
    for kind in ("beat", "lead", "adlib", "backing", "other"):
        for a in groups.get(kind) or []:
            if out.shape[1] < a.shape[1]:
                g = np.zeros((2, a.shape[1]), dtype=np.float32)
                g[:, :out.shape[1]] = out
                out = g
            out[:, :a.shape[1]] += a
    return _headroom(out)


def _rms_db(x):
    return float(20.0 * np.log10(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12))


def _peak_db(x):
    pk = float(np.max(np.abs(x))) if x.size else 0.0
    return 20.0 * np.log10(pk + 1e-12)


def _true_peak_db(x, oversample=4, chunk=1 << 16, guard=4096):
    """True peak in dBTP via FFT oversampling (zero-stuff + brick-wall LPF)."""
    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 1:
        a = a[None, :]
    if a.size == 0:
        return -120.0
    u = max(1, int(oversample))
    total = a.shape[1]
    peak = 0.0
    for ch in range(a.shape[0]):
        for p0 in range(0, total, chunk):
            q = min(p0 + chunk, total)
            lo = max(0, p0 - guard)
            hi = min(total, q + guard)
            seg = a[ch, lo:hi]
            m = int(seg.size)
            N = m * u
            X = np.fft.rfft(seg)
            Y = np.zeros(N // 2 + 1, dtype=np.complex128)
            Y[:X.size] = X * u
            y = np.fft.irfft(Y, N)
            s = (p0 - lo) * u
            e = s + (q - p0) * u
            mx = float(np.max(np.abs(y[s:e])))
            if mx > peak:
                peak = mx
    return 20.0 * np.log10(peak + 1e-12)


def _headroom(x, target_db=-3.0):
    pk = float(np.max(np.abs(x))) if x.size else 0.0
    lim = 10.0 ** (target_db / 20.0)
    if pk > lim:
        x *= (lim / pk)
    return x


def _level_db(S, k):
    return 10.0 * np.log10(np.mean(np.abs(S[:, k]) ** 2, axis=1) + 1e-12)


def _avg(S, band, freq):
    k = (freq >= band[0]) & (freq < band[1])
    return float(np.median(_level_db(S, k)))


def _smooth(x, atk=1.0, rel=8.0):
    a, r = np.exp(-1.0 / max(atk, 1e-6)), np.exp(-1.0 / max(rel, 1e-6))
    out = np.empty_like(x)
    p = 0.0
    for i in range(len(x)):
        c = a if x[i] > p else r
        p = c * p + (1.0 - c) * x[i]
        out[i] = p
    return out


def _activity(lev):
    lo, hi = np.percentile(lev, 25), np.percentile(lev, 90)
    return np.clip((lev - lo) / (hi - lo + 1e-9), 0.0, 1.0)


# ---------- STFT ----------

def _stft(x, chunk=512):
    w = _win()
    x = np.asarray(x, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=0)
    if x.shape[0] < N:
        x = np.pad(x, (0, N - x.shape[0]))
    n = 1 + (x.shape[0] - N) // HOP
    idx = np.arange(N)
    out = np.empty((n, N // 2 + 1), dtype=np.complex64)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        fr = x[(HOP * np.arange(s, e))[:, None] + idx[None, :]] * w
        out[s:e] = np.fft.rfft(fr, axis=1)
        del fr
    return out


def _istft(S, length, chunk=512):
    w = _win()
    out = np.zeros(length + N, dtype=np.float32)
    acc = np.zeros(length + N, dtype=np.float32)
    ww = (w * w).astype(np.float32)
    n = S.shape[0]
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        t = np.fft.irfft(S[s:e], n=N, axis=1).astype(np.float32) * w
        for j in range(t.shape[0]):
            o = (s + j) * HOP
            out[o:o + N] += t[j]
            acc[o:o + N] += ww
        del t
    acc[acc < 1e-8] = 1.0
    return (out / acc)[:length]


# ---------- analysis ----------

def _measures(B, V, freq):
    v = {b: _avg(V, b, freq) for b in BANDS}
    q = {b: _avg(B, b, freq) for b in BANDS}
    return {
        "body": v[BODY],
        "presence": v[PRES] - v[BODY],
        "harsh": v[HARSH] - v[BODY],
        "mud": v[MUD] - v[BODY],
        "box": v[BOX] - v[BODY],
        "sib": v[SIB] - v[BODY],
        "air": v[AIR] - v[HARSH],
        "clarity": v[PRES] - q[PRES],
        "mask_body": v[BODY] - q[BODY],
        "mask_harsh": v[HARSH] - q[HARSH],
    }


def _k_weighting(sr):
    """BS.1770-4 K-weighting biquads, valid at any sample rate. No scipy."""
    import math
    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    K = math.tan(math.pi * fc / sr)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    sh = ([ (Vh + Vb*K/Q + K*K)/a0, 2.0*(K*K - Vh)/a0, (Vh - Vb*K/Q + K*K)/a0 ],
          [ 1.0, 2.0*(K*K - 1.0)/a0, (1.0 - K/Q + K*K)/a0 ])
    fc, Q = 38.13547087602444, 0.5003270373238773
    K = math.tan(math.pi * fc / sr)
    a0 = 1.0 + K / Q + K * K
    hp = ([1.0, -2.0, 1.0],
          [1.0, 2.0*(K*K - 1.0)/a0, (1.0 - K/Q + K*K)/a0])
    return sh, hp


def _biq(x, b, a):
    y = np.empty_like(x, dtype=np.float64)
    z1 = z2 = 0.0
    b0, b1, b2 = float(b[0]), float(b[1]), float(b[2])
    a1, a2 = float(a[1]), float(a[2])
    for i in range(x.size):
        v = x[i]
        o = b0 * v + z1
        z1 = b1 * v - a1 * o + z2
        z2 = b2 * v - a2 * o
        y[i] = o
    return y
_FAST_LOUDNESS_BLOCK = 1 << 15
_FAST_LOUDNESS_IR_LEN = 16384
_FAST_LOUDNESS_CACHE = {}


def _fast_loudness_ir(b, a, n=_FAST_LOUDNESS_IR_LEN):
    """Impulse response of one biquad, matching _biq's TDF-II form."""
    b0, b1, b2 = map(float, b)
    a1, a2 = float(a[1]), float(a[2])
    h = np.empty(n, dtype=np.float64)
    z1 = z2 = 0.0
    for i in range(n):
        v = 1.0 if i == 0 else 0.0
        y = b0 * v + z1
        z1 = b1 * v - a1 * y + z2
        z2 = b2 * v - a2 * y
        h[i] = y
    return h


def _fast_loudness_kernel(sr):
    """Cached FFT kernel built from the runtime K-weighting coefficients."""
    key = float(sr)
    cached = _FAST_LOUDNESS_CACHE.get(key)
    if cached is not None:
        return cached
    sh, hp = _k_weighting(key)
    h = np.convolve(_fast_loudness_ir(sh[0], sh[1]),
                    _fast_loudness_ir(hp[0], hp[1]))
    m = h.size
    nfft = 1 << (_FAST_LOUDNESS_BLOCK + m - 2).bit_length()
    H = np.fft.rfft(h, nfft)
    H.setflags(write=False)
    cached = (H, nfft, m)
    _FAST_LOUDNESS_CACHE[key] = cached
    return cached


def _fast_loudness_chunks(x, H, nfft, m):
    """Overlap-add filtered samples in bounded chunks."""
    x = np.asarray(x)
    n = x.size
    block = _FAST_LOUDNESS_BLOCK
    tail = np.zeros(m - 1, dtype=np.float64)
    for p in range(0, n, block):
        q = min(p + block, n)
        length = q - p
        chunk = np.asarray(x[p:q], dtype=np.float64)
        y = np.fft.irfft(np.fft.rfft(chunk, nfft) * H, nfft)
        conv = y[:length + m - 1]
        out = conv[:length].copy()
        k = min(length, m - 1)
        out[:k] += tail[:k]
        new_tail = conv[length:length + m - 1].copy()
        if length < m - 1:
            new_tail[:m - 1 - length] += tail[length:]
        tail = new_tail
        yield out


def _fast_loudness_energy(x, sr, block_seconds, hop_seconds):
    """Summed per-channel mean-square energy per window."""
    a = np.asarray(x)
    if a.ndim == 1:
        a = a[None, :]
    if a.shape[0] > a.shape[1]:
        a = a.T
    n = a.shape[1]
    block = int(round(block_seconds * sr))
    hop = int(round(hop_seconds * sr))
    if n < block:
        return None
    H, nfft, m = _fast_loudness_kernel(sr)
    count = (n - block) // hop + 1
    energies = np.zeros(count, dtype=np.float64)
    for ch in range(a.shape[0]):
        pending = np.empty(0, dtype=np.float64)
        index = 0
        for filtered in _fast_loudness_chunks(a[ch], H, nfft, m):
            pending = np.concatenate((pending, filtered)) if pending.size else filtered
            while pending.size >= block:
                window = pending[:block]
                energies[index] += np.dot(window, window) / float(block)
                index += 1
                pending = pending[hop:]
    return energies




def integrated_lufs(x, sr):
    """Gated integrated loudness in LUFS. x = (ch, n) or mono."""
    e = _fast_loudness_energy(x, sr, 0.400, 0.100)
    if e is None:
        return None
    e = e[e > 10.0 ** (-70.0 / 10.0)]
    if e.size == 0:
        return None
    rel = 10.0 ** ((10.0 * np.log10(float(e.mean())) - 10.0) / 10.0)
    e = e[e >= rel]
    if e.size == 0:
        return None
    return float(-0.691 + 10.0 * np.log10(float(e.mean())))




def lra_lu(x, sr):
    """Loudness range: 3 s windows, 1 s hop, 10th-95th percentile."""
    e = _fast_loudness_energy(x, sr, 3.0, 1.0)
    if e is None:
        return None
    e = e[e > 10.0 ** (-70.0 / 10.0)]
    if e.size < 2:
        return None
    rel = 10.0 ** ((10.0 * np.log10(float(e.mean())) - 20.0) / 10.0)
    e = e[e >= rel]
    if e.size < 2:
        return None
    lv = -0.691 + 10.0 * np.log10(e)
    return float(np.percentile(lv, 95) - np.percentile(lv, 10))


def analyze(beat_mono, voc_mono, sr):
    freq = np.fft.rfftfreq(N, 1.0 / sr)
    B = _stft(beat_mono)
    V = _stft(voc_mono)
    v = {b: _avg(V, b, freq) for b in BANDS}
    q = {b: _avg(B, b, freq) for b in BANDS}
    del B, V
    return {
        "body": v[BODY],
        "presence": v[PRES] - v[BODY],
        "harsh": v[HARSH] - v[BODY],
        "mud": v[MUD] - v[BODY],
        "box": v[BOX] - v[BODY],
        "sib": v[SIB] - v[BODY],
        "air": v[AIR] - v[HARSH],
        "clarity": v[PRES] - q[PRES],
        "mask_body": v[BODY] - q[BODY],
        "mask_harsh": v[HARSH] - q[HARSH],
    }, freq


def detect_tempo(beat_mono, sr):
    try:
        S = _stft(beat_mono)
        flux = np.maximum(0.0, np.diff(np.abs(S), axis=0)).mean(axis=1)
        del S
        flux = flux - flux.mean()
        n = len(flux)
        if n < 128:
            return 100.0
        F = np.fft.rfft(flux, 2 * n)
        ac = np.fft.irfft(F * np.conj(F))[:n]
        fps = sr / float(HOP)
        lo = int(round(fps * 60.0 / 190.0))
        hi = min(n - 1, int(round(fps * 60.0 / 60.0)))
        if hi <= lo:
            return 100.0
        lag = lo + int(np.argmax(ac[lo:hi]))
        if lag <= 0:
            return 100.0
        bpm = 60.0 * fps / lag
        while bpm < 80.0:
            bpm *= 2.0
        while bpm > 180.0:
            bpm /= 2.0
        return float(bpm)
    except Exception:
        return 100.0


# ---------- impulse response ----------

def plate_ir(sr):
    key = int(sr)
    if key in _PLATE["ir"]:
        return _PLATE["ir"][key]
    dur, pre = 0.95, 0.020
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    env = np.exp(-6.91 * np.maximum(t - pre, 0.0) / dur)
    ir = np.random.default_rng(7).normal(0.0, 1.0, n) * env
    ir[:int(sr * pre)] *= np.linspace(0.0, 1.0, int(sr * pre)) ** 2
    x = ir.astype(np.float32)[None, :]
    x = Pedalboard([HighpassFilter(cutoff_frequency_hz=300.0),
                    LowpassFilter(cutoff_frequency_hz=9000.0)])(x, sr)
    ir = x[0].astype(np.float32)
    e = float(np.sqrt(np.sum(np.square(ir.astype(np.float64))))) + 1e-12
    ir = (ir / e) * 0.9
    _PLATE["ir"][key] = ir.astype(np.float32)
    return _PLATE["ir"][key]


def plate_error():
    return _PLATE.get("err") or None


def _plate(voc, sr):
    ir = plate_ir(sr)
    if Convolution is not None:
        import tempfile as _tf
        path = None
        try:
            from pedalboard.io import AudioFile as _AF
            fd, path = _tf.mkstemp(suffix=".wav")
            os.close(fd)
            _r = np.concatenate([np.zeros(int(sr * 0.011), np.float32), ir])[:ir.shape[0]]
            stereo = np.stack([ir, (_r * 0.97).astype(np.float32)]).astype(np.float32)
            with _AF(path, "w", int(sr), 2) as f:
                try:
                    f.bit_depth = 32
                except Exception:
                    pass
                f.write(stereo)
            for mk in (lambda: Convolution(path, mix=1.0),
                       lambda: Convolution(path)):
                try:
                    y = Pedalboard([mk()])(voc, sr).astype(np.float32)
                    # Convolution returns far quieter than the dry signal
                    # (long IR, energy-normalised). Self-calibrate the wet
                    # level here; the send gain rides on top of this.
                    _a = float(np.sqrt(np.mean(np.asarray(voc, dtype=np.float64) ** 2))) + 1e-9
                    _b = float(np.sqrt(np.mean(y.astype(np.float64) ** 2))) + 1e-9
                    y = (y * (_a / _b)).astype(np.float32)
                    _PLATE["kind"] = "plate"
                    _PLATE["err"] = ""
                    return y
                except Exception as e:
                    _PLATE["err"] = "Convolution: " + str(e)[:160]
        except Exception as e:
            _PLATE["err"] = "ir write: " + str(e)[:160]
        finally:
            if path:
                try:
                    os.remove(path)
                except Exception:
                    pass
    else:
        _PLATE["err"] = "Convolution class unavailable"
    try:
        y = Pedalboard([Reverb(room_size=0.45, damping=0.55,
                               wet_level=1.0, dry_level=0.0, width=1.0)])(voc, sr).astype(np.float32)
        _PLATE["kind"] = "algorithmic"
        return y
    except Exception:
        return None


def _send_sum(voc, sr, plugins):
    plugins = [p for p in plugins if p is not None]
    if not plugins:
        return None
    if Mix is not None and len(plugins) > 1:
        try:
            return Pedalboard([Mix(plugins)])(voc, sr).astype(np.float32)
        except Exception:
            pass
    out = None
    for p in plugins:
        try:
            y = Pedalboard([p])(voc, sr).astype(np.float32)
        except Exception:
            continue
        out = y if out is None else out + y
    return out


# ---------- vocal processing ----------

def _saturate(x, sr, drive_db):
    try:
        y = Pedalboard([Distortion(drive_db=float(drive_db))])(x, sr).astype(np.float32)
    except Exception:
        return x
    return (y * (10.0 ** ((_rms_db(x) - _rms_db(y)) / 20.0))).astype(np.float32)


def _deess(voc, sr, st):
    """Sibilance control calibrated off the band's own level so it fires when
    sibilance is actually present. Runs BEFORE the air shelf in _role_chain."""
    freq = np.fft.rfftfreq(N, 1.0 / sr)
    k = (freq >= 5500) & (freq < 9000)
    if not np.any(k):
        return voc, 0.0
    out = np.empty_like(voc)
    mx = 0.0
    for c in range(voc.shape[0]):
        S = _stft(voc[c])
        lev = _level_db(S, k)
        thr = float(np.median(lev)) + DEESS_OFFSET_DB
        red = _smooth(np.clip(lev - thr, 0.0, MAX_DEESS), atk=DEESS_ATK, rel=DEESS_REL)
        mx = max(mx, float(np.max(red)))
        S[:, k] *= (10.0 ** (-red / 20.0))[:, None]
        out[c] = _istft(S, voc.shape[1])
        del S
    return out, round(mx, 2)


SEND_PLATE = 10.0 ** (-14.0 / 20.0)   # plate send
SEND_SLAP  = 10.0 ** (-14.0 / 20.0)   # slap send


def _ambience(voc, sr, bpm):
    beat_s = 60.0 / max(bpm, 40.0)
    d = max(int(sr * 0.04), min(int(sr * beat_s * 0.5), int(sr * 0.35)))
    wet = None
    slap = None
    try:
        slap = Pedalboard([
            Delay(delay_seconds=d / float(sr), feedback=0.18, mix=1.0),
            HighpassFilter(cutoff_frequency_hz=300.0),
            LowpassFilter(cutoff_frequency_hz=4000.0),
        ])(voc, sr).astype(np.float32)
        wet = slap
    except Exception:
        wet = None
    plate = _plate(voc, sr)
    if plate is not None:
        wet = plate if wet is None else (wet + plate).astype(np.float32)
    kind = _PLATE.get("kind") or "none"
    if wet is None:
        return voc, round(d / float(sr) * 1000.0), "none"
    w = None
    if slap is not None:
        w = SEND_SLAP * slap
    if plate is not None:
        w = SEND_PLATE * plate if w is None else (w + SEND_PLATE * plate)
    if w is None:
        return voc, round(d / float(sr) * 1000.0), "none"
    out = (voc + w).astype(np.float32)
    return _headroom(out, -1.0), round(d / float(sr) * 1000.0), kind


def _double(voc, sr):
    if PitchShift is None:
        return None
    try:
        out = np.zeros_like(voc)
        for cents, ms, pan in ((7.0, 14.0, 0.30), (-6.0, 22.0, -0.30)):
            ch = [PitchShift(semitones=cents / 100.0),
                  HighpassFilter(cutoff_frequency_hz=150.0),
                  LowpassFilter(cutoff_frequency_hz=10000.0)]
            _opt(ch, Chorus, rate_hz=0.4, depth=0.06, mix=0.25)
            ch.append(Delay(delay_seconds=ms / 1000.0, feedback=0.0, mix=1.0))
            y = Pedalboard(ch)(voc, sr).astype(np.float32)
            y[0] *= float(np.sqrt(max(0.0, (1.0 - pan) * 0.5)) * 1.414)
            y[1] *= float(np.sqrt(max(0.0, (1.0 + pan) * 0.5)) * 1.414)
            out += y
        out *= 10.0 ** (DOUBLE_DB / 20.0)
        return out
    except Exception:
        return None


def _role_chain(voc, sr, st, role):
    t = _treat_for(role)
    moves = [["role", role], ["highpass", t["hpf"]]]
    ch = [HighpassFilter(cutoff_frequency_hz=t["hpf"])]
    if st["mud"] > 1.0:
        g = -min(t["mud"], (st["mud"] - 1.0) * 1.1 * 2.0)
        if g < -0.2:
            ch.append(PeakFilter(240.0, g, 0.9)); moves.append(["mud 240", round(g, 2)])
    if st["box"] > 1.0:
        g = -min(t["box"], (st["box"] - 1.0) * 0.8 * 1.5)
        if g < -0.2:
            ch.append(PeakFilter(600.0, g, 1.0)); moves.append(["box 600", round(g, 2)])
    if st["harsh"] > 1.5:
        g = -min(t["harsh"], (st["harsh"] - 1.5) * 2.0)
        if g < -0.2:
            ch.append(PeakFilter(4400.0, g, 1.2)); moves.append(["harsh 4.4k", round(g, 2)])
    if st["presence"] < -2.5 and t["pres"] > 0:
        g = min(MAX_PRESENCE * t["pres"], (-st["presence"] - 2.5) * 0.5 + 0.4)
        if g > 0.2:
            ch.append(PeakFilter(3000.0, g, 0.8)); moves.append(["presence 3k", round(g, 2)])
    _thr = float(np.clip(_rms_db(voc) - 4.0, -45.0, -8.0))
    ch.append(Compressor(threshold_db=_thr, ratio=t["ratio"],
                         attack_ms=t["atk"], release_ms=t["rel"]))
    moves.append(["compress", "%s:1 @ %.1f" % (t["ratio"], _thr)])
    drive = min(1.2, t["sat"])
    out = Pedalboard(ch)(voc, sr).astype(np.float32)
    _pre = _rms_db(voc)
    _post = _rms_db(out)
    makeup = float(np.clip(_pre - _post, 0.0, 4.0))
    if makeup > 0.05:
        out = (out * (10.0 ** (makeup / 20.0))).astype(np.float32)
    moves.append(["makeup", round(makeup, 2)])
    out = _saturate(out, sr, drive)
    moves.append(["saturate", round(drive, 2)])
    out, dd = _deess(out, sr, st)
    moves.append(["de-ess", dd])
    try:
        out = Pedalboard([HighShelfFilter(cutoff_frequency_hz=10000.0,
                                          gain_db=min(MAX_AIR, t["air"]), q=0.7)])(out, sr).astype(np.float32)
    except Exception:
        pass
    moves.append(["air 10k", round(min(MAX_AIR, t["air"]), 2)])
    out = (out * (10.0 ** (t["gain"] / 20.0))).astype(np.float32)
    moves.append(["role gain", t["gain"]])
    return out, moves


def vocal_process(voc, sr, st, bpm):
    out, moves = _role_chain(voc, sr, st, "lead")
    return out, moves


def _plan(st):
    now = {BODY: st["mask_body"], PRES: st["clarity"], HARSH: st["mask_harsh"]}
    return {b: -min(DUCK_CAP[b], max(0.0, (DUCK_TARGET[b] - now[b]) * 0.9))
            for b in (BODY, PRES, HARSH)}


def _duck(beat, voc_eq, freq, st, extra=0.0):
    plan = _plan(st)
    plan = {b: max(-DUCK_CAP[b], v - extra) for b, v in plan.items()}
    Vq = _stft(_mono(voc_eq))
    vpres = _avg(Vq, PRES, freq)
    gains = {}
    for b, db in plan.items():
        if db >= -0.05:
            continue
        k = (freq >= b[0]) & (freq < b[1])
        act = _smooth(_activity(_level_db(Vq, k)))
        gains[b] = (k, (10.0 ** ((db * act) / 20.0)).astype(np.float32))
    del Vq
    if not gains:
        return beat.copy(), plan, vpres, None
    out = np.empty_like(beat)
    for c in range(beat.shape[0]):
        S = _stft(beat[c])
        for b, (k, gain) in gains.items():
            S[:, k] *= gain[:, None]
        out[c] = _istft(S, beat.shape[1])
        del S
    return out, plan, vpres, _avg(_stft(_mono(out)), PRES, freq)


# ---------- width, verify, limit ----------

def _widen(x, sr, amount=None):
    amt = WIDEN if amount is None else amount
    mid = ((x[0] + x[1]) * 0.5).astype(np.float32)
    side = ((x[0] - x[1]) * 0.5).astype(np.float32)
    low = Pedalboard([LowpassFilter(cutoff_frequency_hz=LOW_MONO_HZ)])(side[None, :], sr)[0]
    side = ((side - low) * amt + low).astype(np.float32)
    return np.stack([mid + side, mid - side]).astype(np.float32)


def verify(mixed, sr, voc_eq, ducked):
    freq = np.fft.rfftfreq(N, 1.0 / sr)
    V = _stft(_mono(voc_eq))
    D = _stft(_mono(ducked))
    clarity = _avg(V, PRES, freq) - _avg(D, PRES, freq)
    harsh = _avg(V, HARSH, freq) - _avg(V, BODY, freq)
    sib = _avg(V, SIB, freq) - _avg(V, BODY, freq)
    del V, D
    a = mixed[0].astype(np.float64)
    b = mixed[1].astype(np.float64)
    corr = float(np.dot(a, b) / (np.sqrt(np.dot(a, a) * np.dot(b, b)) + 1e-12))
    res = {
        "clarity": round(float(clarity), 2),
        "harsh": round(float(harsh), 2),
        "sib": round(float(sib), 2),
        "corr": round(corr, 3),
        "peak": round(_peak_db(mixed), 2),
        "rms": round(_rms_db(mixed), 2),
    }
    res["pass"] = (clarity >= TARGETS["clarity"] and harsh < TARGETS["harsh"]
                   and sib < TARGETS["sib"] and corr > TARGETS["corr"])
    return res


def clip(x, sr):
    try:
        return Pedalboard([Clipping(threshold_db=-1.0)])(x, sr).astype(np.float32)
    except Exception:
        return x


def _brick(ceiling_db):
    if BrickwallLimiter is None:
        return None
    attempts = (
        lambda: BrickwallLimiter(threshold_db=ceiling_db, release_ms=100.0, lookahead_ms=3.0),
        lambda: BrickwallLimiter(threshold_db=ceiling_db, release_ms=100.0),
        lambda: BrickwallLimiter(threshold_db=ceiling_db),
        lambda: BrickwallLimiter(ceiling_db=ceiling_db),
        lambda: BrickwallLimiter(),
    )
    for f in attempts:
        try:
            return f()
        except Exception:
            continue
    return None


def limit(x, sr, ceiling_db=CEILING_DB):
    y = None
    b = _brick(ceiling_db)
    if b is not None:
        try:
            y = Pedalboard([b])(x, sr).astype(np.float32)
        except Exception:
            y = None
    if y is None:
        try:
            y = Pedalboard([Limiter(threshold_db=ceiling_db, release_ms=100.0)])(x, sr).astype(np.float32)
        except Exception:
            y = x.copy()
    tp = _true_peak_db(y)
    lim = 10.0 ** (ceiling_db / 20.0)
    if tp > ceiling_db:
        y = y * (lim / (10.0 ** (tp / 20.0)))
        tp = float(ceiling_db)
    return y, float(tp), (b is not None)


# ---------- main ----------

def mix(groups, sr, loud="MEDIUM"):
    beats = list(groups.get("beat") or [])
    others = list(groups.get("other") or [])
    rep = {"sr": int(sr)}
    try:
        rep["arrived"] = {}
        for _k in ("beat", "lead", "adlib", "backing", "other"):
            _g = groups.get(_k) or []
            if _g:
                _s = _sum(_g)
                rep["arrived"][_k] = {"n": len(_g),
                                      "sec": round(_s.shape[1] / float(sr), 2),
                                      "rms_db": round(_rms_db(_s), 1)}
    except Exception as _e:
        rep["arrived"] = {"error": str(_e)[:120]}

    beat = _sum(beats) if beats else None
    ro_map = {}
    for r in ROLE_VOCALS:
        arrs = groups.get(r) or []
        if arrs:
            ro_map[r] = _sum(arrs)
            if len(arrs) > 1:
                try:
                    _ref = arrs[0]
                    _d = []
                    for _i, _a in enumerate(arrs):
                        _mm = min(_a.shape[1], _ref.shape[1])
                        _x = _a[:, :_mm].mean(0); _y = _ref[:, :_mm].mean(0)
                        _c = float(np.corrcoef(_x, _y)[0, 1]) if _i else 1.0
                        _d.append({"i": _i, "rms_db": round(_rms_db(_a), 1),
                                   "corr_vs_1": round(_c, 3) if np.isfinite(_c) else None})
                    _d.append({"sum_rms_db": round(_rms_db(ro_map[r]), 1)})
                    rep.setdefault("bus_diag", {})[r] = _d
                except Exception as _e:
                    rep.setdefault("bus_diag", {})[r] = str(_e)[:120]
    _oth = groups.get("other") or []
    if (beat is None and _oth
            and not any(groups.get(r) for r in ROLE_VOCALS)):
        rep["mode"] = "master"
        rep["note"] = "single full-mix stem - master bus, no vocal chain"
        return _master(_sum(_oth), sr, rep, loud)
    if _oth:
        _o = _sum(_oth)
        if _o is not None:
            beat = _o if beat is None else _sum([beat, _o])
            rep["other_folded_into_beat"] = len(_oth)
    voc = _sum(list(ro_map.values())) if ro_map else None

    if beat is None and voc is None:
        rep["mode"] = "sum"
        return _headroom(_sum(others)), rep

    if voc is None:
        rep["mode"] = "passthrough"
        rep["note"] = "no vocal stem - beat returned without reprocessing"
        return _headroom(beat * (10.0 ** (-1.5 / 20.0))), rep

    if beat is None:
        rep["mode"] = "vocal_only"
        st, _f = analyze(voc, voc, sr)
        parts, moves = [], {}
        for r in list(ro_map.keys()):
            y, mv = _role_chain(ro_map[r], sr, st, r)
            parts.append(y); moves[r] = mv
        core = _sum(parts)
        if others:
            ex = _sum(others)
            n = max(core.shape[1], ex.shape[1])
            core = (_pad(core, n) + _pad(ex, n) * (10.0 ** (-4.0 / 20.0))).astype(np.float32)
        core, ms, pk = _ambience(_exciter(_parallel(_glue(core, sr), sr), sr), sr, detect_tempo(core, sr))
        rep["vocal_chain"] = moves
        rep["slap_ms"] = ms
        rep["plate"] = pk
        rep["plate_error"] = plate_error()
        return _headroom(core), rep

    _match_role_levels(ro_map, sr, rep)
    rep["mode"] = "two_track" if len(beats) == 1 else "stems"
    rep["roles"] = {r: len(groups.get(r) or []) for r in ROLE_VOCALS if groups.get(r)}
    bpm = detect_tempo(_mono(beat), sr)
    rep["bpm"] = round(bpm, 1)

    freq = np.fft.rfftfreq(N, 1.0 / sr)
    Bst = _stft(_mono(beat))
    st = _measures(Bst, _stft(_mono(voc)), freq)
    rep["measured"] = {k: round(float(v), 2) for k, v in st.items()}

    parts, moves = [], {}
    for r in list(ro_map.keys()):
        y, mv = _role_chain(ro_map[r], sr, st, r)
        if ROLE_TREAT[r]["width"] != 1.0:
            y = _widen(y, sr, ROLE_TREAT[r]["width"])
        parts.append(y); moves[r] = mv
    core = _sum(parts)
    if polish is not None:
        try:
            _sh = core.shape
            _y, _pst = polish.dynamic_eq(core, sr, get_stats=True)
            if _y.shape != _sh or not np.isfinite(_y).all(): raise ValueError("bad audio")
            core = _y
            rep["dynamic_eq"] = [{"band": "%g-%g" % (float(b[0]), float(b[1])),
                "avg_db": round(float(b[4]), 2), "max_db": round(float(b[5]), 2),
                "active_pct": round(float(b[6]), 1)} for b in _pst]
        except Exception as _e:
            rep["dynamic_eq_error"] = str(_e)[:200]
    rep["vocal_chain"] = moves

    raised = 0.0
    level_passes = 0
    while (level_passes < 3 and st["clarity"] < (CLARITY_MIN - 0.3)
           and raised < RAISE_CAP):
        add = min(RAISE_PER_PASS, (CLARITY_MIN - st["clarity"]) * 0.7, RAISE_CAP - raised)
        if add <= 0.05:
            break
        raised += add
        core = (core * (10.0 ** (add / 20.0))).astype(np.float32)
        st = _measures(Bst, _stft(_mono(core)), freq)
        level_passes += 1
    del Bst
    rep["vocal_raise_db"] = round(raised, 2)
    rep["level_passes"] = level_passes

    core, ms, pk = _ambience(_exciter(_parallel(_glue(core, sr), sr), sr), sr, bpm)
    rep["slap_ms"] = ms
    rep["plate"] = pk
    rep["plate_error"] = plate_error()

    side_ids = [r for r in ("adlib",) if r in ro_map]
    if side_ids:
        dbl = _double(_sum([ro_map[r] for r in side_ids]), sr)
        if dbl is not None:
            n = max(core.shape[1], dbl.shape[1])
            core = (_pad(core, n) + _pad(dbl, n)).astype(np.float32)
            rep["double"] = True
        else:
            rep["double"] = False
    else:
        rep["double"] = False

    ducked, plan, vpres, post = _duck(beat, core, freq, st)
    tries = 1
    while (post is not None and (vpres - post) < (DUCK_TARGET[PRES] - 0.5)
           and tries < 2 and any(plan[b] > -DUCK_CAP[b] + 0.05 for b in plan)):
        ducked, plan, vpres, post = _duck(beat, core, freq, st, extra=1.0)
        tries += 1

    rep["duck_db"] = {("%d-%d" % b): round(v, 2) for b, v in plan.items()}
    rep["clarity_before"] = round(float(st["clarity"]), 2)
    rep["clarity_after"] = None if post is None else round(float(vpres - post), 2)
    rep["duck_passes"] = tries

    n = max(ducked.shape[1], core.shape[1])
    ducked = _pad(ducked, n)
    core = _pad(core, n)
    mixed = (ducked + core).astype(np.float32)
    if others:
        ex = _sum(others)
        n2 = max(mixed.shape[1], ex.shape[1])
        mixed = (_pad(mixed, n2) + _pad(ex, n2) * (10.0 ** (-4.0 / 20.0))).astype(np.float32)

    mixed = _widen(mixed, sr, float(_PRESET.get("width") or 1.0))
    mixed = _headroom(mixed)
    rep["check"] = verify(mixed, sr, core, ducked)
    return mixed, rep


def _glue(x, sr, thr=-10.0, ratio=1.5, atk=30.0, rel=250.0):
    """Vocal-bus glue: slow, gentle, 1-2 dB of gain reduction.
    Softens peaks and seats lead + backups together - the 'polished record' step."""
    for kw in ({"threshold_db": thr, "ratio": ratio, "attack_ms": atk, "release_ms": rel},
               {"threshold_db": thr, "ratio": ratio}):
        try:
            return np.asarray(Pedalboard([Compressor(**kw)])(x, sr), dtype=np.float32)
        except Exception:
            continue
    return x


# ---------- full-mix master bus ----------

WIDEN_MASTER = 1.10


def _master(x, sr, rep, loud="MEDIUM"):
    """Master a finished stereo mix. No vocal EQ, no role chain, no low-cut
    below 20 Hz. Rumble guard -> tone polish -> modest width. mix.py adds the
    glue, the LUFS normalise and the true-peak limiter on top."""
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    moves = []
    try:
        a = Pedalboard([HighpassFilter(cutoff_frequency_hz=20.0)])(a, sr).astype(np.float32)
        moves.append(["hpf", 20.0])
    except Exception:
        pass
    try:
        a2, pst = polish.dynamic_eq(a, sr, get_stats=True)
        a = np.asarray(a2, dtype=np.float32)
        rep["polish"] = pst
        moves.append(["polish_eq", "on"])
    except Exception as e:
        rep["polish_error"] = str(e)[:160]
    try:
        a = _widen(a, sr, WIDEN_MASTER)
        moves.append(["width", WIDEN_MASTER])
    except Exception:
        pass
    rep["master_chain"] = moves
    return _headroom(a, -1.0), rep


# ---------- polish additions ----------

def _parallel(x, sr):
    """Gentle parallel vocal density; keeps the dry vocal intact."""
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        crushed = Pedalboard([
            Compressor(threshold_db=-24.0, ratio=6.0,
                       attack_ms=8.0, release_ms=90.0),
            Gain(gain_db=3.0),
        ])(a, int(sr)).astype(np.float32)
        y = (a * 0.70 + crushed * 0.30).astype(np.float32)
        return _headroom(y, -1.0).astype(np.float32)
    except Exception:
        return x


def _exciter(x, sr):
    """Low-level high-frequency harmonic air without distorting the body."""
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        air = Pedalboard([
            HighpassFilter(cutoff_frequency_hz=9000.0),
            Distortion(drive_db=1.5),
            LowpassFilter(cutoff_frequency_hz=14000.0),
            Gain(gain_db=-9.0),
        ])(a, int(sr)).astype(np.float32)
        y = (a + air * 0.18).astype(np.float32)
        return _headroom(y, -1.0).astype(np.float32)
    except Exception:
        return x


def _match_role_levels(ro_map, sr, rep):
    """Lift quiet vocal roles toward the lead so they survive the mix."""
    try:
        if ro_map.get("lead") is None:
            rep["level_match"] = "no lead - skipped"
            return
        lead = float(_rms_db(ro_map["lead"]))
        target = {"adlib": lead - 8.0, "backing": lead - 6.0}
        rep["level_match"] = {"lead_rms": round(lead, 1)}
        for r, tgt in target.items():
            v = ro_map.get(r)
            if v is None or getattr(v, "shape", (0, 0))[1] == 0:
                continue
            cur = float(_rms_db(v))
            if cur < -60.0:
                rep["level_match"][r] = "SILENT (%.1f dB) - bad file" % cur
                continue
            pk = float(np.max(np.abs(v))) or 1e-9
            head = 20.0 * np.log10(0.9 / pk)
            gain = float(np.clip(min(tgt - cur, head), -6.0, 21.0))
            if abs(gain) >= 0.1:
                ro_map[r] = (v * (10.0 ** (gain / 20.0))).astype(np.float32)
            rep["level_match"][r] = {"from": round(cur, 1), "gain": round(gain, 2)}
    except Exception as e:
        rep["level_match_error"] = str(e)[:300]
