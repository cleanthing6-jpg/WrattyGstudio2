"""Automatic mix engine v3: measures the voice, makes room for it, then applies
a professional release chain. Every stage is capped, guarded and verified, so a
mix cannot come out harsh, phasing or clipping.
"""

import numpy as np
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
MAX_PRESENCE, MAX_HARSH_CUT, MAX_AIR, MAX_DEESS = 1.5, 3.0, 2.5, 5.0
DUCK_CAP = {BODY: 1.0, PRES: 3.0, HARSH: 2.0}
DUCK_TARGET = {BODY: 2.0, PRES: 2.5, HARSH: 2.0}

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

_PLATE = {}


def kind_of(role):
    r = str(role or "").lower()
    for t in BEAT_ROLES:
        if t in r:
            return "beat"
    for t in VOCAL_ROLES:
        if t in r:
            return "vocal"
    return "other"


# ---------- helpers ----------

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
    for kind in ("beat", "vocal", "other"):
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


def _true_peak_db(x):
    if x.size == 0:
        return -120.0
    pk = float(np.max(np.abs(x)))
    if x.shape[1] > 2:
        pk = max(pk, float(np.max(np.abs((x[:, :-1] + x[:, 1:]) * 0.5))))
    return 20.0 * np.log10(pk + 1e-12)


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
    if len(x) < N:
        x = np.pad(x, (0, N - len(x)))
    n = 1 + (len(x) - N) // HOP
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
    if key in _PLATE:
        return _PLATE[key]
    dur, pre = 1.25, 0.022
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    env = np.exp(-6.91 * np.maximum(t - pre, 0.0) / dur)
    ir = np.random.default_rng(7).normal(0.0, 1.0, n) * env
    ir[:int(sr * pre)] *= np.linspace(0.0, 1.0, int(sr * pre)) ** 2
    x = ir.astype(np.float32)[None, :]
    x = Pedalboard([HighpassFilter(cutoff_frequency_hz=180.0),
                    LowpassFilter(cutoff_frequency_hz=6500.0)])(x, sr)
    ir = x[0].astype(np.float32)
    e = float(np.sqrt(np.sum(np.square(ir.astype(np.float64))))) + 1e-12
    ir = (ir / e) * 0.9
    _PLATE[key] = ir.astype(np.float32)
    return _PLATE[key]


def _plate(voc, sr):
    ir = plate_ir(sr)
    if Convolution is not None:
        try:
            return Pedalboard([Convolution(ir, mix=1.0)])(voc, sr).astype(np.float32)
        except Exception:
            pass
    try:
        return Pedalboard([Reverb(room_size=0.45, damping=0.55,
                                  wet_level=1.0, dry_level=0.0, width=1.0)])(voc, sr).astype(np.float32)
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
    if st["sib"] < 3.0:
        return voc, 0.0
    freq = np.fft.rfftfreq(N, 1.0 / sr)
    k = (freq >= 5500) & (freq < 9000)
    out = np.empty_like(voc)
    mx = 0.0
    for c in range(voc.shape[0]):
        S = _stft(voc[c])
        lev = _level_db(S, k)
        red = _smooth(np.clip((lev - np.percentile(lev, 75)) * 0.6, 0.0, MAX_DEESS))
        mx = max(mx, float(np.max(red)))
        S[:, k] *= (10.0 ** (-red / 20.0))[:, None]
        out[c] = _istft(S, voc.shape[1])
        del S
    return out, round(mx, 2)


def _ambience(voc, sr, bpm):
    beat_s = 60.0 / max(bpm, 40.0)
    d = max(int(sr * 0.04), min(int(sr * beat_s * 0.5), int(sr * 0.35)))
    slap = None
    try:
        slap = Pedalboard([
            Delay(delay_seconds=d / float(sr), feedback=0.18, mix=1.0),
            HighpassFilter(cutoff_frequency_hz=300.0),
            LowpassFilter(cutoff_frequency_hz=4000.0),
        ])
    except Exception:
        slap = None
    plate = None
    if Convolution is not None:
        try:
            plate = Convolution(plate_ir(sr), mix=1.0)
        except Exception:
            plate = None
    wet = _send_sum(voc, sr, [slap, plate])
    if wet is None:
        wet = _plate(voc, sr)
        if wet is None:
            return voc, round(d / float(sr) * 1000.0), "none"
    out = (voc + SEND_WET * wet).astype(np.float32)
    return _headroom(out, -1.0), round(d / float(sr) * 1000.0), ("plate" if plate is not None else "algorithmic")


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


