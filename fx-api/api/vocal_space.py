
"""
vocal_space.py  -  adaptive "pro touch" space for vocals: reverb + delay + early reflections + tiny room (+ optional beat room)

WHAT IT DOES (and why it sounds dry, clear and close)
  * Returns an ADDITIVE wet bus. The dry vocal and the beat are never modified:   mix = beat + vocal + bus
  * Sends are cleaned first: high-passed (no boom / plosives into the reverb) and de-essed (no sibilance smeared into the tail).
  * Pre-delay locked to the song tempo keeps the dry consonant in front of the reverb onset.
  * The wet bus is DUCKED by the dry vocal (sidechain): the space is quiet while words are sung and blooms in the gaps.
    That is the "dry, clear, no smearing, afloat in the mix" sound. Distance is controlled by the direct-to-reverb ratio,
    so the vocal stays close to the ear.
  * Delay is tempo-synced, filtered darker on every repeat, ping-pong wide, ducked, and by default only "thrown" off the
    ends of phrases, so repeats never land on top of the next word.
  * Early reflections (5 taps per side, 7-35 ms) + a 0.22 s room give the "in the room with the music" feel.
  * Optional beat room: a very quiet short room fed by the beat's top end puts vocal and beat in the same space.
    It is added on its own bus; the beat itself is untouched (report shows the measured change).

ADAPTIVE (per song, per user - nothing fixed):
  vocal density, phrase gaps, brightness, sibilance, tempo and genre set: reverb decay, pre-delay, send filters, wet level,
  duck depth/release, delay note value, feedback, throw-vs-full mode, de-ess amount.

USAGE
    bus, rep = vocal_space.build(lead_dry, sr, bpm=99.4, genre="afrobeats", role="lead", beat=beat_stereo, space=0.5)
    mix = beat + lead_dry + bus
    # backing vocals: duck their space from the LEAD so it never competes with it
    bus_b, rep_b = vocal_space.build(backing_dry, sr, bpm=99.4, role="backing", duck_from=lead_dry)

  space: 0..1 user slider (0.5 = neutral, +-4 dB of wet level). Genre values are engineering starting points, not measured.
"""
import time
import numpy as np
import scipy.signal as sg
from scipy.ndimage import uniform_filter1d

__all__ = ["build", "GENRE_SPACE"]

GENRE_SPACE = {
    "afrobeats": dict(rt60=0.95, wet=-19.0, dly=-20.0, duck=8.0, early=-24.0, room=-27.0, fb=0.30, style="note"),
    "amapiano":  dict(rt60=1.20, wet=-18.0, dly=-21.0, duck=8.0, early=-24.0, room=-26.0, fb=0.32, style="note"),
    "hiphop":    dict(rt60=0.70, wet=-21.0, dly=-19.0, duck=10.0, early=-24.0, room=-28.0, fb=0.18, style="slap"),
    "rnb":       dict(rt60=1.30, wet=-17.0, dly=-20.0, duck=8.0, early=-23.0, room=-26.0, fb=0.34, style="note"),
    "pop":       dict(rt60=1.00, wet=-19.0, dly=-20.0, duck=8.0, early=-24.0, room=-27.0, fb=0.28, style="note"),
    "dancehall": dict(rt60=0.85, wet=-20.0, dly=-17.0, duck=9.0, early=-25.0, room=-28.0, fb=0.36, style="note"),
    "gospel":    dict(rt60=1.50, wet=-17.0, dly=-23.0, duck=7.0, early=-23.0, room=-25.0, fb=0.26, style="note"),
    "other":     dict(rt60=0.95, wet=-19.5, dly=-20.5, duck=8.0, early=-24.0, room=-27.0, fb=0.28, style="note"),
}
_ALIAS = {"afro": "afrobeats", "afrobeat": "afrobeats", "afropop": "afrobeats", "rap": "hiphop", "trap": "hiphop",
          "drill": "hiphop", "rb": "rnb", "randb": "rnb", "piano": "amapiano"}


def _genre(g):
    k = "".join(c for c in str(g or "other").lower() if c.isalnum())
    k = _ALIAS.get(k, k)
    return k if k in GENRE_SPACE else "other"


def _bp(lo, hi, sr, order=2):
    return sg.butter(order, [lo, min(hi, sr / 2 * 0.95)], btype="band", fs=sr, output="sos")


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12)


def _db(v):
    return 20.0 * np.log10(max(float(v), 1e-12))


