"""
vocal_space.py  -  adaptive "pro touch" space for vocals: reverb + delay + early reflections + tiny room (+ optional beat room)
"""
import time
import numpy as np
import scipy.signal as sg
from scipy.ndimage import uniform_filter1d

__all__ = ["build", "GENRE_SPACE"]

GENRE_SPACE = {
    "afrobeats": dict(rt60=0.95, wet=-8.0, dly=-17.0, duck=8.0, early=-24.0, room=-27.0, fb=0.30, style="note"),
    "amapiano":  dict(rt60=1.20, wet=-7.0, dly=-18.0, duck=8.0, early=-24.0, room=-26.0, fb=0.32, style="note"),
    "hiphop":    dict(rt60=0.70, wet=-11.0, dly=-16.0, duck=10.0, early=-24.0, room=-28.0, fb=0.18, style="slap"),
    "rnb":       dict(rt60=1.30, wet=-6.0, dly=-17.0, duck=8.0, early=-23.0, room=-26.0, fb=0.34, style="note"),
    "pop":       dict(rt60=1.00, wet=-8.5, dly=-17.0, duck=8.0, early=-24.0, room=-27.0, fb=0.28, style="note"),
    "dancehall": dict(rt60=0.85, wet=-9.0, dly=-14.0, duck=9.0, early=-25.0, room=-28.0, fb=0.36, style="note"),
    "gospel":    dict(rt60=1.50, wet=-6.0, dly=-20.0, duck=7.0, early=-23.0, room=-25.0, fb=0.26, style="note"),
    "other":     dict(rt60=0.95, wet=-8.5, dly=-17.5, duck=8.0, early=-24.0, room=-27.0, fb=0.28, style="note"),
}
_ALIAS = {"afro": "afrobeats", "afrobeat": "afrobeats", "afropop": "afrobeats", "rap": "hiphop", "trap": "hiphop", "drill": "hiphop", "rb": "rnb", "randb": "rnb", "piano": "amapiano"}

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
    return {"active_ratio": float(act.mean()), "phrases": phr, "median_gap_s": float(np.median(gaps)) if gaps else 0.8, "sib_db": _db(sib / mid), "bright_db": _db(top / body), "thr_db": float(thr)}

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
    taps = {0: [(7.0, .9), (11.5, -.7), (17.0, .6), (23.5, -.45), (31.0, .35)], 1: [(9.0, .85), (14.0, -.65), (20.5, .55), (27.0, -.4), (35.0, .3)]}
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

def _syl_env(m, sr):
    hop = int(0.004 * sr)
    x = sg.sosfiltfilt(_bp(250, 3000, sr), m)
    p = uniform_filter1d(x ** 2, size=int(0.015 * sr), mode="nearest")[::hop]
    e = 10 * np.log10(p + 1e-12)
    return uniform_filter1d(e, size=5, mode="nearest"), hop / sr

def _fragments(m, sr, phrases, n_syl=None, words=None, min_len=0.25, max_len=1.1):
    force = n_syl is not None
    if force:
        min_len = 0.12
    n_pref = 2 if n_syl is None else int(n_syl)
    env, hs = _syl_env(m, sr)
    pk, _ = sg.find_peaks(env, prominence=5.0, distance=max(1, int(0.11 / hs)))
    out = []
    for i, (s0, e0) in enumerate(phrases):
        nxt = phrases[i + 1][0] if i + 1 < len(phrases) else None
        if nxt is not None and nxt - e0 < 0.30:
            continue
        start, how = None, "syllables"
        if words:
            ws = [w for w in words if s0 - 0.05 <= w[0] < e0]
            if ws:
                start, how = max(ws[-1][0], e0 - max_len), "word timestamps"
        if start is None:
            p = pk[(pk * hs >= s0) & (pk * hs <= e0)]
            best = None
            for k in range(1, min(4, len(p)) + 1):
                if force and k != n_pref:
                    continue
                if k < len(p):
                    a, b = p[-k - 1], p[-k]
                    v = a + int(np.argmin(env[a:b + 1]))
                    rise = np.flatnonzero(env[v:b + 1] >= env[v] + 6.0)
                    cut = max(v * hs, (v + (int(rise[0]) if len(rise) else 0)) * hs - 0.02)
                    depth = min(env[a], env[b]) - env[v]
                else:
                    cut, depth = s0, 0.0
                if not (min_len <= e0 - cut <= max_len):
                    continue
                score = depth - 1.5 * abs(k - n_pref)
                if best is None or score > best[0]:
                    best = (score, cut, k)
            start, how = (best[1], f"last {best[2]} syllables") if best else (max(s0, e0 - 0.5), "fallback 0.5 s")
        out.append({"start": float(start), "end": float(e0), "next": nxt, "how": how})
    return out

