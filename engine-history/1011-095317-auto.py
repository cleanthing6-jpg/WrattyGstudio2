"""Automatic mix engine v3: measures the voice, makes room for it, then applies
a professional release chain. Every stage is capped, guarded and verified, so a
mix cannot come out harsh, phasing or clipping.
"""

import os
import numpy as np
try:
    import declip as _declip
except ImportError:
    try:
        from . import declip as _declip
    except Exception:
        _declip = None

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

MAX_MUD_CUT, MAX_BOX_CUT = 3.0, 3.0
MAX_PRESENCE, MAX_HARSH_CUT, MAX_AIR, MAX_DEESS = 1.5, 3.0, 1.5, 2.5
DEESS_OFFSET_DB = 8.0   # trigger this far above the band's own median
DEESS_ATK, DEESS_REL = 1.0, 4.0
DUCK_CAP = {BODY: 1.0, PRES: 3.5, HARSH: 2.0}
DUCK_TARGET = {BODY: 1.0, PRES: 3.2, HARSH: 1.3}

ROLE_TREAT = {
    "lead":    {"gain": -2.0,  "hpf": 100.0, "mud": 2.0, "box": 2.0, "pres": 3.0,
                "harsh": 1.5, "air": 2.8, "ratio": 2.0, "atk": 20.0, "rel": 100.0,
                "sat": 0.35, "width": 1.0},
    "adlib":   {"gain": -8.0, "hpf": 135.0, "mud": 2.0, "box": 1.5, "pres": 0.6,
                "harsh": 2.5, "air": 2.0, "ratio": 3.0, "atk": 15.0, "rel": 90.0,
                "sat": 0.6, "width": 1.25},
    "backing": {"gain": -3.0, "hpf": 140.0, "mud": 3.0, "box": 2.0, "pres": 0.0,
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
        "target_lufs": -9.5, "glue_ratio": 1.5, "glue_gr_db": 0.5,
        "width": 1.08, "plate_db": -16.5, "slap_db": -15.0,
        "max_air": 2.0, "max_deess": 3.5,
        "deess_offset_db": 2.5, "deess_atk": 0.5, "deess_rel": 2.0,
        "duck_cap": {BODY: 2.5, PRES: 5.5, HARSH: 3.0},
        "duck_target": {BODY: 2.0, PRES: 4.8, HARSH: 2.0},
        "low_mono_hz": 70.0,
        "lead_shift_ms": 45.0,
        "role_treat_lead": {
            "gain": 0.0, "hpf": 110.0, "mud": 2.5, "box": 1.5, "pres": 2.0,
            "harsh": 1.4, "air": 2.0, "ratio": 2.2, "atk": 25.0, "rel": 130.0,
            "sat": 0.55, "width": 1.0,
        },
    },
    "amapiano": {
        "target_lufs": -11.5, "glue_ratio": 1.5, "glue_gr_db": 0.8,
        "width": 1.08, "plate_db": -16.0, "slap_db": -20.0,
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
        "width": 1.06, "plate_db": -18.0, "slap_db": -22.0, "soft_clip": True,
    },
}
ROLE_DELTAS = {
    "afrobeats": {
        "lead": {"air": 0.5, "sat": 0.15},
        "adlib": {"air": 1.2, "sat": 0.2, "pres": -0.5},
        "backing": {"pres": -0.4, "width": 0.15},
    },
    "amapiano": {
        "lead": {"air": 0.6, "sat": 0.1},
        "adlib": {"air": 0.8, "sat": 0.1, "pres": -0.4},
        "backing": {"pres": -0.3, "width": 0.1},
    },
    "pop": {"lead": {"air": 1.0, "sat": 0.2}},
    "rnb": {"lead": {"air": 0.5, "sat": -0.1}},
    "rap": {"lead": {"air": -0.5, "sat": 0.6}, "backing": {"pres": -0.2}},
}
_PRESET = {}


PRESET_ALIASES = {
    "afrobeats": "afrobeats", "afrobeats recommended": "afrobeats", "afrobeat": "afrobeats",
    "highlife": "afrobeats", "high life": "afrobeats",
    "hip hop": "rap", "hip hop rap": "rap", "hiphop": "rap", "rap": "rap",
    "reggae dancehall": "rnb", "reggae": "rnb", "dancehall": "rnb",
    "pop": "pop", "rnb": "rnb", "r b": "rnb",
    "electronic amapiano": "amapiano", "electronic": "amapiano", "amapiano": "amapiano",
    "acoustic": "neutral", "rock indie": "neutral", "rock": "neutral",
    "other": "neutral", "neutral": "neutral",
}


def normalize_preset(name):
    q = str(name or "neutral").strip().lower()
    for ch in ("—", "–", "-", "/", "_", "."):
        q = q.replace(ch, " ")
    q = " ".join(q.split())
    return PRESET_ALIASES.get(q, q)


def preset_config(name):
    requested = str(name or "neutral")
    p = normalize_preset(requested)
    if p not in PRESETS:
        print("[preset] requested=%r -> UNKNOWN, falling back to neutral" % requested)
        p = "neutral"
    print("[preset] requested=%r resolved=%r" % (requested, p))
    return p, dict(PRESETS[p])


