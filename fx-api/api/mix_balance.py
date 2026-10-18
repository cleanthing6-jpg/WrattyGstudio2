"""
mix_balance.py -- per-song tonal balance planner for the automix (Afrobeats).
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

CENTERS = np.array([31.5, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0, 200.0, 250.0, 315.0, 400.0,
                    500.0, 630.0, 800.0, 1000.0, 1250.0, 1600.0, 2000.0, 2500.0, 3150.0, 4000.0,
                    5000.0, 6300.0, 8000.0, 10000.0, 12500.0, 16000.0])
REF_MEDIAN = np.array([-26.1, -15.5, -8.6, -8.8, -11.1, -11.7, -11.6, -13.9, -14.2, -14.5, -15.2,
                       -12.9, -14.3, -14.9, -16.6, -19.3, -18.5, -18.4, -21.8, -24.7, -24.5, -24.9,
                       -26.2, -25.7, -26.5, -26.6, -30.4, -36.0])

MAX_SHELF_DB, MIN_SHELF_DB = 7.0, -3.0
MAX_BELL_DB, MIN_BELL_DB = 3.0, -2.0
MAX_CUT_DB, MAX_BOOST_DB = -3.0, 1.0

def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=0) if x.ndim == 2 else x

def _ltas(m, sr):
    f, P = sg.welch(m, sr, nperseg=16384)
    edges = np.concatenate([[CENTERS[0] / 2 ** (1 / 6)], CENTERS * 2 ** (1 / 6)])
    B = np.array([P[(f >= edges[i]) & (f < edges[i + 1])].sum() for i in range(len(CENTERS))])
    return 10 * np.log10(B / B.sum() + 1e-20)

def _gap(m, sr):
    g = REF_MEDIAN - _ltas(m, sr)
    anchor = np.median(g[(CENTERS >= 160) & (CENTERS <= 8000)])
    return ndimage.gaussian_filter1d(g - anchor, 1.0, mode="nearest")

def _med(g, lo, hi):
    return float(np.median(g[(CENTERS >= lo) & (CENTERS <= hi)]))

def plan(mixed, sr):
    m = _mono(mixed)
    if m.shape[0] < sr * 2 or np.abs(m).max() < 1e-6:
        return {"shelf80_db": MAX_SHELF_DB, "bell125_db": MAX_BELL_DB, "cut250_db": -2.5, "cut420_db": -2.0,
                "cut550_db": -1.0, "vocal_hot_db": 0.0, "note": "input too short/silent: legacy fixed values"}
    g = _gap(m, sr)
    shelf = float(np.clip(0.9 * _med(g, 40, 80), MIN_SHELF_DB, MAX_SHELF_DB))
    bell = float(np.clip(0.5 * _med(g, 100, 160), MIN_BELL_DB, MAX_BELL_DB))
    cuts = []
    for lo, hi in ((200, 315), (400, 400), (500, 630)):
        cuts.append(float(np.clip(0.8 * _med(g, lo, hi), MAX_CUT_DB, MAX_BOOST_DB)))
    return {"shelf80_db": round(shelf, 2), "bell125_db": round(bell, 2),
            "cut250_db": round(cuts[0], 2), "cut420_db": round(cuts[1], 2), "cut550_db": round(cuts[2], 2),
            "vocal_hot_db": round(float(-_med(g, 800, 2500)), 2),
            "gap_db": {str(int(c)): round(float(v), 1) for c, v in zip(CENTERS, g) if 40 <= c <= 2500}}

def vocal_trim_db(p):
    hot = float(p.get("vocal_hot_db", 0.0))
    return float(np.clip((hot - 1.0) * 0.7, 0.0, 3.0)) if hot > 2.0 else 0.0