def _fragment_echoes(send, sr, frags, grid_s, repeats, decay_db, lpf0, width):
    n = len(send)
    out = np.zeros((2, n), np.float32)
    sched = []
    for f in frags:
        a, b = int(f["start"] * sr), min(n, int((f["end"] + 0.03) * sr))
        seg = send[a:b].copy()
        if len(seg) < int(0.05 * sr):
            continue
        fi, fo = min(int(0.006 * sr), len(seg) // 4), min(int(0.025 * sr), len(seg) // 3)
        seg[:fi] *= np.linspace(0.0, 1.0, fi)
        seg[-fo:] *= np.linspace(1.0, 0.0, fo)
        L = len(seg) / sr
        step = max(1, int(np.ceil((L + 0.03) / grid_s))) * grid_s
        for k in range(1, repeats + 1):
            st = f["start"] + k * step
            if f["next"] is not None and st >= f["next"] - 0.02:
                break
            e = sg.sosfilt(sg.butter(1, max(2200.0, lpf0 - (k - 1) * 900.0), "low", fs=sr, output="sos"), seg) * 10 ** (-decay_db * (k - 1) / 20.0)
            if f["next"] is not None and st + len(e) / sr > f["next"] - 0.02:
                e = e[: max(0, int((f["next"] - 0.02 - st) * sr))]
                if len(e) > 64:
                    e[-int(0.015 * sr):] *= np.linspace(1.0, 0.0, min(len(e), int(0.015 * sr)))
            i0 = int(st * sr)
            i1 = min(n, i0 + len(e))
            if i1 <= i0:
                continue
            side = (k - 1) % 2
            out[side, i0:i1] += e[: i1 - i0].astype(np.float32)
            out[1 - side, i0:i1] += (e[: i1 - i0] * (1.0 - width)).astype(np.float32)
            sched.append((round(f["start"], 2), k, round(st, 2)))
    return out, sched

def build(vocal, sr, bpm=None, genre="afrobeats", role="lead", beat=None, space=0.5, duck_from=None, delay=True, glue_db=-30.0, seed=7, return_parts=False, delay_mode=None, tail_syllables=None, words=None, echo_repeats=3):
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
    lv_avg = {}

    def add(name, wet, rel_db, duck=None, ref=None):
        r = _rms(ref if ref is not None else wet)
        if r < 1e-9:
            return
        wet = wet * (d_rms * 10 ** (rel_db / 20.0) / r)
        if duck is not None:
            wet = wet * duck[None, :]
        parts[name] = wet
        lv[name] = float(round(rel_db, 1))
        lv_avg[name] = float(round(_db(_rms(wet) / d_rms), 1))

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
        mode = delay_mode or ("throw" if gcfg["style"] == "slap" and dens > 0.35 else "full" if gcfg["style"] == "slap" else "fragment")
        d_duck = _duck_curve(act, hop, n, hop_s, 6.0 + 3.0 * dens, 4.0, rel_ms)
        
        if mode == "fragment":
            frags = _fragments(m, sr, an["phrases"], tail_syllables, words, max_len=float(min(1.1, beat_s * 2.0)))
            grid = float(np.clip(beat_s * 0.5, 0.18, 0.5))
            reps = int(echo_repeats if dens < 0.8 else min(echo_repeats, 2))
            wet, sched = _fragment_echoes(send, sr, frags, grid, reps, 6.0, 4800.0, 0.8)
            echo_db = gcfg["dly"] + 6.0 + user
            wet = wet * (10 ** (echo_db / 20.0)) * d_duck[None, :]
            parts["delay"] = wet
            lv["delay"] = float(round(echo_db, 1)); lv_avg["delay"] = float(round(_db(_rms(wet) / d_rms), 1))
            dly_info = {"mode": "fragment (last word, answered on the 1/8 grid)", "grid_ms": round(grid * 1000, 1), "repeats": reps, "decay_db_per_repeat": 6.0, "fragments": [{"from_s": round(f["start"], 2), "to_s": round(f["end"], 2), "found_by": f["how"]} for f in frags[:6]], "echo_schedule_first": sched[:6]}
        else:
            dsend = send * (_throw_gate(an["phrases"], n, sr, float(np.clip(beat_s * 0.75, 0.25, 0.5))) if mode == "throw" else 1.0)
            add("delay", _delay(dsend, sr, d_s, fb, 420.0, 4800.0, 0.8), gcfg["dly"] + user, d_duck, ref=_delay(send, sr, d_s, fb, 420.0, 4800.0, 0.8))
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
    duck_meas = None
    if act_mask.any() and (~act_mask).any():
        duck_meas = {"while_singing_db": round(-_db(float(duck_r[act_mask].mean())), 1), "in_gaps_db": round(-_db(float(duck_r[~act_mask].mean())), 1)}
    
    rep = {
        "analysis": dict({k: (round(v, 2) if isinstance(v, float) else v) for k, v in an.items() if k != "phrases"}, phrases=len(an["phrases"]), density=round(dens, 2)),
        "genre": _genre(genre), "role": role, "bpm": bpm, "space": space,
        "plate": {"rt60_s": round(rt60, 2), "predelay_ms": round(pre_ms, 1), "hpf": hpf, "lpf": round(lpf), "deess_db": round(deess, 1), "duck_db": round(duck_db, 1), "duck_release_ms": round(rel_ms), "duck_applied": duck_meas},
        "delay": dly_info, "beat_glue": glue, "open_levels_vs_dry_db": lv, "average_after_duck_db": lv_avg, "seconds": round(time.time() - t0, 1)}
    return (bus, rep, parts) if return_parts else (bus, rep)
