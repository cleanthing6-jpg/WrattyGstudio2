"""pro_touch.py -- adaptive "close dry lead + floating wide ambience" layer."""
import numpy as np
import scipy.signal as sg

def _mono(x):
    a = np.asarray(x, np.float32)
    return a.mean(axis=0) if a.ndim == 2 else a

def _interp(v, xs, ys):
    return float(np.interp(v, xs, ys))

def _smooth(x, sr, tau_s):
    a = float(np.exp(-1.0 / (tau_s * sr)))
    return sg.lfilter([1.0 - a], [1.0, -a], x).astype(np.float32)

def _frame_db(m, sr, hop_s=0.05):
    hop = max(1, int(sr * hop_s))
    k = len(m) // hop
    if k < 4:
        return np.full(1, -90.0), hop
    r = np.sqrt((m[:k * hop].reshape(k, hop) ** 2).mean(1) + 1e-12)
    return 20 * np.log10(r), hop

def _active_mask(db):
    return db > (np.percentile(db, 95) - 25.0)

def _active_rms_db(x, sr, act=None):
    db, _ = _frame_db(_mono(x), sr)
    if act is None:
        act = _active_mask(db)
    k = min(len(act), len(db))
    a = act[:k]
    if a.sum() == 0:
        a = np.ones(k, bool)
    return float(10 * np.log10((10 ** (db[:k][a] / 10)).mean() + 1e-20)), act

def _duck_env(v, sr):
    a = np.abs(v)
    d = np.maximum(_smooth(a, sr, 0.02), _smooth(a, sr, 0.20))
    return np.clip(d / (np.percentile(d, 95) + 1e-9), 0.0, 1.0)

def _f0_median(m, sr, frames=300):
    N = 2048
    k = len(m) // N
    if k < 8: return None
    fr = m[:k * N].reshape(k, N)
    e = (fr ** 2).mean(1)
    idx = np.argsort(e)[::-1][:frames]
    lo, hi = int(sr / 500), int(sr / 70)
    out = []
    for i in idx:
        f = fr[i] * np.hanning(N)
        ac = np.fft.irfft(np.abs(np.fft.rfft(f, 2 * N)) ** 2)[:N]
        if ac[0] <= 0: continue
        ac = ac / ac[0]
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.45: out.append(sr / lag)
    return float(np.median(out)) if len(out) >= 10 else None

def analyze(voc, sr):
    m = _mono(voc)
    db, hop = _frame_db(m, sr)
    act = _active_mask(db)
    hop_s = hop / sr
    total = len(db) * hop_s
    space, run = 0.0, 0
    nz = np.where(act)[0]
    inner = act[nz[0]:nz[-1] + 1] if len(nz) else act
    total = max(len(inner) * hop_s, 1e-6)
    for a in list(inner) + [True]:
        if not a: run += 1
        else:
            if run * hop_s >= 0.4: space += run * hop_s
            run = 0
    space = space / max(total, 1e-6)
    ad = db[act] if act.sum() > 5 else db
    spread = float(np.percentile(ad, 90) - np.percentile(ad, 10))
    N = 4096
    k = len(m) // N
    bright = -15.0
    if k > 4:
        X = np.abs(np.fft.rfft(m[:k * N].reshape(k, N) * np.hanning(N), axis=1)) ** 2
        f = np.fft.rfftfreq(N, 1.0 / sr)
        e = 10 * np.log10(X.sum(1) + 1e-20)
        a2 = e > np.percentile(e, 95) - 25.0
        P = X[a2].sum(0) if a2.any() else X.sum(0)
        hi = P[(f >= 4000) & (f < 8000)].sum()
        mid = P[(f >= 250) & (f < 1000)].sum()
        bright = float(10 * np.log10((hi + 1e-20) / (mid + 1e-20)))
    return {"active_ratio": float(act.mean()), "space": float(space), "spread_db": spread,
            "bright_db": bright, "f0": _f0_median(m, sr), "dur_s": float(len(m) / sr)}

def _pick_delay_note(bpm):
    beat = 60.0 / bpm
    for note in (0.75, 0.5, 1.0, 1.5, 0.25):
        if 0.25 <= beat * note <= 0.55: return note
    t = 0.75 * beat
    while t > 0.55: t /= 2.0
    while t < 0.25: t *= 2.0
    return t / beat

