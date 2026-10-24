"""Key detection from the beat/instrumental (chroma + Krumhansl profiles)."""
import numpy as np
from scipy import signal
from vocal_dsp import NOTE_NAMES, _KMAJ, _KMIN


def detect_key(x, sr, max_seconds=75):
    """returns (key_string, margin). margin is small when the call is uncertain."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) > max_seconds * sr:
        mid = len(x) // 2
        h = int(max_seconds * sr / 2)
        x = x[mid - h: mid + h]
    n = 16384
    f, _, S = signal.stft(x, sr, window="hann", nperseg=n, noverlap=n // 2)
    mag = np.sqrt(np.abs(S)).mean(axis=1)
    sel = (f >= 55) & (f <= 2000)
    midi = np.round(69 + 12 * np.log2(f[sel] / 440.0)).astype(int)
    pc = np.zeros(12)
    np.add.at(pc, midi % 12, mag[sel])
    pc = pc / pc.sum()
    scores = sorted(
        ((np.corrcoef(pc, np.roll(prof, t))[0, 1], t, m)
         for t in range(12) for m, prof in (("major", _KMAJ), ("minor", _KMIN))),
        reverse=True)
    return f"{NOTE_NAMES[scores[0][1]]} {scores[0][2]}", float(scores[0][0] - scores[1][0])