def apply_preset(name):
    """Activate a preset. Returns its config dict."""
    global _PRESET, SEND_PLATE, SEND_SLAP
    p, cfg = preset_config(name)
    _PRESET = dict(cfg)
    _PRESET["_deltas"] = ROLE_DELTAS.get(p, {})
    _PRESET["_name"] = p
    # per-preset overrides (afrobeats only — other presets fall back to defaults)
    globals()["MAX_AIR"] = float(cfg.get("max_air", 1.5))
    globals()["MAX_DEESS"] = float(cfg.get("max_deess", 2.5))
    globals()["DEESS_OFFSET_DB"] = float(cfg.get("deess_offset_db", 8.0))
    globals()["DEESS_ATK"] = float(cfg.get("deess_atk", 1.0))
    globals()["DEESS_REL"] = float(cfg.get("deess_rel", 4.0))
    globals()["DUCK_CAP"] = cfg.get("duck_cap") or {BODY: 1.0, PRES: 3.5, HARSH: 2.0}
    globals()["DUCK_TARGET"] = cfg.get("duck_target") or {BODY: 1.0, PRES: 3.2, HARSH: 1.3}
    globals()["LOW_MONO_HZ"] = float(cfg.get("low_mono_hz", 120.0))
    globals()["LEAD_SHIFT_MS"] = float(cfg.get("lead_shift_ms", 0.0))
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

# Lead shift earlier in ms. Tune until vocal lands on beat.

# Lead vocal shift earlier in ms (aligns vocal to beat).
LEAD_SHIFT_MS = 0.0

ROLE_VOCALS = ("lead", "adlib", "backing")
CLARITY_MIN = 2.0
RAISE_PER_PASS = 0.75
RAISE_CAP = 2.5
SEND_WET = 0.11
DOUBLE_DB = -30.0
WIDEN = 1.0
LOW_MONO_HZ = 120.0
CEILING_DB = -1.0   # canonical true-peak ceiling; TARGETS['tp'] must match
TARGETS = {"clarity": 2.0, "harsh": 2.0, "sib": 3.0, "corr": 0.20, "tp": -1.0}

BEAT_ROLES = ("beat", "instrumental", "inst", "instrument", "music",
              "2track", "two track", "backing track")
VOCAL_ROLES = ("vocal", "vox", "lead", "adlib", "backing", "harmony",
               "acapella", "acappella", "dry", "main")

_PLATE = {"ir": {}, "err": "", "kind": ""}
_HALL = {"ir": {}}
_DBL = {"kind": ""}


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
    try:
        y = Pedalboard([Reverb(room_size=0.55, damping=0.55,
                               wet_level=1.0, dry_level=0.0, width=1.0)])(voc, sr).astype(np.float32)
        _a = float(np.sqrt(np.mean(np.asarray(voc, dtype=np.float64) ** 2))) + 1e-9
        _b = float(np.sqrt(np.mean(y.astype(np.float64) ** 2))) + 1e-9
        y = (y * (_a / _b)).astype(np.float32)
        _PLATE["kind"] = "algorithmic"
        _PLATE["err"] = ""
        return y
    except Exception as e:
        _PLATE["err"] = "Reverb: " + str(e)[:160]
        return None
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
        y = Pedalboard([Reverb(room_size=0.70, damping=0.55,
                               wet_level=1.0, dry_level=0.0, width=1.0)])(voc, sr).astype(np.float32)
        _pd = int(sr * 0.095)
        if _pd > 0 and y.shape[1] > _pd:
            _z = np.zeros_like(y)
            _z[:, _pd:] = y[:, :y.shape[1] - _pd]
            y = _z
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


def _headphone_wrap(x, sr):
    """Bauer-style crossfeed + M/S widen for headphone playback.
    300 us interaural delay on a lowpassed (<700 Hz) copy of the opposite
    channel at -6 dB. Removes the in-head 'inside your skull' feel while
    keeping the intimate at-the-ear character. Slight M/S widen on top."""
    try:
        from pedalboard import LowpassFilter as _LPF
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] != 2 or a.shape[1] < 128:
            return x
        d = max(1, int(sr * 0.0003))
        cf = np.zeros_like(a)
        cf[0, d:] = a[1, :-d]
        cf[1, d:] = a[0, :-d]
        cf = Pedalboard([_LPF(cutoff_frequency_hz=350.0)])(cf, sr).astype(np.float32)
        g = 10.0 ** (-9.0 / 20.0)
        out = (a + g * cf).astype(np.float32)
        mid = (out[0] + out[1]) * 0.5
        side = (out[0] - out[1]) * 0.5 * 1.05
        out = np.stack([mid + side, mid - side]).astype(np.float32)
        return _headroom(out, -1.0).astype(np.float32)
    except Exception:
        return x


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


SEND_PLATE = 10.0 ** (-12.0 / 20.0)   # plate send
SEND_SLAP  = 10.0 ** (-14.0 / 20.0)   # slap send


def _delay_tree(voc, sr, bpm):
    """Multi-tap tempo-locked delay bus. Feeds a dark reverb downstream.
    Four note values (1/16, 1/8, dotted 1/8, 1/4) at increasing feedback,
    each highpassed and lowpassed so the taps get darker as they decay."""
    import numpy as np
    from pedalboard import Pedalboard, Delay, HighpassFilter, LowpassFilter
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        bpm = 100.0
    if not (bpm > 0) or bpm != bpm:
        bpm = 100.0
    beat = 60.0 / bpm
    # One DOMINANT tap (dotted 1/8) carries the echo. The other three are
    # pulled way down and only thicken the tail. Full-level parallel taps
    # = stammer, not delay.
    taps = [
        (beat * 0.75, 0.22, 380.0, 6000.0, 1.00),   # dotted 1/8  DOMINANT
        (beat * 0.50, 0.10, 450.0, 5500.0, 0.22),   # 1/8         texture
        (beat * 0.25, 0.05, 600.0, 5000.0, 0.10),   # 1/16        texture
        (beat * 1.00, 0.14, 300.0, 6500.0, 0.18),   # 1/4         texture
    ]
    out = None
    for t, fb, hp, lp, gain in taps:
        try:
            y = Pedalboard([
                Delay(delay_seconds=float(t), feedback=float(fb), mix=1.0),
                HighpassFilter(cutoff_frequency_hz=hp),
                LowpassFilter(cutoff_frequency_hz=lp),
            ])(voc, sr).astype(np.float32)
            y = y * float(gain)
            out = y if out is None else (out + y).astype(np.float32)
        except Exception:
            continue
    return out


