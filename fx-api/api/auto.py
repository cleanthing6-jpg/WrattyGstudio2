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

# ── Feature gates for engines added 2026-10-14. Flip one at a time to
#    isolate regressions. All False = chain runs pre-upgrade code.
_NEW = {
    "clip_gain":     False,
    "fet":           False,
    "la2a_pro":      False,
    "saturator_pro": True,
    "deess_pro":     True,
    "exciter_t1":    False,
    "adt_t1":        True,
    "delay_t1":      True,
    "plate_t1":      True,
    "adaptive_amb":  True,
    "parallel_ny":   False,
    "wrap3d":        False,
}
from pedalboard import (
    Pedalboard, HighpassFilter, LowpassFilter, PeakFilter, HighShelfFilter, LowShelfFilter,
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
        "target_lufs": -10.5, "glue_ratio": 1.5, "glue_gr_db": 0.5,
        "width": 1.20, "plate_db": -21.0, "slap_db": -8.0,
        "max_air": 2.0, "max_deess": 1.2,
        "max_mud_cut": 6.0, "max_box_cut": 4.0,
        "max_presence": 3.0, "max_harsh_cut": 5.0,
        "hpf_min": 80.0, "hpf_max": 100.0,
        "deess_offset_db": 2.5, "deess_atk": 0.5, "deess_rel": 2.0,
        "duck_cap": {BODY: 2.5, PRES: 5.5, HARSH: 3.0},
        "duck_target": {BODY: 2.0, PRES: 4.8, HARSH: 2.0},
        "low_mono_hz": 80.0,
        "role_treat_adlib": {
            "gain": -5.0, "hpf": 150.0,
            "mud": 2.0, "mud_hz": 330.0, "mud_q": 2.5,
            "box": 1.5, "box_hz": 600.0, "box_q": 1.0,
            "pres": 0.5, "pres_hz": 3000.0, "pres_q": 1.0,
            "harsh": 2.0, "harsh_hz": 4800.0, "harsh_q": 3.0,
            "air": 0.4, "ratio": 2.5, "atk": 15.0, "rel": 120.0,
            "sat": 0.2, "width": 1.3,
            "body_db": 0.0,
        },
        "role_treat_backing": {
            "gain": -3.0, "hpf": 140.0,
            "mud": 3.0, "mud_hz": 330.0, "mud_q": 2.5,
            "box": 2.0, "box_hz": 600.0, "box_q": 1.0,
            "pres": 0.0, "pres_hz": 3000.0, "pres_q": 1.0,
            "harsh": 2.0, "harsh_hz": 4800.0, "harsh_q": 3.0,
            "air": 0.4, "ratio": 2.5, "atk": 20.0, "rel": 160.0,
            "sat": 0.2, "width": 1.2,
            "body_db": 0.0,
        },
        "role_treat_lead": {
            "gain": 0.0, "hpf": 95.0, "body_db": 2.0,
            "mud": 2.5, "mud_hz": 330.0, "mud_q": 2.5,
            "box": 2.5, "box_hz": 600.0, "box_q": 1.0,
            "pres": 0.8, "pres_hz": 3200.0, "pres_q": 1.0,
            "harsh": 1.4, "harsh_hz": 4800.0, "harsh_q": 3.0,
            "air": 3.0, "ratio": 2.5, "atk": 5.0, "rel": 100.0,
            "sat": 0.15, "width": 1.0,
            "body_db": 0.0,
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
        "lead": {"air": 0.0, "sat": 0.15},
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
    globals()["MAX_MUD_CUT"] = float(cfg.get("max_mud_cut", 3.0))
    globals()["MAX_BOX_CUT"] = float(cfg.get("max_box_cut", 3.0))
    globals()["MAX_PRESENCE"] = float(cfg.get("max_presence", 1.5))
    globals()["MAX_HARSH_CUT"] = float(cfg.get("max_harsh_cut", 3.0))
    SEND_PLATE = 10.0 ** (float(cfg.get("plate_db", -14.0)) / 20.0)
    SEND_SLAP = 10.0 ** (float(cfg.get("slap_db", -14.0)) / 20.0)
    return _PRESET


def _treat_for(role):
    t = dict(ROLE_TREAT.get(role, ROLE_TREAT["other"]))
    if role == "lead":
        for _k, _v in (_PRESET.get("role_treat_lead") or {}).items():
            t[_k] = _v
    elif role == "backing":
        for _k, _v in (_PRESET.get("role_treat_backing") or {}).items():
            t[_k] = _v
    elif role == "adlib":
        for _k, _v in (_PRESET.get("role_treat_adlib") or {}).items():
            t[_k] = _v
    d = _PRESET.get("_deltas", {}).get(role)
    if d:
        for _k, _v in d.items():
            t[_k] = t.get(_k, 0.0) + float(_v)
    return t

# Lead shift earlier in ms. Tune until vocal lands on beat.

# Lead vocal shift earlier in ms (aligns vocal to beat).

ROLE_VOCALS = ("lead", "adlib", "backing")
CLARITY_MIN = 2.0
RAISE_PER_PASS = 0.75
RAISE_CAP = 2.5
SEND_WET = 0.11
DOUBLE_DB = -18.0
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


def detect_tempo(beat_mono, sr, with_conf=False):
    def _ret(bpm, conf):
        return (float(bpm), float(conf)) if with_conf else float(bpm)
    try:
        S = _stft(beat_mono)
        flux = np.maximum(0.0, np.diff(np.abs(S), axis=0)).mean(axis=1)
        del S
        flux = flux - flux.mean()
        n = len(flux)
        if n < 128:
            return _ret(100.0, 0.0)
        F = np.fft.rfft(flux, 2 * n)
        ac = np.fft.irfft(F * np.conj(F))[:n]
        fps = sr / float(HOP)
        lo = int(round(fps * 60.0 / 190.0))
        hi = min(n - 1, int(round(fps * 60.0 / 60.0)))
        if hi <= lo:
            return _ret(100.0, 0.0)
        lag = lo + int(np.argmax(ac[lo:hi]))
        if lag <= 0:
            return _ret(100.0, 0.0)
        bpm = 60.0 * fps / lag
        while bpm < 80.0:
            bpm *= 2.0
        while bpm > 180.0:
            bpm /= 2.0
        conf = float(ac[lag] / (ac[0] + 1e-12))
        return _ret(bpm, conf)
    except Exception:
        return _ret(100.0, 0.0)


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
    if drive_db is None or drive_db <= 0.001:
        return x
    if _NEW["saturator_pro"]:
        try:
            import dsp_pro
            return dsp_pro.pro_saturator(x, sr, drive_db=float(drive_db))
        except Exception:
            return x
    try:
        import numpy as _np
        a = _np.asarray(x, dtype=_np.float32)
        d = 1.0 + float(drive_db) * 2.0
        b = 0.15 * float(drive_db)
        y = _np.tanh(a * d + b) - _np.tanh(b)
        y = y + 0.15 * float(drive_db) * (y ** 2) * _np.sign(y)
        ri = _np.sqrt(_np.mean(a ** 2)) + 1e-9
        ro = _np.sqrt(_np.mean(y ** 2)) + 1e-9
        return (y * (ri / ro)).astype(_np.float32)
    except Exception:
        return x

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
    if _NEW["deess_pro"]:
        try:
            import dsp_pro
            return dsp_pro.deess_drop_in(voc, sr, st, ratio=4.0)
        except Exception:
            return voc, 0.0
    try:
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
    except Exception:
        return voc, 0.0


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
            Distortion(drive_db=3.0),
            Gain(gain_db=-6.0),
        ])(a, sr).astype(np.float32)
        return (a * 0.85 + crushed * 0.15).astype(np.float32)
    except Exception:
        return x


