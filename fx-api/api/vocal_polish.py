"""
vocal_polish.py  -  adaptive "expensive" polish that keeps the vocal clear (no smearing, no pumping)
"""
import os, time, shutil, tempfile, subprocess
import numpy as np
import scipy.signal as sg
import scipy.io.wavfile as wf
from scipy.ndimage import uniform_filter1d, maximum_filter1d

__all__ = ["polish", "ride_vocal", "clean_gaps", "carve_beat", "pad_tail", "fade_tail", "dither_int16", "mp3_safe_gain", "true_peak_db"]

GENRE_POLISH = {
    "afrobeats": dict(ride=1.0, up=3.0, down=3.5, breath=8.0, carve=2.0),
    "amapiano":  dict(ride=1.0, up=3.0, down=3.5, breath=8.0, carve=2.0),
    "hiphop":    dict(ride=1.1, up=3.5, down=4.0, breath=10.0, carve=2.0),
    "rnb":       dict(ride=0.8, up=2.5, down=3.0, breath=5.0, carve=1.5),
    "pop":       dict(ride=1.0, up=3.0, down=3.5, breath=8.0, carve=2.0),
    "dancehall": dict(ride=1.0, up=3.0, down=3.5, breath=8.0, carve=2.0),
    "gospel":    dict(ride=0.8, up=2.5, down=3.0, breath=5.0, carve=1.5),
    "other":     dict(ride=0.9, up=3.0, down=3.0, breath=6.0, carve=1.8),
}
_ALIAS = {"afro": "afrobeats", "afrobeat": "afrobeats", "afropop": "afrobeats", "rap": "hiphop", "trap": "hiphop",
          "drill": "hiphop", "rb": "rnb", "randb": "rnb", "piano": "amapiano"}

def _cfg(g):
    k = "".join(c for c in str(g or "other").lower() if c.isalnum())
    return dict(GENRE_POLISH[_ALIAS.get(k, k) if _ALIAS.get(k, k) in GENRE_POLISH else "other"])

def _bp(lo, hi, sr, order=2):
    return sg.butter(order, [lo, min(hi, sr / 2 * 0.95)], btype="band", fs=sr, output="sos")

def _mono(x):
    x = np.asarray(x, np.float64)
    return x if x.ndim == 1 else x.mean(axis=0)

def _lvl(x, sr, win_s, hop):
    p = uniform_filter1d(x.astype(np.float64) ** 2, size=max(1, int(win_s * sr)), mode="nearest")[::hop]
    return 10 * np.log10(p + 1e-12)

def _to_samples(c, hop, n):
    return np.interp(np.arange(n), (np.arange(len(c)) + 0.5) * hop, c)

def _thr(lvl):
    live = lvl[lvl > -70]
    return None if len(live) < 30 else max(np.percentile(live, 90) - 22.0, -60.0)

def _db(v):
    return 20.0 * np.log10(max(float(v), 1e-12))

def _rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))) + 1e-12)

def ride_vocal(vocal, sr, genre="afrobeats", strength=None):
    x = np.asarray(vocal, np.float64)
    m = _mono(x)
    cfg = _cfg(genre)
    hop = int(0.010 * sr)
    hs = hop / sr
    lvl = _lvl(sg.sosfiltfilt(_bp(150, 5000, sr), m), sr, 0.040, hop)
    sib = _lvl(sg.sosfiltfilt(_bp(5000, 10000, sr), m), sr, 0.040, hop)
    thr = _thr(lvl)
    if thr is None: return x, {"skipped": "vocal silent / too short"}
    act = lvl > thr
    ok = act & ~(sib > lvl - 6.0)
    if ok.sum() < 30: return x, {"skipped": "not enough voiced material"}
    glob = float(np.median(lvl[ok]))
    step, half = 100, 300
    pts, vals = [], []
    for c in range(0, len(lvl), step):
        w = lvl[max(0, c - half): c + half][ok[max(0, c - half): c + half]]
        if len(w) > 20:
            pts.append(c); vals.append(np.median(w))
    local = np.interp(np.arange(len(lvl)), pts, vals) if pts else np.full(len(lvl), glob)
    target = 0.5 * glob + 0.5 * local
    spread = float(np.percentile(lvl[ok], 90) - np.percentile(lvl[ok], 10))
    s = float(np.clip((spread - 3.0) / 8.0, 0.15, 0.65) * cfg["ride"]) if strength is None else float(strength)
    raw = np.clip(s * (target - lvl), -cfg["down"], cfg["up"])
    ka, kr = np.exp(-hs / 0.025), np.exp(-hs / 0.120)
    g = np.zeros(len(lvl))
    cur = 0.0
    for i in range(len(lvl)):
        if ok[i]:
            t = raw[i]
            k = ka if t < cur else kr
            cur = k * cur + (1.0 - k) * t
        elif not act[i]:
            cur *= 0.98
        g[i] = cur
    g = np.r_[g[1:], g[-1]]
    gain = 10 ** (_to_samples(g, hop, x.shape[-1]) / 20.0)
    out = x * gain
    rg = g[act]
    return out, {"strength": round(s, 2), "target_db": round(glob, 1), "spread_db": round(spread, 1),
                 "ride_up_max_db": round(float(max(rg.max(), 0)), 1), "ride_down_max_db": round(float(min(rg.min(), 0)), 1),
                 "mean_abs_move_db": round(float(np.abs(rg).mean()), 2)}

