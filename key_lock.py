"""key_lock.py - decide WHICH NOTES the tuner may snap to. Numpy only."""
import numpy as np

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MAJOR = np.array([0, 2, 4, 5, 7, 9, 11])
MINOR = np.array([0, 2, 3, 5, 7, 8, 10])


def _mono(x):
    x = np.asarray(x, dtype=np.float32)
    return x.mean(0) if x.ndim == 2 else x


def chroma(x, sr, ref_a=440.0, fmin=50.0, fmax=2000.0, n_fft=8192, hop=4096, max_sec=120):
    m = _mono(x)[: int(max_sec * sr)]
    if len(m) < n_fft:
        m = np.pad(m, (0, n_fft - len(m)))
    win = np.hanning(n_fft).astype(np.float32)
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    sel = np.where((freqs >= fmin) & (freqs <= fmax))[0]
    midi = 69.0 + 12.0 * np.log2(freqs[sel] / ref_a)
    frames = []
    for s in range(0, len(m) - n_fft + 1, hop):
        mag = np.abs(np.fft.rfft(m[s:s + n_fft] * win))[sel]
        if mag.max() < 1e-6:
            continue
        pk = (mag[1:-1] > mag[:-2]) & (mag[1:-1] > mag[2:]) & (mag[1:-1] > 0.05 * mag.max())
        idx = np.where(pk)[0] + 1
        frames.append((midi[idx], mag[idx]))
    if not frames:
        return np.zeros(12), 0.0
    dev = np.concatenate([f[0] - np.round(f[0]) for f in frames])
    wt = np.concatenate([f[1] for f in frames])
    ang = 2 * np.pi * dev
    tun = np.arctan2((wt * np.sin(ang)).sum(), (wt * np.cos(ang)).sum()) / (2 * np.pi)
    ch = np.zeros(12)
    for mi, mg in frames:
        pcs = np.round(mi - tun).astype(int) % 12
        fr = np.zeros(12)
        np.add.at(fr, pcs, np.sqrt(mg))
        ch += fr / (fr.sum() + 1e-9)
    return ch / (ch.max() + 1e-9), float(tun * 100.0)


def _set_scores(w):
    sc = np.zeros(12)
    for t in range(12):
        sc[t] = w[(MAJOR + t) % 12].sum() / (w.sum() + 1e-9)
    return sc


def detect_allowed(beat_chroma, vocal_chroma=None, extra_thresh=0.45, floor=0.08):
    w = np.asarray(beat_chroma, float).copy()
    src = "beat"
    if w.sum() < 1e-6 or (w > 0.15).sum() < 4:
        if vocal_chroma is None:
            return dict(allowed=np.ones(12, bool), name="unknown", confidence=0.0,
                        parallel_margin=0.0, source="none")
        w = np.asarray(vocal_chroma, float) + 0.5 * w
        src = "vocal"
    sc = _set_scores(w)
    disagree = False
    if vocal_chroma is not None and src != "vocal":
        disagree = int(np.argmax(_set_scores(np.asarray(vocal_chroma, float)))) != int(np.argmax(_set_scores(np.asarray(beat_chroma, float))))
    order = np.argsort(sc)[::-1]
    best, second = order[0], order[1]
    near = [int(t) for t in order[1:4] if sc[best] - sc[t] < 0.02 and ((t - best) % 12) in (5, 7)]
    rest = [float(sc[t]) for t in order[1:] if int(t) not in near]
    margin = float(sc[best] - (max(rest) if rest else sc[second]))
    allowed = np.zeros(12, bool)
    allowed[(MAJOR + best) % 12] = True
    for t in near:
        allowed[(MAJOR + t) % 12] = True
    allowed |= (np.asarray(beat_chroma) >= extra_thresh)
    if src != "vocal":
        weak = np.asarray(beat_chroma) < floor
        for pc in np.where(weak & allowed)[0]:
            allowed[pc] = False
    if allowed.sum() < 5:
        allowed[(MAJOR + best) % 12] = True
    rel_min = (best + 9) % 12
    conf = float(np.clip(sc[best] * 1.0 - 0.5 * (1 - min(1, margin / 0.08)) * 0.2, 0, 1))
    conf = float(np.clip(conf * (0.6 + 0.4 * min(1, margin / 0.06)), 0, 1))
    if disagree:
        conf *= 0.5
    cands = [f"{NOTES[t]} major / {NOTES[(t + 9) % 12]} minor" for t in order[:3]]
    return dict(allowed=allowed, name=f"{NOTES[best]} major / {NOTES[rel_min]} minor",
                confidence=conf, parallel_margin=margin, source=src, candidates=cands)


def parse_key(s):
    s = s.strip().replace("\u266f", "#").replace("\u266d", "b")
    root, rest = s[0].upper(), s[1:]
    acc = 0
    if rest[:1] == "#":
        acc, rest = 1, rest[1:]
    elif rest[:1] == "b":
        acc, rest = -1, rest[1:]
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[root]
    t = (base + acc) % 12
    minor = rest.strip().lower().startswith(("m", "min")) and not rest.strip().lower().startswith("maj")
    a = np.zeros(12, bool)
    a[((MINOR if minor else MAJOR) + t) % 12] = True
    return dict(allowed=a, name=f"{NOTES[t]} {'minor' if minor else 'major'}",
                confidence=1.0, parallel_margin=1.0, source="manual", candidates=[],
                mode="scale", force_key=True, apply_offset=True, needs_user_key=False)


