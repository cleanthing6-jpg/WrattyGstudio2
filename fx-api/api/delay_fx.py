"""
delay_fx.py - professional vocal delay for WrattyGstudio.  numpy only.
"""
import numpy as np

DELAY_PRESETS = {
    "afrobeats": dict(fb=0.30, taps=5, hp=280.0, lp_bright=5000.0, lp_dark=2500.0, duck_db=10.0, width=0.70, level_db=-16.0),
    "amapiano":  dict(fb=0.24, taps=4, hp=320.0, lp_bright=4500.0, lp_dark=2200.0, duck_db=10.0, width=0.60, level_db=-19.0),
    "highlife":  dict(fb=0.20, taps=4, hp=250.0, lp_bright=5500.0, lp_dark=3000.0, duck_db=8.0,  width=0.50, level_db=-18.0),
    "pop":       dict(fb=0.22, taps=4, hp=250.0, lp_bright=6000.0, lp_dark=3000.0, duck_db=8.0,  width=0.70, level_db=-18.0),
    "rnb":       dict(fb=0.34, taps=5, hp=250.0, lp_bright=4000.0, lp_dark=2000.0, duck_db=8.0,  width=0.80, level_db=-16.0),
    "rap":       dict(fb=0.15, taps=3, hp=320.0, lp_bright=5000.0, lp_dark=2500.0, duck_db=12.0, width=0.50, level_db=-21.0),
    "neutral":   dict(fb=0.20, taps=3, hp=250.0, lp_bright=5000.0, lp_dark=2500.0, duck_db=10.0, width=0.50, level_db=-20.0),
}
SUGGESTED_NOTE = {"afrobeats": 0.75, "amapiano": 1.0, "highlife": 0.5, "pop": 0.5, "rnb": 0.75, "rap": 0.5, "neutral": 1.0}
DELAY_MIN_MS = 180.0
DELAY_MAX_MS = 640.0
MAX_TAIL_MS = 3000.0
ACTIVE_GATE_DB = -45.0


def fold_bpm(bpm, lo=70.0, hi=140.0):
    try: b = float(bpm)
    except (TypeError, ValueError): return 100.0
    if not np.isfinite(b) or b <= 0: return 100.0
    while b < lo: b *= 2.0
    while b > hi: b /= 2.0
    return b


def delay_ms(bpm, note=0.75):
    beat = 60000.0 / fold_bpm(bpm)
    t = max(float(note), 0.0625) * beat
    while t > DELAY_MAX_MS: t /= 2.0
    while t < DELAY_MIN_MS: t *= 2.0
    return t


def _mono(voc):
    a = np.asarray(voc)
    if a.ndim == 1: return a.astype(np.float64)
    return a.mean(axis=0, dtype=np.float64) if a.shape[0] <= a.shape[1] else a.mean(axis=1, dtype=np.float64)


def _rms(a, chunk=1 << 20):
    flat = np.asarray(a).reshape(-1)
    acc = 0.0
    for i in range(0, flat.size, chunk):
        c = flat[i:i + chunk].astype(np.float64)
        acc += float(np.dot(c, c))
    return float(np.sqrt(acc / max(flat.size, 1)))


def _shape(x, sr, hp, lp, order=2, block=1 << 17, pad=4096):
    n = len(x)
    out = np.empty(n, dtype=np.float32)
    nfft = 1 << int(np.ceil(np.log2(block + 2 * pad)))
    f = np.fft.rfftfreq(nfft, 1.0 / sr)
    f[0] = 1e-3
    H = np.ones_like(f)
    if hp: H = H / np.sqrt(1.0 + (hp / f) ** (2 * order))
    if lp: H = H / np.sqrt(1.0 + (f / lp) ** (2 * order))
    for s in range(0, n, block):
        e = min(n, s + block)
        a, b = max(0, s - pad), min(n, e + pad)
        y = np.fft.irfft(np.fft.rfft(x[a:b], nfft) * H, nfft)[:b - a]
        out[s:e] = y[s - a:e - a]
    return out