def clean_gaps(vocal, sr, genre="afrobeats", depth_db=None):
    x = np.asarray(vocal, np.float64)
    m = _mono(x)
    cfg = _cfg(genre)
    hop = int(0.005 * sr)
    hs = hop / sr
    lvl = _lvl(m, sr, 0.020, hop)
    thr = _thr(lvl)
    if thr is None: return x, {"skipped": "vocal silent / too short"}
    act = lvl > thr
    gap = ~act
    gap = uniform_filter1d(gap.astype(float), size=int(0.100 / hs), mode="nearest") > 0.99
    after = maximum_filter1d(act.astype(np.uint8), size=int(0.200 / hs), origin=int(0.100 / hs) - 1).astype(bool)
    before = maximum_filter1d(act.astype(np.uint8), size=int(0.030 / hs), origin=-(int(0.015 / hs))).astype(bool)
    gap &= ~after & ~before
    if not gap.any(): return x, {"skipped": "no gaps found"}
    voice = float(np.median(lvl[act]))
    gap_lvl = float(np.percentile(lvl[gap], 90))
    rel = voice - gap_lvl
    depth = float((depth_db if depth_db is not None else cfg["breath"]) * np.clip((45.0 - rel) / 15.0, 0.25, 1.0))
    red = np.where(gap, depth, 0.0)
    ka, kr = np.exp(-hs / 0.030), np.exp(-hs / 0.006)
    cur = 0.0
    out_r = np.zeros(len(red))
    for i in range(len(red)):
        t = red[i]
        k = ka if t > cur else kr
        cur = k * cur + (1.0 - k) * t
        out_r[i] = cur
    gain = 10 ** (-_to_samples(out_r, hop, x.shape[-1]) / 20.0)
    return x * gain, {"depth_db": round(depth, 1), "gaps_pct": round(float(gap.mean() * 100), 1),
                      "gap_level_below_voice_db": round(rel, 1)}

_CARVE_BANDS = [
    (250, 500, -2.0, 0.75), (500, 1000, 2.0, 1.0), (1000, 2000, 3.0, 1.0), (2000, 4000, 2.0, 1.0)]