def plan(p, bpm):
    bpm = float(np.clip(bpm or 100.0, 60.0, 200.0))
    beat = 60.0 / bpm
    act, space = p["active_ratio"], p["space"]
    ir_s = min(_interp(space, [0.05, 0.55], [0.9, 1.6]), 4.0 * beat)
    note = _pick_delay_note(bpm)
    f0 = p.get("f0")
    return {
        "bpm": round(bpm, 1), "ir_s": round(ir_s, 2),
        "predelay_ms": round(float(np.clip(beat / 8.0 * 1000.0, 40.0, 90.0)), 1),
        "tail_hpf": round(float(np.clip(1.8 * f0, 250.0, 450.0)) if f0 else 350.0, 0),
        "tail_lpf": round(_interp(p["bright_db"], [-24.0, -10.0], [7500.0, 5500.0]), 0),
        "tail_target_db": round(_interp(act, [0.35, 0.75], [-15.0, -20.0]), 1),
        "tail_duck_db": round(_interp(act, [0.35, 0.75], [9.0, 12.0]), 1),
        "delay_note": round(note, 3),
        "delay_ms": round(beat * note * 1000.0, 1),
        "delay_fb": round(_interp(space, [0.05, 0.55], [0.18, 0.26]), 3),
        "delay_target_db": round(_interp(act, [0.35, 0.75], [-16.0, -21.0]), 1),
        "delay_duck_db": round(_interp(act, [0.35, 0.75], [7.0, 11.0]), 1),
        "delay_hpf": 400.0,
        "delay_lpf": round(min(5000.0, _interp(p["bright_db"], [-24.0, -10.0], [5500.0, 4200.0])), 0),
        "double_db": round(_interp(act, [0.35, 0.75], [-8.0, -10.5]), 1),
        "side_db": round(_interp(space, [0.05, 0.55], [1.2, 2.2]), 1),
        "ride_strength": round(float(np.clip((p["spread_db"] - 6.0) / 20.0, 0.2, 0.65)), 2),
        "ride_max_db": round(float(np.clip(p["spread_db"] / 5.0, 2.0, 4.0)), 1),
    }

def long_tail(voc, sr, ir_s, predelay_ms, hpf, lpf, duck_db, target_db, seed=7, ref=None):
    v = _mono(voc); n = len(v); L = int(ir_s * sr)
    t = np.arange(L) / sr
    env = np.exp(-t / (ir_s / 6.9)) * np.minimum(1.0, t / 0.02)
    pre = int(predelay_ms / 1000.0 * sr)
    hp = sg.butter(2, hpf, "highpass", fs=sr, output="sos")
    lp = sg.butter(2, lpf, "lowpass", fs=sr, output="sos")
    lp2 = sg.butter(2, lpf * 0.55, "lowpass", fs=sr, output="sos")
    mixk = np.clip(t / ir_s, 0.0, 1.0)
    chans = []
    for ch in range(2):
        noise = np.random.default_rng(seed + ch * 101).standard_normal(L).astype(np.float32)
        h = sg.sosfilt(hp, noise)
        ir = (sg.sosfilt(lp, h) * (1 - mixk) + sg.sosfilt(lp2, h) * mixk) * env
        ir = np.concatenate([np.zeros(pre, np.float32), ir]).astype(np.float32)
        ir /= (np.sqrt((ir ** 2).sum()) + 1e-9)
        chans.append(sg.oaconvolve(v, ir, mode="full")[:n].astype(np.float32))
    return _finish(np.stack(chans), v, sr, duck_db, target_db)

def pingpong_delay(voc, sr, delay_ms, fb, hpf, lpf, duck_db, target_db, ref=None):
    v = _mono(voc); n = len(v); d = int(sr * delay_ms / 1000.0)
    src = sg.sosfilt(np.vstack([sg.butter(2, hpf, "highpass", fs=sr, output="sos"),
                                sg.butter(2, lpf, "lowpass", fs=sr, output="sos")]), v).astype(np.float32)
    dark = sg.sosfilt(sg.butter(2, lpf * 0.6, "lowpass", fs=sr, output="sos"), src).astype(np.float32)
    out = np.zeros((2, n), np.float32)
    k, g = 1, 1.0
    while g > 0.03 and k * d < n and k <= 10:
        w = min(1.0, (k - 1) / 3.0)
        tap = src * (1 - w) + dark * w
        ch = 1 if k % 2 == 1 else 0
        out[ch, k * d:] += (g * tap[:n - k * d]).astype(np.float32)
        g *= fb; k += 1
    return _finish(out, v, sr, duck_db, target_db)

def _finish(wet, v, sr, duck_db, target_db):
    d = _duck_env(v, sr)
    wet = wet * (10.0 ** (-duck_db * d / 20.0)).astype(np.float32)[None, :]
    dry_db, act = _active_rms_db(v, sr)
    wet_db, _ = _active_rms_db(wet, sr, act)
    wet = wet * np.float32(10.0 ** ((dry_db + target_db - wet_db) / 20.0))
    return wet.astype(np.float32)

def widen_return(wet, sr, side_db=2.5, mono_below=200.0):
    w = np.asarray(wet, np.float32)
    if w.ndim != 2 or w.shape[0] != 2: return w
    m, s = 0.5 * (w[0] + w[1]), 0.5 * (w[0] - w[1])
    s = sg.sosfilt(sg.butter(2, mono_below, "highpass", fs=sr, output="sos"), s) * np.float32(10 ** (side_db / 20))
    return np.stack([m + s, m - s]).astype(np.float32)