def _duck_gain(x, sr, depth_db, release_ms):
    n = len(x)
    blk = max(1, int(sr * 0.001))
    m = n // blk
    if m < 10 or depth_db <= 0: return np.ones(n, dtype=np.float32)
    pk = np.abs(x[:m * blk]).reshape(m, blk).max(axis=1)
    att = np.exp(-1.0 / 3.0)
    rel = np.exp(-1.0 / max(release_ms, 20.0))
    env = np.empty(m); e = 0.0
    for i in range(m):
        c = att if pk[i] > e else rel
        e = c * e + (1.0 - c) * pk[i]
        env[i] = e
    env_db = 20.0 * np.log10(env + 1e-9)
    live = env > 1e-4
    ref_db = float(np.percentile(env_db[live], 75)) if live.any() else -20.0
    amt = np.clip((env_db - (ref_db - 20.0)) / 14.0, 0.0, 1.0)
    g_db = -depth_db * amt
    g = 10.0 ** (g_db / 20.0)
    out = np.empty(n, dtype=np.float32)
    xs = (np.arange(m) + 0.5) * blk
    for i in range(0, n, 1 << 20):
        j = min(n, i + (1 << 20))
        out[i:j] = np.interp(np.arange(i, j), xs, g)
    return out


def _pan_gains(pan):
    th = (pan + 1.0) * np.pi / 4.0
    return float(np.cos(th)), float(np.sin(th))


def render(voc, sr, bpm, preset="neutral", note=0.75, overrides=None, target_rms=None, start_side=1.0):
    p = dict(DELAY_PRESETS.get(str(preset).lower(), DELAY_PRESETS["neutral"]))
    if overrides: p.update(overrides)
    x = _mono(voc); n = len(x)
    info = {"preset": str(preset), "taps": 0, "time_ms": None, "bpm_used": None, "density": None, "fb": None, "duck_db": None, "tail_s": 0.0}
    wet = np.zeros((2, n), dtype=np.float32)
    if n < sr // 2 or float(np.max(np.abs(x))) < 1e-6: return wet, info
    w = int(0.05 * sr); k = n // w
    fr = 20.0 * np.log10(np.sqrt((x[:k * w].reshape(k, w) ** 2).mean(axis=1)) + 1e-12)
    act_frames = fr > ACTIVE_GATE_DB
    dens = float(act_frames.mean()) if k else 0.0
    fb = float(p["fb"]); lvl = float(p["level_db"]); duck = float(p["duck_db"])
    if dens > 0.75: fb *= 0.85; lvl -= 2.0; duck = min(14.0, duck + 2.0)
    elif dens < 0.45: fb = min(0.45, fb * 1.10); lvl += 1.5
    fb = float(np.clip(fb, 0.0, 0.45))
    T = delay_ms(bpm, note); d = int(round(T * sr / 1000.0))
    bright = _shape(x, sr, p["hp"], p["lp_bright"])
    dark = _shape(x, sr, p["hp"], p["lp_dark"])
    sample_mask = np.repeat(act_frames, w)
    sample_mask = np.concatenate([sample_mask, np.zeros(n - sample_mask.size, dtype=bool)])
    ref = bright[sample_mask]
    ref_rms = _rms(ref) if ref.size else 1e-6
    del ref
    base = ref_rms * 10.0 ** (lvl / 20.0)
    taps = int(min(p["taps"], max(1, MAX_TAIL_MS // T)))
    last = 0
    for i in range(1, taps + 1):
        off = i * d
        if off >= n: break
        a = 0.0 if taps == 1 else (i - 1) / float(taps - 1)
        g = base * (fb ** (i - 1)) / max(ref_rms, 1e-9)
        seg = (bright[:n - off] * (1.0 - a) + dark[:n - off] * a) * g
        side = start_side if i % 2 == 1 else -start_side
        pan = side * float(p["width"]) * (0.0 if i == 1 else (0.65 if i == 2 else 1.0))
        gl, gr = _pan_gains(pan)
        wet[0, off:] += seg * gl
        wet[1, off:] += seg * gr
        last = i
    release = float(np.clip(0.45 * T, 110.0, 260.0))
    gain = _duck_gain(x, sr, duck, release)
    wet *= gain[None, :]
    if target_rms is not None and target_rms > 0:
        cur = _rms(wet)
        if cur > 1e-12: wet *= np.float32(target_rms / cur)
    peak = float(np.abs(wet).max())
    if peak > 0.5: wet *= np.float32(0.5 / peak)
    info.update({"taps": last, "time_ms": round(T, 1), "bpm_used": round(fold_bpm(bpm), 1), "density": round(dens, 3), "fb": round(fb, 3), "duck_db": round(duck, 1), "tail_s": round(last * T / 1000.0, 2), "release_ms": round(release)})
    return wet, info