def _ambience(voc, sr, bpm, scale=1.0, headroom=True, delay_scale=None, plate_scale=None, plate_from_delay=False, note_mult=0.75, role=None):
    """Reverb only. _plate is wrapped by reverb_fx hook = Claude's module.
    No delay, no hall, no widening, no ducking, no auto-send."""
    import numpy as np
    if plate_scale is None: plate_scale = scale
    n_out = voc.shape[1]

    plate = None
    _ap = None
    _aa = None
    if _NEW["plate_t1"]:
        try:
            import dsp_pro
            if _NEW.get("adaptive_amb", False):
                try:
                    import adaptive_ambience as _aa
                    _ap = _aa.choose_params(voc, sr, bpm, role or "lead",
                                            str(_PRESET.get("ambience_style") or "clean"))
                except Exception as _ae:
                    _REVERB_LAST["adaptive_error"] = str(_ae)[:200]
                    _ap = None
            if _ap is not None:
                plate = dsp_pro.plate_wet(voc, sr, mix=1.0,
                                          predelay_ms=_ap["predelay_ms"], hp_hz=_ap["hpf_hz"],
                                          lp_hz=_ap["lpf_hz"], ir_len_s=_ap["ir_len_s"],
                                          melt=_ap.get("melt", 0.0),
                                          duck_depth=_ap.get("duck_db", 13.0))
            else:
                plate = dsp_pro.plate_wet(voc, sr, mix=1.0, duck_depth=10.0)
        except Exception as _pr:
            _REVERB_LAST["error"] = str(_pr)[:200]
            plate = None
    if plate is None:
        plate = _plate(voc, sr)

    if plate is None or plate_scale <= 0:
        return voc, 0, "none"

    a = np.asarray(plate, dtype=np.float32)
    if a.ndim == 1:
        a = np.stack([a, a])
    if a.shape[1] < n_out:
        a = np.concatenate([a, np.zeros((a.shape[0], n_out - a.shape[1]), np.float32)], axis=1)
    else:
        a = a[:, :n_out]

    _send = float(plate_scale)
    if _ap is not None:
        try:
            _send = _aa.calibrate_send(voc, a, _ap["target_db"])
            _info = {k: (round(v, 3) if isinstance(v, float) else v)
                     for k, v in _ap.items() if k != "analysis"}
            _info["send"] = round(_send, 4)
            _info["lowmid"] = round(_ap["analysis"]["lowmid"], 3)
            _info["bright_db"] = round(_ap["analysis"]["bright_db"], 1)
            _REVERB_LAST.setdefault("adaptive_by_role", {})[role or "lead"] = _info
        except Exception as _ce:
            _REVERB_LAST["adaptive_error"] = str(_ce)[:200]
            _send = float(plate_scale)
    wet = a * _send

    # --- SPEC DELAY (afrobeats_default_preset_v1.json) ---
    dly_wet = None
    dly_info = {}
    if role in ("lead", "adlib") or role is None:
        _spec_render = None
        if _NEW["delay_t1"]:
            try:
                import dsp_delay as _dspec
                _spec_render = _dspec.delay_render
            except Exception:
                _spec_render = None
        if _spec_render is None:
            try:
                import delay_spec as _dspec2
                _spec_render = _dspec2.render
            except Exception:
                _spec_render = None
        if _spec_render is not None:
            try:
                # Adaptive delay — pick note/feedback/send from BPM + vocal
                _dpar = None
                try:
                    import adaptive_ambience as _aa_d
                    _dpar = _aa_d.choose_delay_params(voc, sr, bpm, role or "lead",
                                                        str(_PRESET.get("ambience_style") or "clean"))
                except Exception:
                    _dpar = None
                if _dpar is not None:
                    try:
                        _dy, _dinfo = _spec_render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"),
                                                  note_div=_dpar["note_factor"], feedback=_dpar["feedback"])
                    except TypeError:
                        _dy, _dinfo = _spec_render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))
                    try:
                        _dsend = _aa_d.calibrate_send(voc, _dy, _dpar["target_db"])
                        _dy = (_dy * _dsend).astype(__import__("numpy").float32)
                        _dinfo["adaptive"] = {
                            "note_factor": round(_dpar["note_factor"], 3),
                            "delay_ms": round(_dpar["delay_ms"], 1),
                            "feedback": round(_dpar["feedback"], 3),
                            "target_db": _dpar["target_db"],
                            "send": round(float(_dsend), 4),
                        }
                    except Exception as _de:
                        _dinfo["adaptive_error"] = str(_de)[:200]
                else:
                    _dy, _dinfo = _spec_render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))
                if _dy is not None:
                    if _dy.shape[1] < n_out:
                        _dy = np.concatenate([_dy, np.zeros((_dy.shape[0], n_out - _dy.shape[1]), np.float32)], axis=1)
                    elif _dy.shape[1] > n_out:
                        _dy = _dy[:, :n_out]
                    dly_wet = _dy
                    dly_info = _dinfo or {}
            except Exception as _de:
                dly_info = {"error": str(_de)[:200]}
    if role is not None:
        _DELAY_LAST[role] = dly_info
    if dly_wet is not None:
        try:
            import numpy as _np
            _dry_rms = float(_np.sqrt(_np.mean(np.asarray(voc, np.float32)**2)) + 1e-12)
            _wet_rms = float(_np.sqrt(_np.mean(np.asarray(dly_wet, np.float32)**2)) + 1e-12)
            dly_info["wet_db_rel_dry"] = round(20.0*_np.log10(_wet_rms/_dry_rms + 1e-12), 2)
        except Exception:
            pass
        _DELAY_LAST[role] = dly_info
    try:
        import numpy as _np
        _dry_rms_p = float(_np.sqrt(_np.mean(np.asarray(voc, np.float32)**2)) + 1e-12)
        _wet_rms_p = float(_np.sqrt(_np.mean(np.asarray(wet, np.float32)**2)) + 1e-12)
        _REVERB_LAST["plate_db_rel_dry"] = round(20.0*_np.log10(_wet_rms_p/_dry_rms_p + 1e-12), 2)
    except Exception:
        pass
    if dly_wet is not None and delay_scale is not None:
        dly_wet = (dly_wet * float(delay_scale)).astype(np.float32)
    base = (voc + wet) if dly_wet is None else (voc + wet + dly_wet)
    return base.astype(np.float32), 0, "plate"