def carve_beat(beat, vocal, sr, genre="afrobeats", strength=1.0):
    b = np.asarray(beat, np.float64)
    if b.ndim == 1: b = np.stack([b, b])
    n = b.shape[1]
    vm = _mono(vocal)
    vm = vm[:n] if len(vm) >= n else np.pad(vm, (0, n - len(vm)))
    cfg = _cfg(genre)
    hop = int(0.010 * sr)
    hs = hop / sr
    vl = _lvl(vm, sr, 0.040, hop)
    thr = _thr(vl)
    if thr is None: return b, {"skipped": "vocal silent / too short"}
    act = vl > thr
    bm = b.mean(axis=0)
    out = b.copy()
    rep = {}
    ka, kr = np.exp(-hs / 0.015), np.exp(-hs / 0.180)
    for lo, hi, want, scale in _CARVE_BANDS:
        sos = _bp(lo, hi, sr)
        Lv = _lvl(sg.sosfiltfilt(sos, vm), sr, 0.050, hop)
        Lb = _lvl(sg.sosfiltfilt(sos, bm), sr, 0.050, hop)
        cap = cfg["carve"] * scale * float(np.clip(strength, 0.0, 1.0))
        need = np.where(act, np.clip(want - (Lv - Lb), 0.0, cap), 0.0)
        name = f"{lo}-{hi}"
        if need.max() < 0.1:
            rep[name] = {"avg_dip_db": 0.0, "max_dip_db": 0.0, "dipping_pct": 0.0}
            continue
        cur, d = 0.0, np.zeros(len(need))
        for i in range(len(need)):
            t = need[i]
            k = ka if t > cur else kr
            cur = k * cur + (1.0 - k) * t
            d[i] = cur
        g = 10 ** (-_to_samples(d, hop, n) / 20.0)
        for ch in range(2):
            band = sg.sosfiltfilt(sos, out[ch])
            out[ch] = out[ch] - (1.0 - g) * band
        rep[name] = {"avg_dip_db": round(float(d[act].mean()), 2), "max_dip_db": round(float(d.max()), 2),
                     "dipping_pct": round(float((d > 0.3).mean() * 100), 1)}
    lo_sos = sg.butter(2, 150, "low", fs=sr, output="sos")
    rep["beat_change_db"] = round(_db(_rms(out) / _rms(b)), 2)
    rep["beat_low_end_change_db"] = round(_db(_rms(sg.sosfiltfilt(lo_sos, out.mean(axis=0))) / _rms(sg.sosfiltfilt(lo_sos, bm))), 2)
    return out, rep

def polish(vocal, beat, sr, genre="afrobeats", ride=True, gaps=True, carve=True, carve_strength=1.0):
    t0 = time.time()
    rep = {"genre": genre}
    v = np.asarray(vocal, np.float64)
    b = np.asarray(beat, np.float64) if beat is not None else None
    if ride: v, rep["ride"] = ride_vocal(v, sr, genre)
    if gaps: v, rep["gaps"] = clean_gaps(v, sr, genre)
    if carve and b is not None: b, rep["carve"] = carve_beat(b, v, sr, genre, carve_strength)
    rep["seconds"] = round(time.time() - t0, 1)
    return v, b, rep

def pad_tail(x, sr, tail_s):
    x = np.asarray(x)
    pad = int(tail_s * sr)
    return np.pad(x, (0, pad)) if x.ndim == 1 else np.pad(x, ((0, 0), (0, pad)))

def fade_tail(y, sr, fade_s=0.25):
    y = np.array(y, np.float64)
    tail = y[..., -int(0.1 * sr):]
    if _db(_rms(tail)) < -55.0: return y, False
    k = int(fade_s * sr)
    y[..., -k:] *= 0.5 * (1 + np.cos(np.linspace(0, np.pi, k)))
    return y, True

def dither_int16(y, seed=1):
    rng = np.random.default_rng(seed)
    q = np.asarray(y, np.float64) * 32767.0
    q = q + rng.random(q.shape) - rng.random(q.shape)
    return np.clip(np.round(q), -32768, 32767).astype(np.int16).T

def true_peak_db(x, sr):
    x = np.atleast_2d(np.asarray(x, np.float64))
    return _db(np.abs(sg.resample_poly(x, 4, 1, axis=-1)).max())

def mp3_safe_gain(y, sr, ceiling=-1.0, bitrate="320k", margin=0.02):
    if shutil.which("ffmpeg") is None: return 0.0, None, "ffmpeg not available"
    d = tempfile.mkdtemp()
    try:
        a = np.atleast_2d(np.asarray(y, np.float32))
        wf.write(os.path.join(d, "a.wav"), sr, a.T)
        run = lambda *c: subprocess.run(c, check=True, capture_output=True)
        run("ffmpeg", "-y", "-i", os.path.join(d, "a.wav"), "-b:a", bitrate, os.path.join(d, "a.mp3"))
        run("ffmpeg", "-y", "-i", os.path.join(d, "a.mp3"), "-f", "wav", "-acodec", "pcm_f32le", os.path.join(d, "b.wav"))
        _, dec = wf.read(os.path.join(d, "b.wav"))
        tp = true_peak_db(np.atleast_2d(dec.astype(np.float64).T), sr)
        return float(min(0.0, ceiling - tp - margin)), round(float(tp), 2), "ok"
    except Exception as e:
        return 0.0, None, f"encode check failed: {str(e)[:60]}"
    finally:
        shutil.rmtree(d, ignore_errors=True)