def _h3000_widen(x, sr):
    """Eventide H3000-style stereo widener for wet returns.
    Short unequal L/R delays + gentle chorus detune per side.
    Spreads the wet signal wide without smearing the dry vocal."""
    import numpy as np
    from pedalboard import Pedalboard, Chorus
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] != 2:
            return x
        dl = max(1, int(sr * 0.009))
        dr = max(1, int(sr * 0.014))
        L = np.zeros_like(a[0]); R = np.zeros_like(a[1])
        L[dl:] = a[0, :-dl]
        R[dr:] = a[1, :-dr]
        wl = Pedalboard([Chorus(rate_hz=0.30, depth=0.04, mix=0.35)])(L[None, :], sr)[0]
        wr = Pedalboard([Chorus(rate_hz=0.27, depth=0.04, mix=0.35)])(R[None, :], sr)[0]
        out = np.stack([wl, wr]).astype(np.float32)
        return out
    except Exception:
        return x


def _hall_ir(sr):
    """Long, dark, diffused stereo IR. 2.4 s with 45 ms pre-delay."""
    key = int(sr)
    if key in _HALL["ir"]:
        return _HALL["ir"][key]
    dur, pre = 2.00, 0.045
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    env = np.exp(-3.2 * np.maximum(t - pre, 0.0) / dur)
    irL = np.random.default_rng(41).normal(0.0, 1.0, n) * env
    irR = np.random.default_rng(83).normal(0.0, 1.0, n) * env
    irL[:int(sr * pre)] *= np.linspace(0.0, 1.0, int(sr * pre)) ** 2
    irR[:int(sr * pre)] *= np.linspace(0.0, 1.0, int(sr * pre)) ** 2
    st = np.stack([irL, irR]).astype(np.float32)
    st = Pedalboard([HighpassFilter(cutoff_frequency_hz=200.0),
                     LowpassFilter(cutoff_frequency_hz=6500.0)])(st, sr)
    e = float(np.sqrt(np.mean(np.square(st.astype(np.float64))))) + 1e-12
    st = (st / e) * 0.9
    _HALL["ir"][key] = st.astype(np.float32)
    return _HALL["ir"][key]


def _hall(voc, sr):
    """Algorithmic hall. No noise IR — clean diffuse tail.
    0.75 room, 0.5 damping, 1.0 width = wide dark space, no hiss."""
    try:
        y = Pedalboard([Reverb(room_size=0.60, damping=0.50,
                               wet_level=1.0, dry_level=0.0, width=1.0)])(voc, sr).astype(np.float32)
        _a = float(np.sqrt(np.mean(np.asarray(voc, dtype=np.float64) ** 2))) + 1e-9
        _b = float(np.sqrt(np.mean(y.astype(np.float64) ** 2))) + 1e-9
        y = (y * (_a / _b)).astype(np.float32)
        return y
    except Exception:
        return None


def _pingpong(voc, sr, bpm, note=0.75):
    """Stereo ping-pong delay. note: 0.75=dotted 1/8, 1.0=quarter."""
    import numpy as np
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        bpm = 100.0
    if not (bpm > 0) or bpm != bpm:
        bpm = 100.0
    d = max(1, int(sr * (60.0 / bpm) * float(note)))
    fb = 0.20
    n = voc.shape[1]
    pad = d * 8
    src = np.zeros(n + pad, dtype=np.float32)
    src[:n] = ((voc[0] + voc[1]) * 0.5).astype(np.float32)
    out = np.zeros((2, n + pad), dtype=np.float32)
    gain = 1.0
    side = 0
    for tap in range(1, 8):
        off = d * tap
        if off >= n + pad:
            break
        out[side, off:] += src[:n + pad - off] * gain
        side = 1 - side
        gain *= fb
    out = Pedalboard([HighpassFilter(cutoff_frequency_hz=500.0),
                      LowpassFilter(cutoff_frequency_hz=4500.0)])(out, sr).astype(np.float32)
    return out[:, :voc.shape[1]]


def _parallel_distort(x, sr):
    """Parallel saturation for vocal body. Keeps dry untouched."""
    import numpy as np
    from pedalboard import Pedalboard, Distortion, HighpassFilter, Gain
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2:
            return x
        crushed = Pedalboard([
            HighpassFilter(cutoff_frequency_hz=200.0),
            Distortion(drive_db=6.0),
            Gain(gain_db=-6.0),
        ])(a, sr).astype(np.float32)
        return (a * 0.85 + crushed * 0.15).astype(np.float32)
    except Exception:
        return x


def _ambience(voc, sr, bpm, scale=1.0, headroom=True, delay_scale=None, plate_scale=None, plate_from_delay=False, note_mult=0.75):
    import numpy as np
    if delay_scale is None: delay_scale = scale
    if plate_scale is None: plate_scale = scale
    try: bpm = float(bpm)
    except Exception: bpm = 100.0
    if not np.isfinite(bpm) or bpm <= 0: bpm = 100.0

    _bar_note_time = (60.0 / bpm) * 0.5
    n_out = voc.shape[1]

    ping = _pingpong(voc, sr, bpm, note=note_mult)
    plate = _plate(voc, sr)

    def _fit(a, n):
        a = np.asarray(a, dtype=np.float32)
        if a.ndim == 1:
            a = np.stack([a, a])
        if a.shape[1] < n:
            a = np.concatenate([a, np.zeros((a.shape[0], n - a.shape[1]), np.float32)], axis=1)
        else:
            a = a[:, :n]
        return a

    wet = None
    if ping is not None and delay_scale > 0:
        wet = _fit(ping, n_out) * float(delay_scale)
    if plate is not None and plate_scale > 0:
        pt = _fit(plate, n_out) * float(plate_scale)
        wet = pt if wet is None else (wet + pt).astype(np.float32)

    kind = "plate" if plate is not None else "none"
    if wet is None:
        return voc, round(_bar_note_time * 1000.0), "none"
    return (voc + wet).astype(np.float32), round(_bar_note_time * 1000.0), kind


