"""
fx_detect_extra.py -- short-gap reverb + delay detection for dense vocals (afrobeats etc.).
"""
import numpy as np
import scipy.signal as sg
from scipy import ndimage

HOP = 0.01
CAP = 0.85
REDUCE_AT = 0.55
BYPASS_AT = 0.90

def _front(voc, sr):
    x = np.asarray(voc, dtype=np.float64)
    m = x if x.ndim == 1 else x[:2].mean(0)
    sos = sg.butter(4, [150, 6000], btype="band", fs=sr, output="sos")
    b = sg.sosfilt(sos, m)
    n = int(HOP * sr); k = len(b) // n
    e = 20 * np.log10(np.sqrt((b[: k * n].reshape(k, n) ** 2).mean(1)) + 1e-9)
    top = float(np.percentile(e, 95))
    floor = max(float(np.percentile(e, 5)), top - 85.0)
    act = e > max(top - 32.0, floor + 12.0)
    act = ndimage.binary_closing(act, np.ones(4)); act = ndimage.binary_opening(act, np.ones(5))
    lab, nl = ndimage.label(act)
    runs = [(int(np.where(lab == j)[0][0]), int(np.where(lab == j)[0][-1])) for j in range(1, nl + 1)]
    return e, act, runs, floor

def reverb_short(e, runs, floor):
    rows = []
    for i, (a, z) in enumerate(runs):
        nxt = runs[i + 1][0] if i + 1 < len(runs) else len(e)
        if z - a < 20 or nxt - z - 2 < 25:
            continue
        w0 = max(a, z - 30)
        pk = e[w0:z + 1].max()
        t0 = w0 + int(np.where(e[w0:z + 1] >= pk - 6)[0][-1])
        seg = e[t0:min(nxt - 2, t0 + 60)]
        low = np.where(seg <= floor + 6)[0]
        if len(low):
            seg = seg[:low[0]]
        if len(seg) < 20:
            rows.append((0, 0.0, 0.0, 0.0, False)); continue
        tt = np.arange(3, len(seg)) * HOP; yy = seg[3:]
        sl, ic = np.polyfit(tt, yy, 1)
        r2 = 1 - ((yy - (sl * tt + ic)) ** 2).sum() / (((yy - yy.mean()) ** 2).sum() + 1e-9)
        drop = float(seg[0] - seg[-1])
        ok = (35.0 <= -sl <= 250.0) and r2 >= 0.8 and drop >= 6.0
        rows.append((len(seg), float(-sl), float(r2), drop, bool(ok)))
    out = {"present": False, "confidence": 0.0, "phrases_checked": len(rows), "rt60_s": None, "tail_db": None,
           "consistency": 0.0, "source": "short-gap"}
    if len(rows) < 2:
        out["why"] = "too few phrase endings with a 0.25 s+ gap to judge reverb"
        return out
    okm = np.array([r[4] for r in rows]); frac = float(okm.mean())
    out["consistency"] = round(frac, 2)
    if okm.sum() < 3:
        return out
    g = [r for r in rows if r[4]]
    sl = float(np.median([r[1] for r in g])); r2 = float(np.median([r[2] for r in g])); dr = float(np.median([r[3] for r in g]))
    c1 = (frac - 0.30) / 0.40
    c2 = (okm.sum() - 1) / 4.0
    c3 = (r2 - 0.70) / 0.25
    c4 = (dr - 5.0) / 10.0
    p = np.clip([c1, c2, c3, c4], 0, 1)
    conf = float(np.prod(p) ** 0.25) if (p > 0).all() else 0.0
    out.update(confidence=round(min(conf, CAP), 3), rt60_s=round(float(np.clip(60.0 / sl, 0.1, 5.0)), 2), tail_db=round(dr, 1))
    out["present"] = out["confidence"] >= REDUCE_AT
    return out

