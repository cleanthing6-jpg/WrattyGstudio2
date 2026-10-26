import numpy as np
from scipy import signal
from vocal_dsp import NOTE_NAMES, _KMAJ, _KMIN
_N = 16384
def _middle(x, sr, max_seconds):
    x = np.asarray(x, dtype=np.float64)
    if len(x) > max_seconds * sr:
        mid, h = len(x) // 2, int(max_seconds * sr / 2); x = x[mid - h: mid + h]
    return x
def detect_tuning_cents(x, sr, max_seconds=75):
    x = _middle(x, sr, max_seconds); f, _, S = signal.stft(x, sr, window="hann", nperseg=_N, noverlap=_N // 2); M = np.abs(S); sel = np.where((f >= 120) & (f <= 2000))[0]; z, wsum = 0j, 0.0
    for t in range(M.shape[1]):
        mag = M[:, t]; seg = mag[sel]
        if seg.max() <= 0: continue
        pk, _ = signal.find_peaks(seg, height=0.15 * seg.max())
        for k in pk:
            i = sel[k]
            if i < 1 or i >= len(f) - 1: continue
            a, b, c = np.log(mag[i - 1] + 1e-12), np.log(mag[i] + 1e-12), np.log(mag[i + 1] + 1e-12); d = 0.5 * (a - c) / (a - 2 * b + c + 1e-12)
            fr = (i + d) * (f[1] - f[0]); semis = 69 + 12 * np.log2(fr / 440.0); w = mag[i]; z += w * np.exp(2j * np.pi * semis); wsum += w
    if wsum == 0: return 0.0, 0.0
    return float(np.angle(z) / (2 * np.pi) * 100.0), float(abs(z) / wsum)
def _key_from_chroma(x, sr, tuning_cents, max_seconds):
    x = _middle(x, sr, max_seconds); f, _, S = signal.stft(x, sr, window="hann", nperseg=_N, noverlap=_N // 2); mag = np.sqrt(np.abs(S)).mean(axis=1); sel = (f >= 55) & (f <= 2000)
    midi = np.round(69 + 12 * np.log2(f[sel] / 440.0) - tuning_cents / 100.0).astype(int); pc = np.zeros(12); np.add.at(pc, midi % 12, mag[sel]); pc = pc / pc.sum()
    scores = sorted(((np.corrcoef(pc, np.roll(prof, t))[0, 1], t, m) for t in range(12) for m, prof in (("major", _KMAJ), ("minor", _KMIN))), reverse=True)
    return f"{NOTE_NAMES[scores[0][1]]} {scores[0][2]}", float(scores[0][0] - scores[1][0])
def analyse_beat(x, sr, max_seconds=75):
    cents, conf = detect_tuning_cents(x, sr, max_seconds); use = conf >= 0.35 and abs(cents) >= 8; ref = float(np.clip(cents, -50, 50)) if use else 0.0
    key, margin = _key_from_chroma(x, sr, ref, max_seconds)
    return dict(key=key, key_margin=margin, tuning_cents=cents, tuning_conf=conf, ref_cents=ref)
