"""asake_engine.py - builds the Asake group-vocal bus ("many people singing the same thing").
numpy + scipy only. group_from_dry(dry_lead, sr) -> (group (n,2) float32 | None, report). Never raises."""
import numpy as np
from scipy import signal as sg
from scipy.ndimage import uniform_filter1d

EPS = 1e-9


def _db(x):
    return 20.0 * np.log10(np.maximum(x, EPS))


def _lin(d):
    return 10.0 ** (np.asarray(d, dtype=np.float64) / 20.0)


def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        if x.shape[0] <= 2 and x.shape[1] > x.shape[0]:
            x = x.T
        return x.mean(axis=1)
    return x


def _hop(x, hop, kind="rms"):
    n = (len(x) + hop - 1) // hop
    pad = np.zeros(n * hop)
    pad[: len(x)] = np.abs(x) if kind == "peak" else x
    b = pad.reshape(n, hop)
    return b.max(axis=1) if kind == "peak" else np.sqrt((b * b).mean(axis=1) + 1e-18)


def _up(g, hop, n):
    return np.interp(np.arange(n), (np.arange(len(g)) + 0.5) * hop, g)


def _smooth_gain(target_db, hop_s, atk_ms, rel_ms):
    a_a = np.exp(-hop_s * 1000.0 / max(atk_ms, 0.1))
    a_r = np.exp(-hop_s * 1000.0 / max(rel_ms, 0.1))
    out = np.empty(len(target_db))
    s = 0.0
    for i, t in enumerate(target_db):
        c = a_a if t < s else a_r
        s = c * s + (1.0 - c) * t
        out[i] = s
    return out


def _active_rms_db(x, sr):
    x2 = x if x.ndim == 1 else np.sqrt((x ** 2).mean(axis=1))
    r = _hop(x2, max(1, int(sr * 0.02)))
    d = _db(r)
    m = d > np.percentile(d, 95) - 30.0
    if m.sum() == 0:
        m = np.ones_like(m)
    return float(10.0 * np.log10(np.mean(r[m] ** 2) + 1e-18)), d, m


def _scale_active(x, target_db, sr):
    return x * float(_lin(target_db - _active_rms_db(x, sr)[0]))


def _biquad(kind, f0, sr, gain_db, q=0.707):
    A = 10.0 ** (gain_db / 40.0)
    w = 2.0 * np.pi * min(f0, 0.45 * sr) / sr
    cw, sw = np.cos(w), np.sin(w)
    al = sw / (2.0 * q)
    if kind == "peak":
        b = [1 + al * A, -2 * cw, 1 - al * A]
        a = [1 + al / A, -2 * cw, 1 - al / A]
    else:  # highshelf
        s = 2 * np.sqrt(A) * al
        b = [A * ((A + 1) + (A - 1) * cw + s), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - s)]
        a = [(A + 1) - (A - 1) * cw + s, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - s]
    return sg.tf2sos(b, a)


def _apply(x, sos):
    return sg.sosfilt(sos, x, axis=0)


def _hp(x, f, sr, order=2):
    return sg.sosfilt(sg.butter(order, f, "highpass", fs=sr, output="sos"), x, axis=0)


def _lp(x, f, sr, order=2):
    return sg.sosfilt(sg.butter(order, min(f, 0.45 * sr), "lowpass", fs=sr, output="sos"), x, axis=0)


def _compress(x, sr, thr_db, ratio, atk_ms=30.0, rel_ms=200.0, knee_db=6.0):
    det = np.max(np.abs(x), axis=1)
    hop = max(1, int(sr * 0.002))
    over = _db(_hop(det, hop, "peak")) - thr_db
    k = knee_db
    y = np.where(over < -k / 2, over,
                 np.where(over > k / 2, over / ratio, over + (1.0 / ratio - 1.0) * (over + k / 2) ** 2 / (2 * k)))
    gs = _smooth_gain(np.minimum(y - over, 0.0), hop / sr, atk_ms, rel_ms)
    return x * _lin(_up(gs, hop, len(det)))[:, None]


def _saturate(x, drive_db, sr):
    if drive_db < 0.1:
        return x
    rms_db = _active_rms_db(x, sr)[0]
    if rms_db < -90:
        return x
    sc = float(_lin(-14.0 - rms_db))
    d = float(_lin(drive_db))
    up = sg.resample_poly(x * sc, 4, 1)
    y = sg.resample_poly(np.tanh(d * up + 0.06) - np.tanh(0.06), 1, 4)
    y = y[: len(x)] if len(y) >= len(x) else np.pad(y, (0, len(x) - len(y)))
    y = _hp(y, 20.0, sr, 1)
    return y * float(_lin(rms_db - _active_rms_db(y, sr)[0]))


def _ir(sr, length_s, predelay_ms, rng, decay_db=60.0, hp=200.0, lp=7000.0):
    n = max(8, int(sr * length_s))
    env = 10.0 ** (-(decay_db / 20.0) * (np.arange(n) / sr) / length_s)
    ir = np.stack([rng.standard_normal(n) * env for _ in range(2)], axis=1)
    ir = _lp(_hp(ir, hp, sr), lp, sr)
    pre = int(sr * predelay_ms / 1000.0)
    if pre:
        ir = np.pad(ir, ((pre, 0), (0, 0)))
    return ir / (np.sqrt((ir ** 2).sum(axis=0, keepdims=True)) + EPS)