def delay_short(e, act, runs, floor, bpm=None):
    n = len(e); rs = []
    for i, (a, z) in enumerate(runs):
        nxt = runs[i + 1][0] if i + 1 < len(runs) else n
        g0, g1 = z + 4, min(nxt - 2, z + 90)
        if g1 - g0 < 14 or z - a < 20:
            continue
        G = e[g0:g1]
        if G.max() - floor < 8.0 or G.std() < 1.5:
            continue
        sc = np.full(90, -1.0); lv = np.zeros(90)
        for d in range(15, 90):
            s0 = g0 - d
            if s0 < 0:
                break
            H = e[s0:s0 + len(G)]
            if H.std() < 1.5:
                continue
            c = float(np.corrcoef(G, H)[0, 1])
            sc[d] = c; lv[d] = float(np.mean(G - H))
        rs.append((sc, lv))
    out = {"present": False, "confidence": 0.0, "delay_ms": None, "phrases_checked": len(rs), "source": "short-gap"}
    if len(rs) < 2:
        out["why"] = "too few gaps with energy in them to judge delay"
        return out
    S = np.array([r[0] for r in rs]); Lv = np.array([r[1] for r in rs])
    best = S.argmax(1); bsc = S.max(1)
    hist = np.bincount(best[bsc >= 0.6], minlength=90).astype(float)
    hist = ndimage.uniform_filter1d(hist, 3) * 3
    mode = int(np.argmax(hist))
    agree = (np.abs(best - mode) <= 2) & (bsc >= 0.6)
    frac = float(agree.mean())
    if agree.sum() < 3:
        return out
    lvl = float(np.median(Lv[agree, mode]))
    meanc = float(np.median(bsc[agree]))
    base = float(np.median(S[:, 15:90]))
    if not (-30.0 <= lvl <= -1.0):
        return out
    c1 = (frac - 0.30) / 0.40
    c2 = (agree.sum() - 2) / 4.0
    c3 = (meanc - 0.60) / 0.30
    c4 = (meanc - base - 0.30) / 0.30
    p = np.clip([c1, c2, c3, c4], 0, 1)
    conf = float(np.prod(p) ** 0.25) if (p > 0).all() else 0.0
    ms = mode * HOP * 1000.0
    synced = None
    if bpm and 50 <= bpm <= 210:
        fr = ms / (60000.0 / bpm)
        synced = any(abs(fr - q) / q < 0.06 for q in (0.25, 1 / 3, 0.5, 0.75, 1.0, 1.5))
    out.update(confidence=round(min(conf, CAP), 3), delay_ms=round(ms, 0), concentration=round(frac, 2),
               echo_level_db=round(lvl, 1), tempo_synced=synced)
    out["present"] = out["confidence"] >= REDUCE_AT
    return out

def augment(a, voc, sr, bpm=None):
    if not isinstance(a, dict) or "reverb" not in a:
        return a
    x = np.asarray(voc)
    if x.size == 0 or x.shape[-1] < sr * 12:
        return a
    e, act, runs, floor = _front(voc, sr)
    rv = reverb_short(e, runs, floor)
    dl = delay_short(e, act, runs, floor, bpm)
    a["extra"] = {"reverb": rv, "delay": dl}
    if rv["confidence"] > a["reverb"].get("confidence", 0.0):
        a["reverb"] = dict(a["reverb"], **{k: v for k, v in rv.items() if k != "why"})
    if dl["confidence"] > a["delay"].get("confidence", 0.0):
        a["delay"] = dict(a["delay"], **{k: v for k, v in dl.items() if k != "why"})
    ks = ("reverb", "delay", "stereo", "pitch")
    hits = [k for k in ks if a[k].get("confidence", 0) >= BYPASS_AT]
    maybe = [k for k in ks if REDUCE_AT <= a[k].get("confidence", 0) < BYPASS_AT]
    unsure = (a["reverb"].get("confidence", 0) == 0 and a["delay"].get("confidence", 0) == 0
              and (rv.get("why") or dl.get("why")))
    a["verdict"] = (("processed: " + ", ".join(hits)) if hits
                    else ("probably processed: " + ", ".join(maybe)) if maybe
                    else "unknown (too few gaps to judge reverb/delay)" if unsure
                    else "dry (no effects found)")
    return a
