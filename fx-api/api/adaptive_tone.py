"""adaptive_tone.py -- per-song vocal tone corrector for a multi-user automix.
Targets come from six commercial Afrobeats vocal stems.
Only corrects a band when the vocal is OUTSIDE the reference range. Clamped."""
import numpy as np
import scipy.signal as sg

REF = {"b60_100": (-53.6, -43.7), "b100_150": (-29.8, -16.5), "b150_250": (-14.4, -6.1),
       "b5_9k": (-21.2, -15.3), "sib": (-15.8, -6.1)}


def _peak(f0, g, q, sr):
    A = 10 ** (g / 40.0); w0 = 2 * np.pi * f0 / sr; al = np.sin(w0) / (2 * q); c = np.cos(w0)
    return sg.tf2sos([1 + al * A, -2 * c, 1 - al * A], [1 + al / A, -2 * c, 1 - al / A])


def _shelf(f0, g, sr, high, s=0.8):
    A = 10 ** (g / 40.0); w0 = 2 * np.pi * f0 / sr; c = np.cos(w0)
    al = np.sin(w0) / 2 * np.sqrt((A + 1 / A) * (1 / s - 1) + 2); sq = 2 * np.sqrt(A) * al
    if high:
        b = [A * ((A + 1) + (A - 1) * c + sq), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - sq)]
        a = [(A + 1) - (A - 1) * c + sq, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - sq]
    else:
        b = [A * ((A + 1) - (A - 1) * c + sq), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - sq)]
        a = [(A + 1) + (A - 1) * c + sq, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - sq]
    return sg.tf2sos(b, a)


def measure(voc, sr):
    x = np.asarray(voc, dtype=np.float64)
    m = x.mean(axis=0) if x.ndim == 2 else x
    n = int(0.02 * sr); k = len(m) // n
    fr = m[: k * n].reshape(k, n)
    e = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    act = e > (np.percentile(e, 95) - 40.0)
    seg = fr[act].reshape(-1) if act.sum() > 10 else m
    f, P = sg.welch(seg, sr, nperseg=16384)
    B = lambda a, b: P[(f >= a) & (f < b)].sum() + 1e-20
    ref = B(150, 9000)
    db = lambda a, b: 10 * np.log10(B(a, b) / ref)
    return {"b60_100": db(60, 100), "b100_150": db(100, 150), "b150_250": db(150, 250),
            "b5_9k": db(5000, 9000), "sib": 10 * np.log10(B(5000, 9000) / B(1000, 4000))}


def plan(voc, sr):
    m = measure(voc, sr)
    hpf = 90.0 if m["b60_100"] > REF["b60_100"][1] else 70.0
    boom = m["b100_150"] - REF["b100_150"][1]
    low_cut = -float(np.clip(boom * 0.8 + 1.0, 0.0, 3.0)) if boom > 0 else 0.0
    box = m["b150_250"] - REF["b150_250"][1]
    dip = -float(np.clip(box * 0.7 + 1.0, 0.0, 3.0)) if box > 0 else 0.0
    gap = REF["b5_9k"][0] + 2.0 - m["b5_9k"]
    cap = 4.0 if m["sib"] < -12.0 else 2.0 if m["sib"] < -9.0 else 0.0
    shelf = float(np.clip(gap * 0.8, 0.0, cap)) if gap > 0 else 0.0
    return {"hpf_hz": hpf, "low_shelf_db": low_cut, "dip_db": dip,
            "hi_shelf_db": shelf, "measured": m}


def tone_correct(voc, sr, return_plan=False):
    p = plan(voc, sr)
    sos = [sg.butter(4, p["hpf_hz"], btype="highpass", fs=sr, output="sos")]
    if p["low_shelf_db"] < -0.2: sos.append(_shelf(130.0, p["low_shelf_db"], sr, high=False))
    if p["dip_db"] < -0.2: sos.append(_peak(200.0, p["dip_db"], 0.9, sr))
    if p["hi_shelf_db"] > 0.2: sos.append(_shelf(6500.0, p["hi_shelf_db"], sr, high=True))
    y = sg.sosfilt(np.vstack(sos), np.asarray(voc, dtype=np.float32), axis=-1).astype(np.float32)
    return (y, p) if return_plan else y