ROLE_BUS = {
    "lead":    {"glue": None,          "plate": 0.18, "delay": 0.16, "exciter": True, "plate_from_delay": False, "note": 1.00},
    "backing": {"glue": (-12.0, 1.30), "plate": 0.15, "delay": 0.13, "exciter": True,  "note": 1.00},
    "adlib":   {"glue": (-14.0, 1.20), "plate": 0.20, "delay": 0.18, "exciter": True,  "note": 0.75},
}


def _role_space(voc, sr, scale):
    """Add extra plate depth for a role so it sits in its own space."""
    try:
        if not scale:
            return voc
        pl = _plate(voc, sr)
        if pl is None:
            return voc
        n = int(sr * 0.030)
        if n > 0 and pl.shape[1] > n:
            q = np.zeros_like(pl)
            q[:, n:] = pl[:, :pl.shape[1] - n]
            pl = q
        return (voc + (SEND_PLATE * float(scale)) * pl).astype(np.float32)
    except Exception:
        return voc


def _role_buses(pre, sr, bpm, raised):
    """Give each vocal role its OWN glue and its OWN reverb depth, then sum.
    No cross-role compression: the lead is never glued to backing or adlib.
    Per-bus peak normalisation is SKIPPED (headroom=False) so the locked role
    levels are untouched; the summed bus normalises once at the end."""
    out = []
    first = None
    for r, y0 in pre.items():
        y = np.asarray(y0, dtype=np.float32)
        if polish is not None:
            try:
                _y, _ = polish.dynamic_eq(y, sr, get_stats=True)
                if _y.shape == y.shape and np.isfinite(_y).all():
                    y = np.asarray(_y, dtype=np.float32)
            except Exception:
                pass
        if raised:
            y = (y * (10.0 ** (raised / 20.0))).astype(np.float32)
        cfg = ROLE_BUS.get(r) or {"glue": None, "plate": 1.0, "delay": 1.0}
        if cfg.get("glue"):
            _thr, _rat = cfg["glue"]
            y = _glue(y, sr, thr=_thr, ratio=_rat)
        if cfg.get("exciter"):
            y = _exciter(y, sr)
        _pl = float(cfg.get("plate", cfg.get("space", 1.0)))
        _dl = float(cfg.get("delay", _pl))
        _pfd = bool(cfg.get("plate_from_delay", False))
        if _pl or _dl or _pfd:
            _nt = float(cfg.get("note", 0.75))
            y, _ms, _kind = _ambience(y, sr, bpm, scale=_pl,
                                      plate_scale=_pl, delay_scale=_dl,
                                      plate_from_delay=_pfd, headroom=False,
                                      note_mult=_nt)
            if first is None:
                first = (_ms, _kind)
        out.append(y)
    return _sum(out), first


KICK_PUNCH_DB = 1.5   # attack-only lift on 40-170 Hz. 0.0 = off


def _transient(x, sr, amount_db, fast_ms=6.0, slow_ms=140.0):
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[1] < 64: return a
        bs = max(1, int(sr * 0.001)); n = a.shape[1] // bs
        if n < 64: return a
        blk = np.abs(a[:, : n * bs]).reshape(a.shape[0], n, bs).max(axis=2)
        kf = float(np.exp(-1.0 / max(1.0, fast_ms)))
        ks = float(np.exp(-1.0 / max(1.0, slow_ms)))
        ef = np.empty_like(blk); es = np.empty_like(blk)
        for c in range(a.shape[0]):
            pf = ps = 0.0
            for i in range(n):
                v = float(blk[c, i])
                pf = v if v > pf * kf else pf * kf
                ps = v if v > ps * ks else ps * ks
                ef[c, i] = pf; es[c, i] = ps
        ratio = np.clip(ef / (es + 1e-9), 0.0, 3.0)
        amt = float(10.0 ** (amount_db / 20.0)) - 1.0
        g = 1.0 + np.clip(ratio - 1.0, 0.0, 2.0) * (amt / 2.0)
        g = np.repeat(g, bs, axis=1)
        if g.shape[1] < a.shape[1]:
            g = np.concatenate([g, np.ones((a.shape[0], a.shape[1] - g.shape[1]), np.float32)], axis=1)
        return (a * g).astype(np.float32)
    except Exception:
        return x


def _kick_punch(x, sr):
    """Attack-only lift on 40-170 Hz. Level already matches refs - no EQ boost."""
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[1] < 128: return x
        lo = Pedalboard([LowpassFilter(cutoff_frequency_hz=170.0)])(a, sr).astype(np.float32)
        hi = (a - lo).astype(np.float32)
        return _headroom(_transient(lo, sr, KICK_PUNCH_DB) + hi, -1.0).astype(np.float32)
    except Exception:
        return x