def key_chroma(x, sr):
    try:
        from scipy import signal as _sg
        x = _sg.sosfilt(_sg.butter(4, [250, 2500], btype="band", fs=sr, output="sos"), _mono(x)).astype(np.float32)
        return chroma(x, sr, fmin=250.0, fmax=2500.0)[0]
    except Exception:
        return chroma(x, sr)[0]


def resolve(manual=None, beat=None, vocal=None, sr=44100, min_conf=0.55):
    if manual:
        return parse_key(manual)
    bc = key_chroma(beat, sr) if beat is not None else None
    vc = chroma(vocal, sr)[0] if vocal is not None else None
    if bc is not None:
        r = detect_allowed(bc, vc)
        r["candidates"] = r.get("candidates", [])
        if r["confidence"] >= min_conf:
            r.update(mode="scale", force_key=True, apply_offset=True, needs_user_key=False)
            return r
        return dict(allowed=np.ones(12, bool), name="unsure", confidence=r["confidence"],
                    parallel_margin=r["parallel_margin"], source="safe-chromatic",
                    candidates=r["candidates"], mode="limited", max_pull_cents=25.0,
                    force_key=False, apply_offset=False, needs_user_key=True)
    elif vc is not None:
        r = detect_allowed(np.zeros(12), vc)
        if r["confidence"] >= min_conf:
            return r
    return dict(allowed=np.ones(12, bool), name="unsure", confidence=0.0,
                parallel_margin=0.0, source="safe-chromatic", candidates=[], mode="limited",
                max_pull_cents=25.0, force_key=False, apply_offset=False, needs_user_key=True)


def estimate_offset(f0_hz, allowed, ref_a=440.0, span=100.0, step=2.5, sigma=35.0, min_conf=0.15):
    f0 = np.asarray(f0_hz, float)
    f0 = f0[np.isfinite(f0) & (f0 > 0)]
    allowed = np.asarray(allowed, bool)
    if f0.size < 50 or not allowed.any():
        return 0.0, 0.0
    midi_c = 100.0 * (69.0 + 12.0 * np.log2(f0 / ref_a))
    idx = np.where(allowed)[0]
    offs = np.arange(-span, span + step, step)
    sc = np.zeros(len(offs))
    for i, o in enumerate(offs):
        pc = np.mod((midi_c + o) / 100.0, 12.0)
        d = np.abs(((pc[:, None] - idx[None, :] + 6.0) % 12.0) - 6.0).min(axis=1) * 100.0
        sc[i] = np.mean(np.exp(-0.5 * (d / sigma) ** 2)) - 0.0002 * abs(o)
    b = int(np.argmax(sc))
    far = np.abs(offs - offs[b]) > 40.0
    second = sc[far].max() if far.any() else 0.0
    conf = float(np.clip((sc[b] - second) / (sc[b] + 1e-9), 0.0, 1.0))
    if conf < min_conf:
        return 0.0, conf
    return float(offs[b]), conf


def _yin(x, sr, fmin=70.0, fmax=900.0, hop_s=0.02, W=1024, thr=0.15):
    hop = int(sr * hop_s); tmax = int(sr / fmin) + 1; tmin = max(2, int(sr / fmax))
    n = W + tmax; nfft = 1 << int(np.ceil(np.log2(2 * n)))
    cs = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    f0, cm_out = [], []
    for s in range(0, len(x) - n, hop):
        e0 = cs[s + W] - cs[s]
        if np.sqrt(e0 / W) < 0.01:
            f0.append(np.nan); cm_out.append(1.0); continue
        fr = x[s:s + n].astype(np.float64)
        r = np.fft.irfft(np.fft.rfft(fr, nfft) * np.conj(np.fft.rfft(fr[:W], nfft)), nfft)[:tmax]
        e = cs[s + W + np.arange(tmax)] - cs[s + np.arange(tmax)]
        d = e0 + e - 2 * r; d[0] = 0
        cm = np.ones(tmax); cm[1:] = d[1:] * np.arange(1, tmax) / np.maximum(np.cumsum(d[1:]), 1e-12)
        t = None
        for tau in range(tmin, tmax - 1):
            if cm[tau] < thr:
                while tau + 1 < tmax - 1 and cm[tau + 1] < cm[tau]:
                    tau += 1
                t = tau; break
        if t is None:
            f0.append(np.nan); cm_out.append(float(cm[tmin:].min())); continue
        a, b, c = cm[t - 1], cm[t], cm[t + 1]; den = a - 2 * b + c
        tau = t + 0.5 * (a - c) / den if abs(den) > 1e-12 else t
        f0.append(sr / tau); cm_out.append(float(b))
    return np.array(f0), np.array(cm_out)


def estimate_global_offset(x, sr, allowed, min_conf=0.15):
    from scipy import signal as _sg
    m = _mono(x)
    tsr = 22050
    if sr != tsr:
        from math import gcd
        g = gcd(int(sr), tsr)
        m = _sg.resample_poly(m, tsr // g, int(sr) // g).astype(np.float32)
    f0, cm = _yin(m, tsr)
    ok = np.isfinite(f0) & (cm < 0.12)
    return estimate_offset(f0[ok], allowed, min_conf=min_conf)