ROLE_BUS = {
    "lead":    {"glue": None,          "plate": 0.1, "delay": 1.0, "exciter": False, "plate_from_delay": False, "note": 0.75},
    "backing": {"glue": (-12.0, 1.30), "plate": 0.06, "delay": 1.0, "exciter": False,  "note": 1.00},
    "adlib":   {"glue": (-14.0, 1.20), "plate": 0.12, "delay": 1.0, "exciter": False,  "note": 0.75},
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
                                      note_mult=_nt, role=r)
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
    if _NEW["adt_t1"]:
        try:
            import dsp_tier1
            blend = 10.0 ** (DOUBLE_DB / 20.0)
            out = dsp_tier1.adt_double(voc, sr, depth_ms=14.0, rate_hz=0.5,
                                       right_offset_ms=8.0, pan=0.55, blend=blend)
            _DBL["kind"] = "adt (LFO+cubic, 14/22ms, +/-0.30pan)"
            return out
        except Exception as _e:
            _DBL["error"] = repr(_e)
            return None
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
    except Exception as _e:
        _DBL["error"] = repr(_e)
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





def _adaptive_hpf(voc, sr, fallback_hz):
    """Pick HPF from measured vocal pitch. Clamped 70-110 Hz (same range as qc.py).
    Falls back to preset value on any failure. Only for lead."""
    try:
        import qc as _qc
    except Exception:
        try:
            from . import qc as _qc
        except Exception:
            return fallback_hz
    try:
        x = voc.mean(0) if getattr(voc, "ndim", 1) > 1 else voc
        f0 = _qc.f0_percentiles(x, sr)
        if not f0:
            return fallback_hz
        _lo = float(_PRESET.get("hpf_min", 70.0))
        _hi = float(_PRESET.get("hpf_max", 110.0))
        return float(int(min(_hi, max(_lo, 0.7 * float(f0["f0_p2"])))))
    except Exception:
        return fallback_hz