def _analyse(m, sr):
    hop = int(0.010 * sr)
    n = len(m) // hop
    fr = np.sqrt(np.mean(m[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    lvl = 20 * np.log10(fr)
    live = lvl[lvl > -70]
    if len(live) < 20:
        return None
    thr = max(np.percentile(live, 90) - 22.0, -60.0)
    act = lvl > thr
    idx = np.flatnonzero(act)
    phr = []
    if len(idx):
        s = p = idx[0]
        for i in idx[1:]:
            if (i - p) * 0.010 > 0.25:
                phr.append((s * 0.010, (p + 1) * 0.010)); s = i
            p = i
        phr.append((s * 0.010, (p + 1) * 0.010))
    phr = [q for q in phr if q[1] - q[0] >= 0.4]
    gaps = [phr[i + 1][0] - phr[i][1] for i in range(len(phr) - 1)]
    sib = _rms(sg.sosfilt(_bp(5000, 9500, sr), m)[: n * hop].reshape(n, hop)[act])
    mid = _rms(sg.sosfilt(_bp(1000, 4000, sr), m)[: n * hop].reshape(n, hop)[act])
    top = _rms(sg.sosfilt(_bp(4000, 10000, sr), m)[: n * hop].reshape(n, hop)[act])
    body = _rms(sg.sosfilt(_bp(300, 4000, sr), m)[: n * hop].reshape(n, hop)[act])
    return {"active_ratio": float(act.mean()), "phrases": phr, "median_gap_s": float(np.median(gaps)) if gaps else 0.8,
            "sib_db": _db(sib / mid), "bright_db": _db(top / body), "thr_db": float(thr)}


def _activity(m, sr, thr_db, hop_s=0.002):
    hop = max(1, int(hop_s * sr))
    p = uniform_filter1d(m.astype(np.float64) ** 2, size=int(0.008 * sr), mode="nearest")[::hop]
    lvl = 10 * np.log10(p + 1e-12)
    return np.clip((lvl - (thr_db - 3.0)) / 6.0, 0.0, 1.0), hop


def _smooth(x, hop_s, atk_s, rel_s):
    ka, kr = np.exp(-hop_s / atk_s), np.exp(-hop_s / rel_s)
    y = np.empty_like(x)
    s = 0.0
    for i, v in enumerate(x):
        k = ka if v > s else kr
        s = k * s + (1.0 - k) * v
        y[i] = s
    return y


def _duck_curve(act, hop, n, hop_s, duck_db, atk_ms, rel_ms):
    a = _smooth(act, hop_s, atk_ms / 1000.0, rel_ms / 1000.0)
    g = 10 ** (-duck_db * a / 20.0)
    return np.interp(np.arange(n), (np.arange(len(g)) + 0.5) * hop, g).astype(np.float32)


def _clean_send(m, sr, hpf, deess_db):
    x = sg.sosfilt(sg.butter(2, hpf, "high", fs=sr, output="sos"), m)
    sb = sg.sosfiltfilt(_bp(5000, 9500, sr), x)
    env = uniform_filter1d(np.abs(sb), size=max(1, int(0.003 * sr)), mode="nearest")
    ref = np.median(env[env > np.percentile(env, 60)]) if np.any(env > np.percentile(env, 60)) else np.median(env)
    g = np.clip((1.5 * ref) / (env + 1e-12), 10 ** (-deess_db / 20.0), 1.0)
    g = uniform_filter1d(g, size=max(1, int(0.002 * sr)), mode="nearest")
    return x - (1.0 - g) * sb


def _plate_ir(sr, rt60, pre_ms, hpf, lpf, seed):
    n = int(sr * (rt60 * 1.1 + pre_ms / 1000.0))
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    bands = [(150, 700, 1.15), (700, 3000, 1.0), (3000, max(lpf, 4500), 0.55)]
    ir = np.zeros((2, n))
    for ch in range(2):
        noise = rng.standard_normal(n)
        for lo, hi, mult in bands:
            ir[ch] += sg.sosfilt(_bp(lo, hi, sr), noise) * np.exp(-6.9078 * t / (rt60 * mult))
    ir *= (1.0 - np.exp(-t / 0.012))
    pre = int(pre_ms / 1000.0 * sr)
    ir = np.concatenate([np.zeros((2, pre)), ir[:, : n - pre]], axis=1)
    ir = sg.sosfilt(sg.butter(2, hpf, "high", fs=sr, output="sos"), ir, axis=-1)
    ir = sg.sosfilt(sg.butter(2, lpf, "low", fs=sr, output="sos"), ir, axis=-1)
    return ir / (np.sqrt((ir ** 2).sum(axis=1, keepdims=True)) + 1e-12)


def _early_ir(sr):
    taps = {0: [(7.0, .9), (11.5, -.7), (17.0, .6), (23.5, -.45), (31.0, .35)],
            1: [(9.0, .85), (14.0, -.65), (20.5, .55), (27.0, -.4), (35.0, .3)]}
    ir = np.zeros((2, int(0.045 * sr)))
    for ch, ts in taps.items():
        for ms, a in ts:
            ir[ch, int(ms / 1000.0 * sr)] += a
    ir = sg.sosfilt(sg.butter(2, 250, "high", fs=sr, output="sos"), ir, axis=-1)
    ir = sg.sosfilt(sg.butter(2, 7000, "low", fs=sr, output="sos"), ir, axis=-1)
    return ir / (np.sqrt((ir ** 2).sum(axis=1, keepdims=True)) + 1e-12)


def _conv(send, ir):
    return sg.oaconvolve(send.astype(np.float32)[None, :], ir.astype(np.float32), axes=-1)[:, : len(send)]


def _delay(send, sr, d_s, fb, hpf, lpf, width):
    n, d = len(send), int(d_s * sr)
    lp = sg.butter(1, lpf, "low", fs=sr, output="sos")
    e = np.concatenate([np.zeros(d), sg.sosfilt(sg.butter(2, hpf, "high", fs=sr, output="sos"), send)])[:n]
    out = np.zeros((2, n), np.float32)
    amp, k = 1.0, 0
    while amp > 0.01 and k < 8 and d * (k + 1) < n:
        e = sg.sosfilt(lp, e)
        side = k % 2
        out[side] += (amp * e).astype(np.float32)
        out[1 - side] += (amp * e * (1.0 - width)).astype(np.float32)
        e = np.concatenate([np.zeros(d), e])[:n]
        amp *= fb ** 1.0
        k += 1
    return out


def _throw_gate(phr, n, sr, tail_s):
    g = np.zeros(n, np.float32)
    for i, (s, e) in enumerate(phr):
        gap = (phr[i + 1][0] - e) if i + 1 < len(phr) else 9.0
        if gap >= 0.30:
            a, b = int(max(s, e - tail_s) * sr), min(n, int((e + 0.06) * sr))
            g[a:b] = 1.0
    return uniform_filter1d(g, size=max(1, int(0.015 * sr)), mode="nearest")


def build(vocal, sr, bpm=None, genre="afrobeats", role="lead", beat=None, space=0.5, duck_from=None,
          delay=True, glue_db=-30.0, seed=7):
    t0 = time.time()
    v = np.asarray(vocal, dtype=np.float64)
    m = v if v.ndim == 1 else v.mean(axis=0)
    n = len(m)
    zeros = np.zeros((2, n), np.float32)
    an = _analyse(m, sr)
    if an is None:
        return zeros, {"skipped": "vocal silent / too short"}
    gcfg = dict(GENRE_SPACE[_genre(genre)])
    lead = role != "backing"
    bpm = float(bpm) if bpm else 95.0
    beat_s = 60.0 / bpm
    dens = float(np.clip((an["active_ratio"] - 0.30) / 0.45, 0.0, 1.0))
    user = (float(np.clip(space, 0, 1)) - 0.5) * 8.0

    rt60 = float(np.clip(gcfg["rt60"] * (1.18 - 0.55 * dens) * (1.0 if lead else 1.15), 0.45, 1.8))
    pre_ms = float(np.clip(60000.0 / bpm / 16.0, 18.0, 60.0) + (0 if lead else 8.0))
    hpf = 380.0 if lead else 300.0
    lpf = float(np.interp(an["bright_db"], [-18.0, -6.0], [8000.0, 5200.0]) - (0 if lead else 900.0))
    deess = float(np.interp(an["sib_db"], [-18.0, -8.0], [3.0, 9.0]))
    wet_db = gcfg["wet"] + 2.0 * (1.0 - dens) - 2.5 * dens + user + (3.0 if not lead else 0.0)
    duck_db = gcfg["duck"] + 4.0 * dens
    rel_ms = float(np.clip(60000.0 / bpm / 4.0, 80.0, 260.0))

    key = m if duck_from is None else (np.asarray(duck_from, np.float64).mean(axis=0) if np.ndim(duck_from) == 2 else np.asarray(duck_from, np.float64))
    key = key[:n] if len(key) >= n else np.pad(key, (0, n - len(key)))
    kan = an if duck_from is None else (_analyse(key, sr) or an)
    act, hop = _activity(key, sr, kan["thr_db"])
    hop_s = hop / sr
    duck_r = _duck_curve(act, hop, n, hop_s, duck_db, 4.0, rel_ms)

    send = _clean_send(m, sr, hpf, deess)
    d_rms = _rms(m)
    bus = np.zeros((2, n), np.float32)
    lv, parts = {}, {}

    def add(name, wet, rel_db, duck=None):
        if duck is not None:
            wet = wet * duck[None, :]
        r = _rms(wet)
        if r < 1e-9:
            return
        wet = wet * (d_rms * 10 ** (rel_db / 20.0) / r)
        parts[name] = wet
        lv[name] = round(_db(_rms(wet) / d_rms), 1)

    add("plate", _conv(send, _plate_ir(sr, rt60, pre_ms, hpf, lpf, seed)), wet_db, duck_r)
    add("early", _conv(send, _early_ir(sr)), gcfg["early"] + user * 0.5)
    add("room", _conv(send, _plate_ir(sr, 0.22, 0.0, 200.0, 6500.0, seed + 1)), gcfg["room"] + user * 0.5)

    dly_info = None
    if delay and lead:
        if gcfg["style"] == "slap":
            d_s, note = float(np.clip(beat_s * 0.25, 0.08, 0.16)), "1/16 slap"
        else:
            opts = [(1.0, "1/4"), (0.75, "dotted 1/8"), (0.5, "1/8")]
            lim = max(0.9 * an["median_gap_s"], 0.25)
            pick = next(((f, nm) for f, nm in opts if 0.18 <= beat_s * f <= min(0.75, lim)), (0.5, "1/8"))
            d_s, note = float(np.clip(beat_s * pick[0], 0.18, 0.75)), pick[1]
        fb = float(np.clip(gcfg["fb"] + 0.10 * (1.0 - dens), 0.12, 0.45))
        mode = "throw" if dens > 0.35 else "full"
        dsend = send * (_throw_gate(an["phrases"], n, sr, float(np.clip(beat_s * 0.75, 0.25, 0.5))) if mode == "throw" else 1.0)
        d_duck = _duck_curve(act, hop, n, hop_s, 6.0 + 3.0 * dens, 4.0, rel_ms)
        add("delay", _delay(dsend, sr, d_s, fb, 420.0, 4800.0, 0.8), gcfg["dly"] + user + (2.0 if mode == "throw" else 0.0), d_duck)
        dly_info = {"ms": round(d_s * 1000, 1), "note": note, "feedback": round(fb, 2), "mode": mode}

    for p in parts.values():
        bus += p.astype(np.float32)

    glue = None
    if beat is not None and glue_db is not None and lead:
        b = np.asarray(beat, np.float64)
        bm = b.mean(axis=0) if b.ndim == 2 else b
        bm = bm[:n] if len(bm) >= n else np.pad(bm, (0, n - len(bm)))
        top = sg.sosfiltfilt(_bp(1800, 9000, sr), bm)
        w = _conv(top, _plate_ir(sr, 0.38, 0.0, 1500.0, 9000.0, seed + 2))
        w = w * (_rms(top) * 10 ** (glue_db / 20.0) / _rms(w))
        bus += w.astype(np.float32)
        glue = {"level_db_vs_beat_top": glue_db, "beat_top_change_db": round(_db(_rms(top + w.mean(axis=0)) / _rms(top)), 2)}

    act_mask = np.interp(np.arange(n), (np.arange(len(act)) + 0.5) * hop, act) > 0.5
    plate = parts.get("plate")
    duck_meas = None
    if plate is not None and act_mask.any() and (~act_mask).any():
        duck_meas = round(_db(_rms(plate[:, act_mask]) / _rms(plate[:, ~act_mask])), 1)
    return bus, {
        "analysis": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in an.items() if k != "phrases"} | {"phrases": len(an["phrases"]), "density": round(dens, 2)},
        "genre": _genre(genre), "role": role, "bpm": bpm, "space": space,
        "plate": {"rt60_s": round(rt60, 2), "predelay_ms": round(pre_ms, 1), "hpf": hpf, "lpf": round(lpf), "deess_db": round(deess, 1),
                  "duck_db": round(duck_db, 1), "duck_release_ms": round(rel_ms), "duck_ducked_vs_open_db": duck_meas},
        "delay": dly_info, "beat_glue": glue, "levels_vs_dry_db": lv, "seconds": round(time.time() - t0, 1)}