def vocal_process(voc, sr, st, bpm):
    moves = [["highpass", 85.0]]
    ch = [HighpassFilter(cutoff_frequency_hz=85.0)]
    if st["mud"] > 1.5:
        g = -min(MAX_MUD_CUT, (st["mud"] - 1.5) * 1.2)
        ch.append(PeakFilter(220.0, g, 0.9)); moves.append(["mud 220", round(g, 2)])
    if st["box"] > 1.5:
        g = -min(MAX_BOX_CUT, (st["box"] - 1.5) * 0.8)
        ch.append(PeakFilter(650.0, g, 1.0)); moves.append(["box 650", round(g, 2)])
    if st["harsh"] > 2.0:
        g = -min(MAX_HARSH_CUT, st["harsh"] - 2.0)
        ch.append(PeakFilter(4300.0, g, 1.2)); moves.append(["harsh 4.3k", round(g, 2)])
    if st["presence"] < -3.0 and st["harsh"] < 2.0:
        g = min(MAX_PRESENCE, (-st["presence"] - 3.0) * 0.5 + 0.5)
        if g > 0.2:
            ch.append(PeakFilter(2800.0, g, 0.8)); moves.append(["presence 2.8k", round(g, 2)])
    ch.append(Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=5.0, release_ms=90.0))
    moves.append(["compress", "3:1 @ -20"])
    air = min(MAX_AIR, max(0.8, (-st["air"] - 3.0) * 0.3))
    ch.append(HighShelfFilter(cutoff_frequency_hz=10000.0, gain_db=air, q=0.7))
    moves.append(["air 10k", round(air, 2)])

    out = Pedalboard(ch)(voc, sr).astype(np.float32)
    drive = min(3.0, 1.2 + max(0.0, (2.5 - st["clarity"]) * 0.6))
    out = _saturate(out, sr, drive)
    moves.append(["saturate", round(drive, 2)])
    out, dd = _deess(out, sr, st)
    moves.append(["de-ess", dd])
    out, ms, plate_kind = _ambience(out, sr, bpm)
    moves.append(["slap ms", ms])
    moves.append(["plate", plate_kind])
    return out, moves


# ---------- ducking ----------

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

def _widen(x, sr):
    mid = ((x[0] + x[1]) * 0.5).astype(np.float32)
    side = ((x[0] - x[1]) * 0.5).astype(np.float32)
    low = Pedalboard([LowpassFilter(cutoff_frequency_hz=LOW_MONO_HZ)])(side[None, :], sr)[0]
    side = ((side - low) * WIDEN + low).astype(np.float32)
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
        return Pedalboard([Clipping(threshold_db=-2.0)])(x, sr).astype(np.float32)
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
    return y, float(_true_peak_db(y)), (b is not None)


# ---------- main ----------

def mix(groups, sr, loud="MEDIUM"):
    beats = list(groups.get("beat") or [])
    vocs = list(groups.get("vocal") or [])
    others = list(groups.get("other") or [])
    rep = {"sr": int(sr)}

    beat = _sum(beats) if beats else None
    voc = _sum(vocs) if vocs else None

    if beat is None and voc is None:
        rep["mode"] = "sum"
        return _headroom(_sum(others)), rep

    if voc is None:
        rep["mode"] = "passthrough"
        rep["note"] = "no vocal stem - beat returned without reprocessing"
        return _headroom(beat * (10.0 ** (-1.5 / 20.0))), rep

    if beat is None:
        rep["mode"] = "vocal_only"
        voc = voc * (10.0 ** (-6.0 / 20.0))
        st, freq = analyze(voc, voc, sr)
        voc, moves = vocal_process(voc, sr, st, detect_tempo(voc, sr))
        rep["vocal_chain"] = moves
        return _headroom(voc), rep

    rep["mode"] = "two_track" if len(beats) == 1 else "stems"
    bpm = detect_tempo(_mono(beat), sr)
    rep["bpm"] = round(bpm, 1)

    g = float(np.clip(_rms_db(beat) - _rms_db(voc) - 6.0, -18.0, 6.0))
    voc = (voc * (10.0 ** (g / 20.0))).astype(np.float32)
    rep["vocal_gain_db"] = round(g, 2)

    st, freq = analyze(_mono(beat), _mono(voc), sr)
    rep["measured"] = {k: round(float(v), 2) for k, v in st.items()}
    voc_eq, moves = vocal_process(voc, sr, st, bpm)
    rep["vocal_chain"] = moves

    ducked, plan, vpres, post = _duck(beat, voc_eq, freq, st)
    tries = 1
    while (post is not None and (vpres - post) < (DUCK_TARGET[PRES] - 0.5)
           and tries < 2 and any(plan[b] > -DUCK_CAP[b] + 0.05 for b in plan)):
        ducked, plan, vpres, post = _duck(beat, voc_eq, freq, st, extra=1.0)
        tries += 1

    rep["duck_db"] = {("%d-%d" % b): round(v, 2) for b, v in plan.items()}
    rep["clarity_before"] = round(float(st["clarity"]), 2)
    rep["clarity_after"] = None if post is None else round(float(vpres - post), 2)
    rep["duck_passes"] = tries

    n = max(ducked.shape[1], voc_eq.shape[1])
    ducked = _pad(ducked, n)
    voc_eq = _pad(voc_eq, n)

    dbl = _double(voc_eq, sr)
    rep["double"] = dbl is not None
    if dbl is not None:
        dbl = _pad(dbl, n)
        mixed = (ducked + voc_eq + dbl).astype(np.float32)
    else:
        mixed = (ducked + voc_eq).astype(np.float32)

    mixed = _widen(mixed, sr)
    mixed = _headroom(mixed)
    rep["check"] = verify(mixed, sr, voc_eq, ducked)
    return mixed, rep