def _role_chain(voc, sr, st, role):
    t = _treat_for(role)
    _tone_plan = None
    if role == "lead":
        try:
            import adaptive_tone as _at
            voc, _tone_plan = _at.tone_correct(voc, sr, return_plan=True)
        except Exception:
            _tone_plan = None
    _comp = None
    if role == "lead":
        try:
            import adaptive_ambience as _aa_c
            _comp = _aa_c.tune_compressors(voc, sr)
        except Exception:
            _comp = None
    # Adaptive vocal tone — measure lowmid, adjust body_db / mud cap per user
    if role == "lead":
        try:
            import adaptive_ambience as _aa
            _vt = _aa.tune_vocal(voc, sr, role)
            if _vt is not None:
                t = dict(t)
                t["body_db"] = _vt["body_db"]
                t["mud"] = _vt["mud_cap"]
        except Exception:
            pass
    if role == "lead":
        _h = _adaptive_hpf(voc, sr, float(t["hpf"]))
        if _h > 0:
            t["hpf"] = _h
    moves = [["role", role], ["highpass", t["hpf"]]]
    if _tone_plan is not None:
        moves.append(["tone-hpf", _tone_plan["hpf_hz"]])
        if _tone_plan["low_shelf_db"] < -0.2:
            moves.append(["tone-low", round(_tone_plan["low_shelf_db"], 2)])
        if _tone_plan["dip_db"] < -0.2:
            moves.append(["tone-dip", round(_tone_plan["dip_db"], 2)])
        if _tone_plan["hi_shelf_db"] > 0.2:
            moves.append(["tone-hi", round(_tone_plan["hi_shelf_db"], 2)])
    # (vocal chop disabled — was cutting the start of the first word)
    ch = [HighpassFilter(cutoff_frequency_hz=t["hpf"])]
    # Chest/body shelf — restores 250-600 Hz weight the mud+box cuts remove.
    # Only on the vocal path, so the ready-made beat is untouched.
    try:
        _body_db = float(t.get("body_db", 1.5))
        if _body_db > 0.1:
            _bf = float(t.get("body_hz", 300.0))
            ch.append(LowShelfFilter(cutoff_frequency_hz=_bf, gain_db=_body_db))
            moves.append(["body %g" % _bf, round(_body_db, 2)])
    except Exception as _be:
        moves.append(["body-error", str(_be)[:80]])
    if st["mud"] > 1.0:
        g = -min(MAX_MUD_CUT, t["mud"], (st["mud"] - 1.0) * 1.1 * 2.0)
        if g < -0.2:
            _f = float(t.get("mud_hz", 380.0)); _q = float(t.get("mud_q", 1.5))
            ch.append(PeakFilter(_f, g, _q)); moves.append(["mud %g" % _f, round(g, 2)])
    if st["box"] > 1.0:
        g = -min(MAX_BOX_CUT, t["box"], (st["box"] - 1.0) * 0.8 * 1.5)
        if g < -0.2:
            _f = float(t.get("box_hz", 600.0)); _q = float(t.get("box_q", 1.0))
            ch.append(PeakFilter(_f, g, _q)); moves.append(["box %g" % _f, round(g, 2)])
    if st["harsh"] > 1.5:
        g = -min(MAX_HARSH_CUT, t["harsh"], (st["harsh"] - 1.5) * 2.0)
        if g < -0.2:
            _f = float(t.get("harsh_hz", 4400.0)); _q = float(t.get("harsh_q", 1.2))
            ch.append(PeakFilter(_f, g, _q)); moves.append(["harsh %g" % _f, round(g, 2)])
    if st["presence"] < -2.5 and t["pres"] > 0:
        # Preset value is the HARD CAP on the boost. Previously the formula
        # could exceed it, which made tuning the preset useless.
        _pres_cap = float(t["pres"])
        g = min(_pres_cap, (-st["presence"] - 2.5) * 1.8 + 0.4)
        if g > 0.2:
            _f = float(t.get("pres_hz", 3000.0)); _q = float(t.get("pres_q", 1.0))
            ch.append(PeakFilter(_f, g, _q)); moves.append(["presence %g" % _f, round(g, 2)])
    # (noise gate disabled — was chopping word tails that feed the delay)
    _thr = float(np.clip(_rms_db(voc) - 1.5, -32.0, -12.0))
    # Compressor moved post-chain (opto LA-2A, opto_comp.py). Record the
    # settings now; actual compression runs after Pedalboard(ch) below.
    _opto_thr = _thr
    _opto_ratio = t["ratio"]
    moves.append(["compress", "opto %s:1 @ %.1f" % (t["ratio"], _thr)])
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
    # --- Clip-gain ride (gated)
    if _NEW["clip_gain"] and role in ("lead", "adlib", "backing"):
        try:
            import clip_gain
            _cg_in = _rms_db(voc)
            voc = clip_gain.clip_gain_ride(voc, sr, window_ms=100.0,
                                           max_gain_db=1.5,
                                           silence_threshold_db=-32.0)
            _cg_out = _rms_db(voc)
            moves.append(["clip-gain", "linked +/-1.5dB  100ms  mean shift %.2f dB" % (_cg_out - _cg_in)])
        except Exception as _cge:
            moves.append(["clip-gain-error", str(_cge)[:80]])

    out = Pedalboard(ch)(voc, sr).astype(np.float32)

    # --- 1176-style FET stage (UREI Rev D topology, feedback, near-instant attack).
    #     Runs BEFORE the LA-2A: FET catches peaks, LA-2A glues the body.
    if _NEW["fet"] and role in ("lead", "adlib", "backing"):
        try:
            import fet_comp
            _fet_rms = _rms_db(out)
            _fet_thr = float(_comp["fet_thr"]) if _comp else float(np.clip(_fet_rms + 10.0, -30.0, -6.0))
            _fet_out, _fet_info = fet_comp.fet_compress(
                out, sr,
                threshold_db=_fet_thr,
                ratio=4.0,
                attack_ms=5.0,
                release_ms=80.0,
                sidechain_hpf_hz=90.0,
                sat_drive=0.10,
            )
            out = _fet_out
            moves.append(["fet", "1176 4:1 @ %.1f  gr %.2f" % (
                _fet_thr, _fet_info.get("max_gr_db", 0.0))])
            moves.append(["fet-model", _fet_info.get("model", "")])
        except Exception as _fe:
            moves.append(["fet-error", str(_fe)[:80]])

    # LA-2A style opto compression — program-dependent, two-stage release.
    # Runs on the chain output so EQ/de-ess shape the signal before
    # compression sees it, matching real vocal-chain signal flow.
    try:
        import dsp_pro
        import opto_comp
        # Adaptive threshold: measure THIS vocal's RMS, set threshold
        # 8 dB above it. Works for every user regardless of recording
        # level — quiet bedroom mic, hot studio take, whatever.
        # 8 dB headroom means compression only hits peaks, not every sample.
        _vocal_rms = _rms_db(out)
        _opto_thr_cal = float(_comp["opto_thr"]) if _comp else float(max(-14.0, _vocal_rms + 8.0))
        moves.append(["opto-thr", round(_opto_thr_cal, 1)])
        _la2a_fn = dsp_pro.la2a_compress if _NEW["la2a_pro"] else opto_comp.opto_compress
        out, _opto_info = _la2a_fn(
            out, sr,
            threshold_db=_opto_thr_cal,
            ratio=2.0,
            attack_ms=10.0,
            release_fast_ms=60.0,
            release_slow_ms=1500.0,
            makeup_db=0.0,
        )
        moves.append(["opto-gr", _opto_info.get("max_gr_db", 0.0)])
    except Exception as _oe:
        moves.append(["opto-error", str(_oe)[:80]])
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
    
    # Conditional low-mid shaping — only fires when the source is genuinely
    # muddy. Voices that aren't muddy keep their body.
    if st.get("mud", 0) > 1.0:
        try:
            out = Pedalboard([
                PeakFilter(cutoff_frequency_hz=320.0, gain_db=-2.5, q=1.1),
                LowShelfFilter(cutoff_frequency_hz=150.0, gain_db=-1.5),
            ])(out, sr).astype(np.float32)
        except Exception:
            pass
        
    out = _saturate(out, sr, drive)
    moves.append(["saturate", round(drive, 2)])

    try:
        # Boost clean high fidelity air gracefully at the top of the chain
        out = Pedalboard([HighShelfFilter(cutoff_frequency_hz=10000.0,
                                          gain_db=min(1.5, float(t["air"])), q=0.7)])(out, sr).astype(np.float32)
    except Exception:
        pass
    moves.append(["air 11k", round(min(1.5, float(t["air"])), 2)])
    out = (out * (10.0 ** (t["gain"] / 20.0))).astype(np.float32)
    moves.append(["role gain", t["gain"]])

    # -1 dBFS true-peak guard on the vocal bus (Claude fix 4b)
    if role == "lead":
        try:
            out = _headroom(out, -1.0).astype(np.float32)
            moves.append(["peak-guard", -1.0])
        except Exception:
            pass

    # Log output vocal crest — same metric detect_effects.py reports for refs
    try:
        _w = int(sr * 0.1)
        _k = out.shape[1] // _w
        if _k > 5:
            _o = np.abs(out[:, :_k*_w]).reshape(out.shape[0], _k, _w)
            _pk = _o.max(axis=(0, 2))
            _rms = np.sqrt((_o ** 2).mean(axis=(0, 2)))
            _m = _rms > 1e-6
            if _m.any():
                _c = float(np.median(20 * np.log10(_pk[_m] / (_rms[_m] + 1e-9))))
                moves.append(["vocal-crest-db", round(_c, 2)])
    except Exception:
        pass

    # --- 3D head-wrap on lead only (stereo out)
    if _NEW["wrap3d"] and role == "lead":
        try:
            import wrap3d
            out = wrap3d.apply_wrap(_mono(out), int(sr), instrumental_rms=-14.0)
            moves.append(["wrap3d", "3d head-wrap (M/S, HRTF, Haas)"])
        except Exception as _we:
            moves.append(["wrap3d-error", str(_we)[:80]])

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
    """Master limiter. Priority order:
       1. numpy sidechain-HPF limiter (bass-preserving, from limiter.py)
       2. numpy lookahead limiter (fallback, also preserves crest)
       3. pedalboard BrickwallLimiter (last resort, clips flat)
    """
    y = None

    # Primary: bass-preserving limiter with sidechain HPF on detector
    try:
        from limiter import Limiter as _NewLimiter
        _lim = _NewLimiter(threshold_db=ceiling_db, release_ms=80.0,
                           lookahead_ms=5.0, sc_hpf_hz=120.0)
        y = _lim.process(x, sr)
    except Exception:
        y = None

    # numpy lookahead limiter (transparent, preserves crest)
    if y is None:
        try:
            y, _ = _lookahead_limiter(x, sr, ceiling_db,
                                      lookahead_ms=5.0, release_ms=80.0)
        except Exception:
            y = None

    # Fallback 2: pedalboard brickwall
    if y is None:
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

    # Safety trim: true peak enforcement
    tp = _true_peak_db(y)
    lim = 10.0 ** (ceiling_db / 20.0)
    if tp > ceiling_db:
        y = (y * (lim / (10.0 ** (tp / 20.0)))).astype(np.float32)
        tp = float(ceiling_db)
    return y, float(tp), True


