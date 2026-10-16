"""adaptive_ambience.py -- per-song reverb chooser. Pure numpy/scipy, no state."""
import numpy as np
import scipy.signal as sig

TARGET_DB = {"lead": -20.0, "adlib": -17.0, "backing": -23.0}
STYLE_OFFSET_DB = {"dry": -5.0, "clean": 0.0, "spacious": +3.5}
MELT = {"dry": 0.3, "clean": 0.8, "spacious": 1.0}


def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    return x.mean(axis=0) if x.ndim == 2 and x.shape[0] <= 2 else (x.mean(axis=1) if x.ndim == 2 else x)


def _frames_db(m, sr, win=0.02):
    n = max(1, int(win * sr))
    k = len(m) // n
    e = np.sqrt((m[: k * n].reshape(k, n) ** 2).mean(axis=1) + 1e-18)
    return 20 * np.log10(e)


def analyze_vocal(voc, sr):
    m = _mono(voc)
    edb = _frames_db(m, sr)
    peak_db = 20 * np.log10(np.abs(m).max() + 1e-12)
    thr = max(np.percentile(edb, 95) - 35.0, -70.0)
    act = edb > thr
    active_frac = float(act.mean())
    runs, cur = [], 0
    for a in act:
        if not a:
            cur += 1
        elif cur:
            runs.append(cur); cur = 0
    gap_s = float(np.median(runs) * 0.02) if runs else 0.0
    n = int(0.02 * sr)
    k = len(m) // n
    fr = m[: k * n].reshape(k, n)[act[:k]]
    if len(fr) < 10:
        fr = m[: k * n].reshape(k, n)
    f, P = sig.welch(fr.reshape(-1), sr, nperseg=4096)
    band = lambda a, b: P[(f >= a) & (f < b)].sum() + 1e-18
    lowmid = band(250, 500) / band(500, 5000)
    bright = 10 * np.log10(band(5000, 9000) / band(1000, 4000))
    return dict(peak_db=float(peak_db), active_frac=active_frac, gap_s=gap_s,
                lowmid=float(lowmid), bright_db=float(bright),
                hot_input=bool(peak_db > -0.3))


def _adaptive_target(role, style, a):
    """Base target by role/style, then nudge from the vocal's own measurements.
    Bright vocals -> less wet (avoids harshness).
    Dark vocals -> more wet (adds needed air).
    Dense vocals -> more wet (so reverb is heard through the words).
    Sparse vocals -> less wet (reverb already blooms in gaps).
    """
    base = TARGET_DB.get(role, -20.0) + STYLE_OFFSET_DB.get(style, 0.0)
    b = float(a["bright_db"])
    if b > -14.0:      base -= 2.0
    elif b < -22.0:    base += 2.0
    g = float(a["gap_s"])
    if g > 0.6:        base -= 1.5
    elif g < 0.2:      base += 1.5
    return float(np.clip(base, -26.0, -12.0))


def choose_params(voc, sr, bpm, role="lead", style="clean"):
    a = analyze_vocal(voc, sr)
    beat = 60.0 / float(np.clip(bpm or 100.0, 70.0, 140.0))
    tail = np.clip(beat * 1.0, 0.40, 0.65)
    if a["active_frac"] > 0.80 or a["gap_s"] < 0.15:
        tail *= 0.80
    if style == "spacious":
        tail = min(tail * 1.25, 0.85)
    if style == "dry":
        tail *= 0.75
    predelay = float(np.clip(beat * 1000 / 12.0, 35.0, 60.0))
    hpf = float(np.clip(500 + (a["lowmid"] - 0.30) * 600, 500, 750))
    lpf = float(np.clip(6500 - (a["bright_db"] + 12.0) * 150, 5500, 7500))
    return dict(melt=MELT.get(style, 0.8), ir_len_s=float(tail),
                predelay_ms=predelay, hpf_hz=hpf, lpf_hz=lpf,
                target_db=_adaptive_target(role, style, a),
                analysis=a)


def calibrate_send(dry, wet, target_db, lo=0.03, hi=0.25):
    d, w = _mono(dry), _mono(wet)
    n = min(len(d), len(w)); d, w = d[:n], w[:n]
    dd = _frames_db(d, 44100)
    act = dd > max(np.percentile(dd, 95) - 35.0, -70.0)
    fr = 882
    k = n // fr
    dr = np.sqrt((d[: k * fr].reshape(k, fr) ** 2).mean(axis=1))[act[:k]]
    wr = np.sqrt((w[: k * fr].reshape(k, fr) ** 2).mean(axis=1))[act[:k]]
    d_rms = np.sqrt((dr ** 2).mean() + 1e-18)
    w_rms = np.sqrt((wr ** 2).mean() + 1e-18)
    send = (10 ** (target_db / 20.0)) * d_rms / w_rms
    return float(np.clip(send, lo, hi))


def qc_ambience(dry, wet_scaled, sr):
    d, w = _mono(dry), _mono(wet_scaled)
    n = min(len(d), len(w)); d, w = d[:n], w[:n]
    dd = _frames_db(d, sr); wd = _frames_db(w, sr)
    act = dd > max(np.percentile(dd, 95) - 35.0, -70.0)
    gap = ~act
    out = dict(wet_vs_dry_db=float(np.mean(wd[act]) - np.mean(dd[act])) if act.any() else None)
    out["gap_wet_db"] = float(np.percentile(wd[gap], 90)) if gap.any() else None
    out["ok"] = bool(out["wet_vs_dry_db"] is not None and -26 <= out["wet_vs_dry_db"] <= -14)
    return out

# ── Adaptive vocal tone: lowmid measurement -> body/mud adjustment ──
VOCAL_NEUTRAL_LOWMID = 0.67   # measured from 6 real refs (FOLA 0.53, Burna 0.75, Davido 0.66, Rema 1.21)
VOCAL_LOWMID_MUD_SLOPE = 10.0
VOCAL_LOWMID_BODY_SLOPE = 7.0


def tune_vocal(voc, sr, role="lead"):
    """Return adaptive body_db and mud_cap from the vocal's low-mid content.

    Muddy vocal  -> deeper mud cut, thinner body shelf
    Thin vocal   -> shallower mud cut, more body shelf
    Neutral      -> preset defaults (body 2.0 dB, mud 2.5 dB)
    All values in dB. Ratio-based, so level-independent -> multi-user safe.
    """
    try:
        a = analyze_vocal(voc, sr)
        lowmid = float(a["lowmid"])
    except Exception:
        return None

    delta = lowmid - VOCAL_NEUTRAL_LOWMID       # + muddy, - thin
    mud_extra  = float(np.clip(delta * VOCAL_LOWMID_MUD_SLOPE,  -1.5, +3.0))
    body_delta = float(np.clip(-delta * VOCAL_LOWMID_BODY_SLOPE, -2.0, +1.0))

    return {
        "body_db": float(np.clip(2.0 + body_delta, 0.0, 4.0)),
        "mud_cap": float(np.clip(2.5 + mud_extra, 1.0, 6.0)),
        "lowmid": lowmid,
    }