def _double(voc, sr):
    # PitchShift is optional - without it the two copies still differ
    # by delay (14/22 ms) and pan, which combs and widens on its own.
    try:
        out = np.zeros_like(voc)
        for cents, ms, pan in ((7.0, 14.0, 0.30), (-6.0, 22.0, -0.30)):
            ch = ([] if PitchShift is None else [PitchShift(semitones=cents / 100.0)]) + [
                  HighpassFilter(cutoff_frequency_hz=150.0),
                  LowpassFilter(cutoff_frequency_hz=10000.0)]
            _opt(ch, Chorus, rate_hz=0.4, depth=0.06, mix=0.25)
            ch.append(Delay(delay_seconds=ms / 1000.0, feedback=0.0, mix=1.0))
            y = Pedalboard(ch)(voc, sr).astype(np.float32)
            y[0] *= float(np.sqrt(max(0.0, (1.0 - pan) * 0.5)) * 1.414)
            y[1] *= float(np.sqrt(max(0.0, (1.0 + pan) * 0.5)) * 1.414)
            out += y
        out *= 10.0 ** (DOUBLE_DB / 20.0)
        _DBL["kind"] = "adt (detune+delay+pan)" if PitchShift is not None else "delays+pan only (no PitchShift)"
        return out
    except Exception:
        return None


def _noise_gate(x, sr, reduction_db=8.0, hold_ms=30.0):
    """Gentle gate. Measures the stem's own noise floor, then ducks
    quiet passages by up to `reduction_db`. Not a hard gate — smooth
    ramp, hold time keeps it from chattering between syllables."""
    import numpy as np
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[1] < 512:
            return x
        mono = a.mean(axis=0) if a.shape[0] > 1 else a[0]
        win = max(1, int(sr * 0.010))
        n_frames = len(mono) // win
        if n_frames < 4:
            return x
        frames = mono[: n_frames * win].reshape(n_frames, win)
        env = 20.0 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-12)
        floor = float(np.percentile(env, 10))
        thr = floor + 3.0
        # smooth gate curve in dB -> linear
        gate_db = np.where(env < thr, -reduction_db, 0.0)
        # hold: keep gate open briefly after last loud frame
        hold_n = max(1, int(hold_ms / 10.0))
        held = np.zeros_like(gate_db)
        counter = 0
        for i in range(len(gate_db)):
            if gate_db[i] >= 0.0:
                held[i] = 0.0
                counter = hold_n
            else:
                if counter > 0:
                    held[i] = 0.0
                    counter -= 1
                else:
                    held[i] = gate_db[i]
        # attack/release smoothing (5 ms / 80 ms)
        a_c, r_c = 0.40, 0.06
        sm = np.empty_like(held)
        p_ = 0.0
        for i in range(len(held)):
            c = a_c if held[i] > p_ else r_c
            p_ = c * p_ + (1.0 - c) * held[i]
            sm[i] = p_
        gain = 10.0 ** (sm / 20.0)
        gain_full = np.repeat(gain, win)
        if gain_full.size < a.shape[1]:
            gain_full = np.concatenate([gain_full, np.ones(a.shape[1] - gain_full.size, np.float32)])
        else:
            gain_full = gain_full[: a.shape[1]]
        return (a * gain_full[None, :]).astype(np.float32)
    except Exception:
        return x


def _align_to_beat(voc, beat, sr, max_shift_ms=400):
    """Auto-align a vocal to the beat via cross-correlation of energy
    envelopes. Returns the vocal shifted earlier (or later) so its first
    energy peak lands on the beat's first energy peak. Only small shifts."""
    import numpy as np
    try:
        if voc is None or beat is None:
            return voc, 0
        v = voc.mean(axis=0) if voc.ndim > 1 else voc
        b = beat.mean(axis=0) if beat.ndim > 1 else beat
        n = min(len(v), len(b))
        if n < sr:
            return voc, 0
        win = max(1, int(sr * 0.010))
        nf = n // win
        ve = np.abs(v[: nf * win].reshape(nf, win)).max(axis=1)
        be = np.abs(b[: nf * win].reshape(nf, win)).max(axis=1)
        # keep only first 30 s of envelope (align at start of song)
        cap = min(nf, int(30.0 / 0.010))
        ve = ve[:cap]; be = be[:cap]
        if ve.size < 8 or be.size < 8:
            return voc, 0
        ve = ve - ve.mean(); be = be - be.mean()
        # cross-correlation via FFT
        nfft = 1 << int(2 * cap - 1).bit_length()
        F = np.fft.rfft(ve, nfft) * np.conj(np.fft.rfft(be, nfft))
        cc = np.fft.irfft(F, nfft)[:cap]
        # search only +/- max_shift frames
        msh = max(1, int(max_shift_ms / 10.0))
        lo = cap - msh
        hi = cap + msh
        if lo < 0: lo = 0
        if hi > cap: hi = cap
        if hi <= lo:
            return voc, 0
        # lag = shift of vocal relative to beat
        seg = cc[lo:hi]
        lag_idx = int(np.argmax(seg)) + lo - cap   # negative = vocal is late
        if abs(lag_idx) < 2:
            return voc, 0
        shift = -lag_idx * win                       # positive = shift vocal earlier
        if shift > 0:
            out = voc[:, shift:].astype(np.float32)
        else:
            pad = -shift
            out = np.concatenate([np.zeros((voc.shape[0], pad), np.float32), voc], axis=1)
        return out, int(round(lag_idx * win / sr * 1000.0))   # ms the vocal was off
    except Exception:
        return voc, 0


def shift_vocal_earlier(vocal, sr, shift_ms=10.0):
    """Shift vocal earlier relative to a readymade beat.
    Does not change tempo or pitch. Same number of samples."""
    if sr <= 0:
        return vocal
    if not 0.0 <= shift_ms <= 100.0:
        return vocal
    audio = np.asarray(vocal, dtype=np.float32)
    shift_samples = int(round(sr * shift_ms / 1000.0))
    if shift_samples == 0:
        return audio.copy()
    shifted = np.zeros_like(audio)
    if audio.ndim == 1:
        shifted[:-shift_samples] = audio[shift_samples:]
    elif audio.ndim == 2:
        shifted[:, :-shift_samples] = audio[:, shift_samples:]
    else:
        return vocal
    return shifted