def _conv(x, ir):
    n = len(x)
    return np.stack([sg.fftconvolve(x[:, c], ir[:, c])[:n] for c in range(2)], axis=1)


def _duck(env_norm, hop_s, hop, n, duck_db):
    return _lin(_up(_smooth_gain(-duck_db * env_norm, hop_s, 10.0, 250.0), hop, n))


def _group_bus(src, sr, n_vox, group_db, rng, env_norm, hop, hop_s, lead_rms, rdb, act):
    N = len(src)
    t = np.arange(N, dtype=np.float64)
    pans = np.linspace(-0.85, 0.85, n_vox)
    rng.shuffle(pans)
    pans = np.clip(pans + rng.uniform(-0.05, 0.05, n_vox), -0.95, 0.95)
    L = np.zeros(N)
    R = np.zeros(N)
    for i in range(n_vox):
        tm = t - rng.uniform(0.012, 0.040) * sr                 # 12-40 ms behind the lead
        for _ in range(2):                                      # slow timing/pitch wander (zero mean)
            f = rng.uniform(0.25, 0.9)
            A = rng.uniform(0.0004, 0.0014) * sr
            tm = tm + A * np.sin(2 * np.pi * f * t / sr + rng.uniform(0, 2 * np.pi))
        v = np.interp(tm, t, src, left=0.0, right=0.0)
        v = _apply(v, _biquad("peak", rng.uniform(900, 3200), sr, rng.uniform(-3.5, 3.5), 1.0))
        v = _apply(v, _biquad("highshelf", 2500, sr, rng.uniform(-2.5, 2.5)))
        v = _saturate(v, rng.uniform(0.0, 2.0), sr)
        v = v * float(_lin(rng.uniform(-2.5, 2.5)))
        th = (pans[i] + 1.0) * np.pi / 4.0
        L += v * np.cos(th)
        R += v * np.sin(th)
    G = np.stack([L, R], axis=1) / np.sqrt(n_vox)
    G = _lp(_hp(G, 250.0, sr), 9000.0, sr)                       # mid-forward group tone
    pre = _active_rms_db(G, sr)[0]
    G = _compress(G, sr, pre + 2.0, 2.0)                         # glue
    G = G * float(_lin(pre - _active_rms_db(G, sr)[0]))
    sm = uniform_filter1d(rdb, size=max(3, int(2.0 / hop_s)), mode="nearest")   # louder sections = bigger group
    swell = np.clip((sm - (np.median(sm[act]) if act.any() else np.median(sm))) * 0.5, -3.0, 3.0)
    G = G * _lin(_up(swell, hop, N))[:, None]
    G = _scale_active(G, lead_rms - group_db, sr)
    M = (G[:, 0] + G[:, 1]) / 2.0
    S = _hp((G[:, 0] - G[:, 1]) / 2.0, 120.0, sr)                # low-mono below 120 Hz
    c0 = float(np.corrcoef(G[:, 0], G[:, 1])[0, 1])
    if c0 < 0.15:
        S = S * 0.7                                              # narrow if the stack gets phasey
    G = np.stack([M + S, M - S], axis=1)
    dry = _active_rms_db(G, sr)[0]
    room = _scale_active(_conv(G, _ir(sr, 0.06, 4.0, rng, 40.0, 250.0, 8000.0)), dry - 14.0, sr)
    plate = _scale_active(_conv(G, _ir(sr, 1.8, 30.0, rng, 60.0, 250.0, 7500.0)), dry - 11.0, sr)
    plate = plate * _duck(env_norm, hop_s, hop, N, 4.0)[:, None]  # tail ducks under the lead
    return G + room + plate, c0


def group_from_dry(lead_dry, sr, bpm=None, seed=0, n_voices=None):
    rep = {"engine": "asake_engine", "ok": False}
    try:
        sr = int(sr)
        if sr < 32000:
            raise ValueError("sample rate %d too low (need >= 32000)" % sr)
        x = np.nan_to_num(_mono(lead_dry))
        x = x - float(np.mean(x))
        N = len(x)
        if N < sr:
            raise ValueError("lead shorter than 1 second")
        if float(np.max(np.abs(x))) < 1e-5:
            raise ValueError("lead is silent")
        lead_rms, rdb, act = _active_rms_db(x, sr)
        dens = float(act.mean())
        n_vox = int(np.clip(int(n_voices), 4, 20)) if n_voices else int(np.clip(round(14 - 6 * dens), 8, 14))
        group_db = float(np.clip(4.5 + 4.0 * dens, 5.0, 9.0))
        hop = max(1, int(sr * 0.02))
        env_norm = np.clip((rdb - (np.percentile(rdb, 95) - 25.0)) / 15.0, 0.0, 1.0)
        G, c0 = _group_bus(x, sr, n_vox, group_db, np.random.default_rng(seed), env_norm, hop, hop / sr, lead_rms, rdb, act)
        G = np.nan_to_num(G)
        pk, ceil = float(np.max(np.abs(G))), float(_lin(-0.5))
        if pk > ceil:
            G = G * (ceil / pk)
        rep.update(ok=True, n_voices=n_vox, group_db_below_lead=group_db, corr_before_width=c0,
                   level_vs_lead_db=float(_active_rms_db(G, sr)[0] - lead_rms))
        return G.astype(np.float32), rep
    except Exception as e:
        rep["error"] = "%s: %s" % (type(e).__name__, e)
        return None, rep