def filter_double(dbl, sr, hpf=200.0, lpf=9000.0):
    sos = np.vstack([sg.butter(2, hpf, "highpass", fs=sr, output="sos"),
                     sg.butter(2, lpf, "lowpass", fs=sr, output="sos")])
    return sg.sosfilt(sos, np.asarray(dbl, np.float32), axis=-1).astype(np.float32)

def render(voc, sr, bpm):
    prof = analyze(voc, sr)
    P = plan(prof, bpm)
    plate = long_tail(voc, sr, P["ir_s"], P["predelay_ms"], P["tail_hpf"], P["tail_lpf"],
                      P["tail_duck_db"], P["tail_target_db"])
    dly = pingpong_delay(voc, sr, P["delay_ms"], P["delay_fb"], P["delay_hpf"], P["delay_lpf"],
                         P["delay_duck_db"], P["delay_target_db"])
    plate = widen_return(plate, sr, P["side_db"])
    dly = widen_return(dly, sr, P["side_db"] * 0.8)
    P["profile"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in prof.items()}
    return plate, dly, P

def ride(x, sr, max_db=3.0, strength=0.5, smooth_s=0.35):
    a = np.asarray(x, np.float32)
    m = _mono(a)
    hop = int(sr * 0.01)
    k = len(m) // hop
    if k < 10: return a
    db = 20 * np.log10(np.sqrt((m[:k * hop].reshape(k, hop) ** 2).mean(1)) + 1e-6)
    act = db > np.percentile(db, 95) - 25.0
    if act.sum() < 10: return a
    g = np.where(act, np.clip(strength * (np.median(db[act]) - db), -max_db, max_db), 0.0)
    g = sg.lfilter(*sg.butter(1, 1.0 / smooth_s, fs=100.0), g)
    gi = np.interp(np.arange(a.shape[-1]), (np.arange(k) + 0.5) * hop, g)
    return (a * (10.0 ** (gi / 20.0)).astype(np.float32)).astype(np.float32)

# ==== pro_space bridge ====
_render_orig = render

def render(voc, sr, bpm, send=None):
    if send is None:
        return _render_orig(voc, sr, bpm)
    prof = analyze(voc, sr)
    P = plan(prof, bpm)
    plate = long_tail(send, sr, P["ir_s"], P["predelay_ms"], P["tail_hpf"], P["tail_lpf"],
                      P["tail_duck_db"], P["tail_target_db"], ref=voc)
    dly = pingpong_delay(send, sr, P["delay_ms"], P["delay_fb"], P["delay_hpf"], P["delay_lpf"],
                         P["delay_duck_db"], P["delay_target_db"], ref=voc)
    plate = widen_return(plate, sr, P["side_db"])
    dly = widen_return(dly, sr, P["side_db"] * 0.8)
    P["profile"] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in prof.items()}
    return plate, dly, P


def _tail(send, sr, ir_s, pre_ms, hpf, lpf, seed=7):
    v = _mono(send)
    n = len(v)
    L = max(1, int(ir_s * sr))
    t = np.arange(L) / sr
    env = np.exp(-t / (ir_s / 6.9)) * np.minimum(1.0, t / 0.02)
    pre = int(pre_ms / 1000.0 * sr)
    hp = sg.butter(2, hpf, "highpass", fs=sr, output="sos")
    lp = sg.butter(2, lpf, "lowpass", fs=sr, output="sos")
    lp2 = sg.butter(2, lpf * 0.55, "lowpass", fs=sr, output="sos")
    mixk = np.clip(t / max(ir_s, 1e-6), 0.0, 1.0)
    chans = []
    for ch in range(2):
        noise = np.random.default_rng(seed + ch * 101).standard_normal(L).astype(np.float32)
        h = sg.sosfilt(hp, noise)
        ir = (sg.sosfilt(lp, h) * (1 - mixk) + sg.sosfilt(lp2, h) * mixk) * env
        ir = np.concatenate([np.zeros(pre, np.float32), ir]).astype(np.float32)
        ir /= (np.sqrt((ir ** 2).sum()) + 1e-9)
        chans.append(sg.oaconvolve(v, ir, mode="full")[:n].astype(np.float32))
    return np.stack(chans).astype(np.float32)


def _fast_duck(v, sr, depth_db, smooth_s=0.12):
    a = np.abs(_mono(v))
    fast = _smooth(a, sr, 0.02)
    slow = _smooth(a, sr, float(smooth_s))
    d = np.maximum(fast, slow)
    env = np.clip(d / (np.percentile(d, 95) + 1e-9), 0.0, 1.0)
    depth_lin = 10 ** (-float(depth_db) / 20)
    return (1.0 - env * (1.0 - depth_lin)).astype(np.float32)


def _env10(v, sr):
    return _frame_db(_mono(v), sr, hop_s=0.01)


def _phrases(db, hs):
    return _active_mask(db), np.zeros_like(db, dtype=bool)