def _role_chain(voc, sr, st, role):
    t = _treat_for(role)
    moves = [["role", role], ["highpass", t["hpf"]]]
    # (vocal chop disabled — was cutting the start of the first word)
    ch = [HighpassFilter(cutoff_frequency_hz=t["hpf"])]
    if st["mud"] > 1.0:
        g = -min(MAX_MUD_CUT, t["mud"], (st["mud"] - 1.0) * 1.1 * 2.0)
        if g < -0.2:
            ch.append(PeakFilter(380.0, g, 1.5)); moves.append(["mud 380", round(g, 2)])
    if st["box"] > 1.0:
        g = -min(MAX_BOX_CUT, t["box"], (st["box"] - 1.0) * 0.8 * 1.5)
        if g < -0.2:
            ch.append(PeakFilter(600.0, g, 1.0)); moves.append(["box 600", round(g, 2)])
    if st["harsh"] > 1.5:
        g = -min(MAX_HARSH_CUT, t["harsh"], (st["harsh"] - 1.5) * 2.0)
        if g < -0.2:
            ch.append(PeakFilter(4400.0, g, 1.2)); moves.append(["harsh 4.4k", round(g, 2)])
    if st["presence"] < -2.5 and t["pres"] > 0:
        g = min(MAX_PRESENCE * t["pres"], (-st["presence"] - 2.5) * 1.8 + 0.4)
        if g > 0.2:
            ch.append(PeakFilter(3000.0, min(g, 2.0), 1.0)); moves.append(["presence 3k", round(min(g, 2.0), 2)])
    # (noise gate disabled — was chopping word tails that feed the delay)
    _thr = float(np.clip(_rms_db(voc) - 1.5, -32.0, -12.0))
    ch.append(Compressor(threshold_db=_thr, ratio=t["ratio"],
                         attack_ms=t["atk"], release_ms=t["rel"]))
    moves.append(["compress", "%s:1 @ %.1f" % (t["ratio"], _thr)])
    drive = min(1.2, t["sat"])
    try:
        _ah = (np.abs(voc) >= 0.999).any(axis=0) if getattr(voc, "ndim", 1) == 2 else (np.abs(voc) >= 0.999)
        _ad = np.diff(np.concatenate([[0], _ah.astype(np.int8), [0]]))
        _as = np.where(_ad == 1)[0]
        _ae = np.where(_ad == -1)[0]
        _aruns = (_ae - _as) if _as.size else np.array([], dtype=int)
        _along = int((_aruns >= 3).sum()) if _aruns.size else 0
        _amax = int(_aruns.max()) if _aruns.size else 0
        if _along >= 200 and _amax >= 15:
            drive = drive * 0.5
    except Exception:
        pass
    out = Pedalboard(ch)(voc, sr).astype(np.float32)
    _pre = _rms_db(voc)
    _post = _rms_db(out)
    _makeup_cap = 2.0 if role == "backing" else 4.0
    makeup = float(np.clip(_pre - _post, 0.0, _makeup_cap))
    if makeup > 0.05:
        out = (out * (10.0 ** (makeup / 20.0))).astype(np.float32)
    moves.append(["makeup", round(makeup, 2)])
    # Professional Engineering Fix: Clean out the harsh sibilance BEFORE saturating
    out, dd = _deess(out, sr, st)
    moves.append(["de-ess", dd])
    
    # Apply a tight notch to decouple vocal weight completely from the instruments
    try:
        out = Pedalboard([
            PeakFilter(cutoff_frequency_hz=320.0, gain_db=-2.5, q=1.1),
            LowshelfFilter(cutoff_frequency_hz=150.0, gain_db=-3.0, q=0.7),
            HighpassFilter(cutoff_frequency_hz=95.0),
        ])(out, sr).astype(np.float32)
    except Exception:
        pass
        
    out = _saturate(out, sr, drive)
    moves.append(["saturate", round(drive, 2)])

    # 3D Headphone Wrap Exciter: Pulls the crystal clear air right up to the ear pads without clipping
    try:
        from pedalboard import HighShelfFilter as _HSF
        out = Pedalboard([
            _HSF(cutoff_frequency_hz=12500.0, gain_db=2.5, q=0.7) # Extra expensive sonic sheen layer
        ])(out, sr).astype(np.float32)
    except Exception:
        pass
    
    try:
        # Boost clean high fidelity air gracefully at the top of the chain
        out = Pedalboard([HighShelfFilter(cutoff_frequency_hz=11000.0,
                                          gain_db=min(MAX_AIR + 1.0, t["air"] + 0.8), q=0.7)])(out, sr).astype(np.float32)
    except Exception:
        pass
    try:
        out = Pedalboard([HighShelfFilter(cutoff_frequency_hz=11000.0, gain_db=-1.0, q=0.7)])(out, sr).astype(np.float32)
    except Exception:
        pass
    moves.append(["air 11k", 2.0])
    out = (out * (10.0 ** (t["gain"] / 20.0))).astype(np.float32)
    moves.append(["role gain", t["gain"]])
    return out, moves


def vocal_process(voc, sr, st, bpm):
    out, moves = _role_chain(voc, sr, st, "lead")
    return out, moves


