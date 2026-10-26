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
        if mag.max() < 1e-6: continue
        pk = (mag[1:-1] > mag[:-2]) & (mag[1:-1] > mag[2:]) & (mag[1:-1] > 0.05 * mag.max())
        idx = np.where(pk)[0] + 1
        frames.append((midi[idx], mag[idx]))
    if not frames: return np.zeros(12), 0.0
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
            return dict(allowed=np.ones(12, bool), name="unknown", confidence=0.0, parallel_margin=0.0, source="none")
        w = np.asarray(vocal_chroma, float) + 0.5 * w; src = "vocal"
    elif vocal_chroma is not None:
        w = w + 0.25 * np.asarray(vocal_chroma, float)
        src = "beat+vocal"
    sc = _set_scores(w)
    disagree = False
    if vocal_chroma is not None and src != "vocal":
        disagree = int(np.argmax(_set_scores(np.asarray(vocal_chroma, float)))) != int(np.argmax(_set_scores(np.asarray(beat_chroma, float))))
    order = np.argsort(sc)[::-1]
    best, second = order[0], order[1]
    margin = float(sc[best] - sc[second])
    allowed = np.zeros(12, bool)
    allowed[(MAJOR + best) % 12] = True
    allowed |= (np.asarray(beat_chroma) >= extra_thresh)
    if src != "vocal":
        weak = np.asarray(beat_chroma) < floor
        for pc in np.where(weak & allowed)[0]:
            allowed[pc] = False
    if allowed.sum() < 5: allowed[(MAJOR + best) % 12] = True
    rel_min = (best + 9) % 12
    conf = float(np.clip(sc[best] * 1.0 - 0.5 * (1 - min(1, margin / 0.08)) * 0.2, 0, 1))
    conf = float(np.clip(conf * (0.6 + 0.4 * min(1, margin / 0.06)), 0, 1))
    if disagree: conf *= 0.5
    return dict(allowed=allowed, name=f"{NOTES[best]} major / {NOTES[rel_min]} minor", confidence=conf, parallel_margin=margin, source=src)

def parse_key(s):
    s = s.strip().replace("♯", "#").replace("♭", "b")
    root, rest = s[0].upper(), s[1:]
    acc = 0
    if rest[:1] == "#": acc, rest = 1, rest[1:]
    elif rest[:1] == "b": acc, rest = -1, rest[1:]
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[root]
    t = (base + acc) % 12
    minor = rest.strip().lower().startswith(("m", "min")) and not rest.strip().lower().startswith("maj")
    a = np.zeros(12, bool)
    a[((MINOR if minor else MAJOR) + t) % 12] = True
    return dict(allowed=a, name=f"{NOTES[t]} {'minor' if minor else 'major'}", confidence=1.0, parallel_margin=1.0, source="manual")

def resolve(manual=None, beat=None, vocal=None, sr=44100, min_conf=0.55):
    if manual: return parse_key(manual)
    bc = chroma(beat, sr)[0] if beat is not None else None
    vc = chroma(vocal, sr)[0] if vocal is not None else None
    if bc is not None:
        r = detect_allowed(bc, vc)
        if r["confidence"] >= min_conf: return r
    elif vc is not None:
        r = detect_allowed(np.zeros(12), vc)
        if r["confidence"] >= min_conf: return r
    return dict(allowed=np.ones(12, bool), name="unsure", confidence=0.0, parallel_margin=0.0, source="safe-chromatic", max_pull_cents=35.0)


def estimate_global_offset(x, sr, allowed, max_sec=120):
    """Convenience wrapper: extract peak f0 from audio, compute cents offset to align to allowed notes."""
    m = _mono(x)[: int(max_sec * sr)]
    if len(m) < 8192:
        m = np.pad(m, (0, 8192 - len(m)))
    win = np.hanning(8192).astype(np.float32)
    freqs = np.fft.rfftfreq(8192, 1.0 / sr)
    sel = np.where((freqs >= 50) & (freqs <= 2000))[0]
    midi_vals = 69.0 + 12.0 * np.log2(freqs[sel] / 440.0)
    f0_all = []
    for s_idx in range(0, len(m) - 8192 + 1, 4096):
        mag = np.abs(np.fft.rfft(m[s_idx:s_idx + 8192] * win))[sel]
        if mag.max() < 1e-6:
            continue
        pk = (mag[1:-1] > mag[:-2]) & (mag[1:-1] > mag[2:]) & (mag[1:-1] > 0.05 * mag.max())
        idx = np.where(pk)[0] + 1
        f0_all.append(440.0 * 2 ** ((midi_vals[idx] - 69.0) / 12.0))
    if not f0_all:
        return 0.0, 0.0
    f0_hz = np.concatenate(f0_all)
    return estimate_offset(f0_hz, allowed)