# ---------- main ----------

def _band_carve(beat, lead, sr):
    """Band-limited sidechain carve: duck only the bands where the vocal
    lives, only while the vocal is active. Flat when the vocal is silent.
    Cheaper and more transparent than full-band STFT ducking."""
    try:
        import numpy as _np
        from pedalboard import Pedalboard as _PB, HighpassFilter as _HPF, LowpassFilter as _LPF
        n = min(beat.shape[1], lead.shape[1])
        if n < 64:
            return beat
        # Vocal activity envelope (15 ms attack, 120 ms release)
        mono = _np.mean(lead[:, :n], axis=0)
        env = _np.abs(mono)
        a = float(_np.exp(-1.0 / max(1.0, sr * 0.015)))
        r = float(_np.exp(-1.0 / max(1.0, sr * 0.120)))
        e = _np.empty_like(env)
        cur = 0.0
        for i in range(env.shape[0]):
            x = env[i]
            cur = x + (a if x > cur else r) * (cur - x)
            e[i] = cur
        ref = float(_np.percentile(e, 90)) + 1e-9
        d = _np.clip(e / ref, 0.0, 1.0).astype(_np.float32)
        out = beat.copy()
        for lo, hi, db in ((250.0, 500.0, 1.0), (1500.0, 4500.0, 2.5), (4500.0, 8000.0, 1.2)):
            band = _PB([_HPF(cutoff_frequency_hz=lo), _LPF(cutoff_frequency_hz=hi)])(beat, sr)
            gain = (10.0 ** (-db * d / 20.0) - 1.0).astype(_np.float32)
            out[:, :n] = out[:, :n] + gain[None, :] * band[:, :n]
        return out.astype(_np.float32)
    except Exception:
        return beat


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
        try:
            rep["reverb_last"] = dict(_REVERB_LAST)
        except Exception:
            rep["reverb_last"] = {}
        try:
            rep["delay_last"] = dict(_DELAY_LAST)
        except Exception:
            rep["delay_last"] = {}
        try:
            rep["parallel_last"] = dict(_PAR_LAST)
            rep["exciter_last"] = dict(_EXC_LAST)
        except Exception:
            pass
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
    bpm, _bpm_conf = detect_tempo(_mono(beat), sr, with_conf=True)
    if _bpm_conf < 0.15:
        bpm = 100.0
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

    # Parallel compression on the summed vocal bus (two-track path)
    if _NEW.get("parallel_ny", False):
        try:
            core = _parallel(core, sr)
        except Exception as _pe:
            _PAR_LAST["error"] = str(_pe)[:200]
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
    try:
        rep["reverb_last"] = dict(_REVERB_LAST)
    except Exception:
        rep["reverb_last"] = {}
    try:
        rep["delay_last"] = dict(_DELAY_LAST)
    except Exception:
        rep["delay_last"] = {}
    try:
        rep["parallel_last"] = dict(_PAR_LAST)
        rep["exciter_last"] = dict(_EXC_LAST)
    except Exception:
        pass

    _DOUBLE_ON = True    # ADT detune copy — widens the vocal (refs sit corr 0.85-0.92)
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
            rep["double_error"] = _DBL.get("error", "")
    else:
        rep["double"] = False
        rep["double_error"] = "side_ids empty"

    ducked_stft, plan, vpres, post = _duck(beat, _dry_voc, freq, st)
    ducked = _band_carve(ducked_stft, _dry_voc, sr)
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

    _w = float(_PRESET.get("width") or 1.0)
    try:
        if mixed.shape[0] >= 2:
            _m = (mixed[0] + mixed[1]) * 0.5
            _s = (mixed[0] - mixed[1]) * 0.5
            _rm = float(np.sqrt(np.mean(_m**2)))
            _rs = float(np.sqrt(np.mean(_s**2)))
            _sm = 20.0 * np.log10(max(1e-9, _rs) / max(1e-9, _rm))
            rep["widen_probe"] = {"width_wanted": _w, "sm_db": round(_sm, 2),
                                  "gate_would_fire": bool(_sm < -14.0)}
    except Exception as _we:
        rep["widen_probe_error"] = str(_we)[:120]
    mixed = _widen(mixed, sr, _w)   # AUDIO PATH UNCHANGED
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
    # polish removed from master mode: a finished mix was already EQ'd
    # by its producer/mastering engineer. Re-applying polish cut -2.97 dB
    # at 2.5-4.5 kHz and -2.5 dB at 5.5-9 kHz on every upload, which made
    # finished beats sound lean and light. Master mode is now transparent:
    # HPF -> width -> loudness -> true-peak limiter.
    try:
        a = _widen(a, sr, WIDEN_MASTER)
        moves.append(["width", WIDEN_MASTER])
    except Exception:
        pass
    rep["master_chain"] = moves
    return _headroom(a, -1.0), rep