def _plan(st, pres_min=2.5):
    """Commercial-ready lead pocket: guarantees floor cuts across ALL major 
    frequency bands so the vocal floats inside dense 2-track masters."""
    now = {BODY: st["mask_body"], PRES: st["clarity"], HARSH: st["mask_harsh"]}
    out = {}
    # Professional minimum floor targets to force room inside the ready-made beat
    floors = {BODY: 1.8, PRES: float(pres_min), HARSH: 1.5}
    for b in (BODY, PRES, HARSH):
        v = max(0.0, (DUCK_TARGET[b] - now[b]) * 0.9)
        v = max(v, floors[b]) # Force the minimum floor
        out[b] = -min(DUCK_CAP[b], v)
    return out


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
            g = gain
            if g.shape[0] != S.shape[0]:
                if g.shape[0] < S.shape[0]:
                    g = np.concatenate([g, np.ones(S.shape[0] - g.shape[0], np.float32)])
                else:
                    g = g[:S.shape[0]]
            S[:, k] *= g[:, None]
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
    if beat is not None and "LEAD_SHIFT_MS" in globals() and LEAD_SHIFT_MS > 0:
        _padn = int(sr * LEAD_SHIFT_MS / 1000.0)
        beat = np.concatenate([np.zeros((beat.shape[0], _padn), np.float32), beat], axis=1)
        rep["beat_shift_later_ms"] = LEAD_SHIFT_MS
    # Shift BEAT later (pad with silence) so vocal lands on the beat.
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

    # ---- optional declip: only fires on genuinely damaged stems ----
    if _declip is not None:
        for _r in list(ro_map.keys()):
            try:
                _v = ro_map[_r]
                _h = (np.abs(_v) >= 0.999).any(axis=0) if _v.ndim == 2 else (np.abs(_v) >= 0.999)
                if int(_h.sum()) < 200:
                    continue
                _dd = np.diff(np.concatenate([[0], _h.astype(np.int8), [0]]))
                _ds = np.where(_dd == 1)[0]
                _de = np.where(_dd == -1)[0]
                _dr = (_de - _ds) if _ds.size else np.array([], dtype=int)
                _dlong = int((_dr >= 3).sum()) if _dr.size else 0
                _dmax = int(_dr.max()) if _dr.size else 0
                if _dlong < 200 or _dmax < 15:
                    continue
                _fixed, _drep = _declip.declip(_v, sr)
                if _drep.get("repaired", 0) > 0:
                    ro_map[_r] = _fixed
                    rep.setdefault("declip", {})[_r] = _drep
            except Exception as _e:
                rep.setdefault("declip_error", {})[_r] = str(_e)[:120]

    _match_role_levels(ro_map, sr, rep)
    rep["mode"] = "two_track" if len(beats) == 1 else "stems"
    rep["roles"] = {r: len(groups.get(r) or []) for r in ROLE_VOCALS if groups.get(r)}
    bpm = detect_tempo(_mono(beat), sr)
    rep["bpm"] = round(bpm, 1)

    freq = np.fft.rfftfreq(N, 1.0 / sr)
    Bst = _stft(_mono(beat))
    st = _measures(Bst, _stft(_mono(voc)), freq)
    rep["measured"] = {k: round(float(v), 2) for k, v in st.items()}

    parts, moves, _pre = [], {}, {}
    for r in list(ro_map.keys()):
        y, mv = _role_chain(ro_map[r], sr, st, r)
        if r == "lead":
            pass  # dry lead stays mono/centered. Width lives on the wet return.
        if ROLE_TREAT[r]["width"] != 1.0:
            y = _widen(y, sr, ROLE_TREAT[r]["width"])
        _pre[r] = y
        parts.append(y); moves[r] = mv
    core = _sum(parts)   # dry sum: polish, raise and _dry_voc all read this
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
    rep["clarity_before"] = round(float(st["clarity"]), 2)

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

    _dry_voc = core.copy()
    core, _info = _role_buses(_pre, sr, bpm, raised)
    try:
        beat = _kick_punch(beat, sr)
        rep["kick_punch_db"] = KICK_PUNCH_DB
    except Exception as _e:
        rep["kick_punch_error"] = str(_e)[:120]
    ms, pk = _info if _info else (0, "none")
    rep["bus"] = {r: ROLE_BUS.get(r, {}) for r in _pre}
    rep["slap_ms"] = ms
    rep["plate"] = pk
    rep["plate_error"] = plate_error()

    _DOUBLE_ON = False   # ADT detune copy welds lead+adlib - off
    side_ids = [r for r in ("lead", "adlib") if r in ro_map] if _DOUBLE_ON else []
    if side_ids:
        dbl = _double(_sum([ro_map[r] for r in side_ids]), sr)
        if dbl is not None:
            n = max(core.shape[1], dbl.shape[1])
            core = (_pad(core, n) + _pad(dbl, n)).astype(np.float32)
            rep["double"] = True
            rep["double_kind"] = _DBL.get("kind", "")
        else:
            rep["double"] = False
    else:
        rep["double"] = False

    ducked, plan, vpres, post = _duck(beat, _dry_voc, freq, st)
    tries = 1

    rep["duck_db"] = {("%d-%d" % b): round(v, 2) for b, v in plan.items()}
    rep["clarity_after_raise"] = round(float(st["clarity"]), 2)
    rep["clarity_after"] = None if post is None else round(float(
        _avg(_stft(_mono(core)), PRES, freq) - _avg(_stft(_mono(ducked)), PRES, freq)), 2)
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

WIDEN_MASTER = 1.0


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
        target = {"adlib": lead - 8.0, "backing": lead - 4.0}
        rep["level_match"] = {"lead_rms": round(lead, 1)}
        for r, tgt in target.items():
            v = ro_map.get(r)
            if v is None or getattr(v, "shape", (0, 0))[1] == 0:
                continue
            cur = float(_rms_db(v))
            if cur < -60.0:
                rep["level_match"][r] = "SILENT (%.1f dB) - bad file" % cur
                continue
            if (lead - cur) > 18.0:
                rep["level_match"][r] = "TOO QUIET (%.1f dB under lead) - not boosted" % (lead - cur)
                pass
            pk = float(np.max(np.abs(v))) or 1e-9
            head = 20.0 * np.log10(0.9 / pk)
            gain = float(np.clip(min(tgt - cur, max(head, 8.0)), -12.0, 20.0))
            if abs(gain) >= 0.1:
                ro_map[r] = (v * (10.0 ** (gain / 20.0))).astype(np.float32)
            rep["level_match"][r] = {"from": round(cur, 1), "gain": round(gain, 2)}
    except Exception as e:
        rep["level_match_error"] = str(e)[:300]


def soft_clip(x, sr, knee=0.70, oversample=4):
    """Transparent soft clipper. Linear below `knee`, smooth tanh bend above.
    4x FFT oversampling keeps the new harmonics from aliasing back down.
    Quiet material passes through untouched."""
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    n = a.shape[1]
    k = int(oversample)
    if k < 2 or n < 64:
        return x
    up = k * n
    y = np.empty((a.shape[0], up), dtype=np.float64)
    for c in range(a.shape[0]):
        F = np.fft.rfft(a[c].astype(np.float64))
        F2 = np.zeros(up // 2 + 1, dtype=np.complex128)
        F2[: F.shape[0]] = F * k
        y[c] = np.fft.irfft(F2, up)
    t = float(knee)
    m = np.abs(y)
    over = m > t
    if np.any(over):
        y[over] = np.sign(y[over]) * (t + (1.0 - t) * np.tanh((m[over] - t) / (1.0 - t)))
    out = np.empty((a.shape[0], n), dtype=np.float64)
    for c in range(a.shape[0]):
        F = np.fft.rfft(y[c])
        out[c] = np.fft.irfft(F[: n // 2 + 1] / k, n)
    return out.astype(np.float32)

# --- WRATTY DELAY HOOK v1 BEGIN (python3 install_delay.py --remove restores the original delay) ---
try:
    try:
        import delay_fx as _dfx
    except ImportError:
        from . import delay_fx as _dfx
    import os as _os_dfx
    _pingpong_legacy = _pingpong

    def _pingpong(voc, sr, bpm, note=0.75):
        old = _pingpong_legacy(voc, sr, bpm, note=note)
        if _os_dfx.environ.get("WRATTY_DELAY", "1") == "0":
            return old
        try:
            ref = np.asarray(old)
            if ref.ndim == 2 and ref.shape[0] <= 8:
                lay, n_ref = "cf", ref.shape[1]
            elif ref.ndim == 2:
                lay, n_ref = "cl", ref.shape[0]
            else:
                lay, n_ref = "m", ref.shape[0]
            r_old = float(np.sqrt(np.mean(np.square(ref, dtype=np.float64))))
            if r_old <= 0.0:
                return old
            # level-match DISABLED — play at preset level, not old-delay level
            wet, _info = _dfx.render(voc, sr, bpm, _PRESET.get("_name", "neutral"),
                                     note=note, target_rms=r_old)
            n = wet.shape[1]
            if n < n_ref:
                wet = np.pad(wet, ((0, 0), (0, n_ref - n)))
            elif n > n_ref:
                wet = wet[:, :n_ref]
            if lay == "cl":
                wet = wet.T
            elif lay == "m":
                wet = wet.mean(axis=0)
            return np.ascontiguousarray(wet, dtype=np.float32)
        except Exception as _e:
            print("[delay_fx] fallback to legacy delay:", _e)
            return old
except Exception as _e:
    print("[delay_fx] not installed, using legacy delay:", _e)
# --- WRATTY DELAY HOOK v1 END ---

# --- WRATTY REVERB HOOK v1 BEGIN (python3 install_reverb.py --remove restores the original) ---
try:
    try:
        import reverb_fx as _rvx
    except ImportError:
        from . import reverb_fx as _rvx
    import os as _os_rvx
    _plate_legacy = _plate
    _hall_legacy = _hall
    _REV_NOTE_CACHE = {"bpm": None}

    def _reverb_swap(voc, sr, kind, legacy_fn):
        old = legacy_fn(voc, sr)
        if old is None:
            return None
        if _os_rvx.environ.get("WRATTY_REVERB", "1") == "0":
            return old
        try:
            ref = np.asarray(old)
            n_ref = ref.shape[-1] if ref.ndim >= 2 else ref.shape[0]
            r_old = float(np.sqrt(np.mean(np.square(ref, dtype=np.float64))))
            if r_old <= 0.0:
                return old
            # song bpm is stored by the delay hook; fall back to 100
            bpm = _PRESET.get("_bpm", 100.0)
            wet, _info = _rvx.render(voc, sr, bpm, _PRESET.get("_name", "neutral"),
                                     target_rms=r_old, out_len=n_ref)
            if wet.shape[-1] < n_ref:
                wet = np.pad(wet, ((0, 0), (0, n_ref - wet.shape[-1])))
            elif wet.shape[-1] > n_ref:
                wet = wet[:, :n_ref]
            return np.ascontiguousarray(wet, dtype=np.float32)
        except Exception as _e:
            print("[reverb_fx] fallback to legacy %s: %s" % (kind, _e))
            return old

    def _plate(voc, sr):
        return _reverb_swap(voc, sr, "plate", _plate_legacy)

    def _hall(voc, sr):
        return _reverb_swap(voc, sr, "hall", _hall_legacy)
except Exception as _e:
    print("[reverb_fx] not installed, using legacy reverb:", _e)
# --- WRATTY REVERB HOOK v1 END ---