# ---------- polish additions ----------

def _parallel(x, sr):
    if _NEW["parallel_ny"]:
        try:
            import parallel_comp
            out = parallel_comp.industry_parallel_compressor(x, sr, blend_amount=0.30)
            _PAR_LAST["ran"] = True
            _PAR_LAST["mode"] = "ny 6:1 8ms hpf120 sub30"
            return out
        except Exception as _e:
            _PAR_LAST["error"] = str(_e)[:200]
            return x
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        crushed = Pedalboard([
            Compressor(threshold_db=-24.0, ratio=6.0, attack_ms=8.0, release_ms=90.0),
            Gain(gain_db=3.0),
        ])(a, int(sr)).astype(np.float32)
        y = (a * 0.70 + crushed * 0.30).astype(np.float32)
        _PAR_LAST["ran"] = True
        return _headroom(y, -1.0).astype(np.float32)
    except Exception as _e:
        _PAR_LAST["error"] = str(_e)[:200]
        return x


def _exciter(x, sr):
    if _NEW["exciter_t1"]:
        try:
            import dsp_tier1
            a = np.asarray(x, dtype=np.float32)
            if a.ndim != 2 or a.shape[1] == 0:
                return x
            y = dsp_tier1.exciter(a, int(sr), drive_db=8.0, blend=0.08)
            _EXC_LAST["ran"] = True
            return _headroom(y, -1.0).astype(np.float32)
        except Exception as _e:
            _EXC_LAST["error"] = str(_e)[:200]
            return x
    try:
        from pedalboard import Pedalboard as _PB, HighpassFilter as _HP, LowpassFilter as _LP, Distortion as _D, Gain as _G
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        air = _PB([_HP(cutoff_frequency_hz=5000.0),
                   _D(drive_db=0.8),
                   _LP(cutoff_frequency_hz=10000.0),
                   _G(gain_db=-9.0)])(a, int(sr)).astype(np.float32)
        y = (a + air * 0.08).astype(np.float32)
        _EXC_LAST["ran"] = True
        return _headroom(y, -1.0).astype(np.float32)
    except Exception as _e:
        _EXC_LAST["error"] = str(_e)[:200]
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
        # Claude's delay only for afrobeats — every other genre uses the original engine delay
        if _PRESET.get("_name", "neutral") != "afrobeats":
            return old
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

_REVERB_LAST = {}
_DELAY_LAST = {}
_PAR_LAST = {}
_EXC_LAST = {}
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
        # Claude's reverb only for afrobeats — other genres use the original engine reverb
        if _PRESET.get("_name", "neutral") != "afrobeats":
            return old
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
            try:
                _REVERB_LAST[kind] = dict(_info) if _info else {}
            except Exception:
                pass
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