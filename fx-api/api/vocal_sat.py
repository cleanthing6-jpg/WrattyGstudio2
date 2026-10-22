"""vocal_sat.py -- adaptive grade-1 VOCAL saturator (lead / backing / adlib).

Measures the vocal first (crest, brightness, sibilance, pitch, loudness), then plans the saturation from that:
  * 4x oversampled tube-style curve (asymmetric tanh: even + odd harmonics), DC-blocked, unity small-signal gain
  * works only on a band (about 1.6 x pitch up to 5-8 kHz): no low-mid mud, no saturated 's' sounds
  * drive is searched so the ADDED harmonic energy hits a target (about -30 dB for a lead), parallel mixed
  * guards: crest loss <= 1 dB, sibilance rise <= 1 dB, loudness matched, peaks held at original + 0.3 dB
Your engine's sat value (0.15 / 0.3 / 0.6 ...) maps to the target, so it stays a familiar control.

  process(voc, sr, role="lead", amount=0.3) -> (voc_out, report)
Pure numpy/scipy. voc: (n,) or (ch, n) float32.
"""
import numpy as np
import scipy.signal as sg

_OS = 4
ROLES = {
    "lead":    dict(hp=(150.0, 260.0), lp=7000.0, mix_max=0.50, amount=0.30),
    "backing": dict(hp=(220.0, 320.0), lp=5500.0, mix_max=0.50, amount=0.20),
    "adlib":   dict(hp=(200.0, 300.0), lp=6500.0, mix_max=0.50, amount=0.30),
}
LIMITS = dict(crest_drop_db=1.0, sib_rise_db=1.0, peak_rise_db=0.3)


# ----------------------------------------------------------------- helpers
def _mono(x):
    a = np.asarray(x, np.float32)
    return a.mean(axis=0) if a.ndim == 2 else a


def _sos(kind, f, sr, order=4):
    return sg.butter(order, f, kind, fs=sr, output="sos")


def _zp(x, sos):
    return sg.sosfiltfilt(sos, x).astype(np.float32)


def _db(v):
    return 20.0 * np.log10(np.asarray(v, np.float64) + 1e-12)


def _hfir(sr):
    return sg.firwin(255, min(21000.0, 0.46 * sr) / (sr * _OS / 2.0), window=("kaiser", 9.0))


def _frames(x, sr, hop_s=0.05):
    h = int(hop_s * sr); k = len(x) // h
    return 10 * np.log10((x[:k * h].reshape(k, h).astype(np.float64) ** 2).mean(1) + 1e-14)


def _f0_median(m, sr, frames=300):
    N = 2048; k = len(m) // N
    if k < 8: return None
    fr = m[:k * N].reshape(k, N); e = (fr ** 2).mean(1); idx = np.argsort(e)[::-1][:frames]
    lo, hi = int(sr / 500), int(sr / 70); out = []
    for i in idx:
        f = fr[i] * np.hanning(N); ac = np.fft.irfft(np.abs(np.fft.rfft(f, 2 * N)) ** 2)[:N]
        if ac[0] <= 0: continue
        ac = ac / ac[0]; lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] > 0.45: out.append(sr / lag)
    return float(np.median(out)) if len(out) >= 10 else None


# ----------------------------------------------------------------- 1. measure
def measure_vocal(v, sr):
    m = _mono(v)
    tot = _frames(m, sr); act = tot > (np.percentile(tot, 95) - 25.0)
    mid = _frames(_zp(m, _sos("bandpass", [250, 1000], sr, 2)), sr)
    hi = _frames(_zp(m, _sos("bandpass", [4000, 8000], sr, 2)), sr)
    air = _frames(_zp(m, _sos("bandpass", [8000, min(16000, 0.45 * sr)], sr, 2)), sr)
    sib = _frames(_zp(m, _sos("bandpass", [5000, 9000], sr, 2)), sr)
    pres = _frames(_zp(m, _sos("bandpass", [1500, 4000], sr, 2)), sr)
    w = int(0.4 * sr); k = len(m) // w
    fr = m[:k * w].reshape(k, w); r = np.sqrt((fr.astype(np.float64) ** 2).mean(1) + 1e-14); p = np.abs(fr).max(1)
    loud = _db(r) > np.percentile(_db(r), 50)
    crest = float(np.median((_db(p) - _db(r))[loud])) if loud.any() else 10.0
    ad = tot[act]
    return {"crest_short_db": round(crest, 2), "bright_db": round(float((hi - mid)[act].mean()), 1),
            "air_db": round(float((air - mid)[act].mean()), 1),
            "sib_p95_db": round(float(np.percentile((sib - pres)[act], 95)), 1),
            "active_rms_db": round(float(10 * np.log10((10 ** (ad / 10)).mean())), 2),
            "spread_db": round(float(np.percentile(ad, 90) - np.percentile(ad, 10)), 1),
            "f0": _f0_median(m, sr), "peak_db": round(float(_db(np.abs(np.asarray(v)).max())), 2)}


# ----------------------------------------------------------------- 2. plan
def plan(meas, role="lead", amount=None):
    R = ROLES.get(role, ROLES["lead"])
    amount = R["amount"] if amount is None else float(amount)
    target = float(np.interp(amount, [0, 0.15, 0.3, 0.6, 1.5], [-40, -34, -30, -26, -20]))
    target += float(np.interp(meas["crest_short_db"], [8, 14], [-3.0, 2.0]))   # squashed vocal: less, dynamic vocal: more
    lp, notes = R["lp"], []
    if meas["sib_p95_db"] > 5.0:
        lp = min(lp, 5000.0); target -= 1.5; notes.append("sibilant: saturation kept below 5 kHz")
    elif meas["sib_p95_db"] < 1.0 and meas["bright_db"] < -17.5:
        lp = max(lp, 8000.0); notes.append("dark vocal with soft s: harmonics allowed to reach the top")
    f0 = meas.get("f0") or 200.0
    hp = float(np.clip(1.6 * f0, *R["hp"]))
    bias = float(np.interp(meas["bright_db"], [-24, -14], [0.18, 0.08]))
    return {"role": role, "amount": amount, "target_db": round(float(np.clip(target, -42, -18)), 1), "hp": round(hp), "lp": round(lp),
            "bias": round(bias, 3), "mix_max": R["mix_max"], "notes": notes}


# ----------------------------------------------------------------- 3. saturator core
def _curve(x, drive, bias):
    t0 = np.tanh(bias)
    return (np.tanh(drive * x + bias) - t0) / (drive * (1.0 - t0 * t0))


def _sat_os(x, drive, bias, sr, chunk=441000, ctx=2048):
    H = _hfir(sr); n = len(x); out = np.empty(n, np.float32)
    for s in range(0, n, chunk):
        a0, b0 = max(0, s - ctx), min(n, s + chunk + ctx)
        seg = x[a0:b0].astype(np.float64)
        y = _curve(sg.resample_poly(seg, _OS, 1, window=H), drive, bias)
        dn = sg.resample_poly(y, 1, _OS, window=H)[:len(seg)]
        out[s:min(n, s + chunk)] = dn[s - a0: s - a0 + min(chunk, n - s)].astype(np.float32)
    return out


def _dcblock(x, sr):
    return sg.sosfilt(_sos("highpass", 15.0, sr, 2), x).astype(np.float32)


def _apply(x, sr, P, drive_db, mix):
    """one channel: band = [hp, lp] is saturated and mixed in parallel; everything else is untouched."""
    sos = _sos("bandpass", [P["hp"], min(P["lp"], 0.45 * sr)], sr, 3)
    band = _zp(x, sos); rest = x - band
    wet = _dcblock(_sat_os(band, 10 ** (drive_db / 20.0), P["bias"], sr), sr)
    return (rest + (1.0 - mix) * band + mix * wet).astype(np.float32)


def _peak_guard(x, ceiling, sr, look_ms=2.0):
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    a = np.asarray(x, np.float32); pk = np.abs(a).max(axis=0) if a.ndim == 2 else np.abs(a)
    L = max(3, int(look_ms / 1000.0 * sr)); env = maximum_filter1d(pk, size=2 * L + 1)
    g = np.minimum(1.0, ceiling / (env + 1e-12)).astype(np.float32); g = uniform_filter1d(g, size=2 * L + 1).astype(np.float32)
    g = np.minimum(g, np.minimum(1.0, ceiling / (pk + 1e-12)))
    return (a * g[None, :] if a.ndim == 2 else a * g).astype(np.float32)


def _band_energy_db(x, sr, lo, hi):
    m = _mono(x); N = 4096; k = (len(m) - N) // 2048 + 1
    idx = np.arange(N)[None, :] + 2048 * np.arange(k)[:, None]
    P = np.abs(np.fft.rfft(m[idx] * np.hanning(N), axis=1)) ** 2; f = np.fft.rfftfreq(N, 1 / sr)
    tot = 10 * np.log10(P[:, (f >= 100) & (f < 8000)].sum(1) + 1e-12); act = tot > np.percentile(tot, 95) - 25
    return float(10 * np.log10(P[act][:, (f >= lo) & (f < hi)].sum() + 1e-20))


# ----------------------------------------------------------------- 4. process
def process(voc, sr, role="lead", amount=None, mix=None):
    a = np.asarray(voc, np.float32)
    m = _mono(a)
    before = measure_vocal(a, sr)
    P = plan(before, role, amount)
    # probe = loudest 20 s
    w = int(20 * sr)
    if len(m) > w:
        step = int(sr * 2); starts = list(range(0, len(m) - w, step)); e = [float((m[s:s + w].astype(np.float64) ** 2).mean()) for s in starts]
        s0 = starts[int(np.argmax(e))]; probe = m[s0:s0 + w]
    else:
        probe = m
    sos = _sos("bandpass", [P["hp"], min(P["lp"], 0.45 * sr)], sr, 3)
    pband = _zp(probe, sos); pe = float((probe.astype(np.float64) ** 2).mean() + 1e-20)

    def added_db(drive_db, mx):
        wet = _sat_os(pband, 10 ** (drive_db / 20.0), P["bias"], sr)
        return float(10 * np.log10(((mx * (wet - pband)).astype(np.float64) ** 2).mean() / pe + 1e-20))

    def probe_stats(x):
        mm = measure_vocal(x, sr); return mm["crest_short_db"], mm["sib_p95_db"]
    c0, s0_ = probe_stats(probe)
    tries, mix_use, drive_use = [], 0.0, None
    cands = [mix] if mix is not None else [P["mix_max"] * f for f in (1.0, 0.7, 0.5, 0.35, 0.25)]
    for mx in cands:
        if mx <= 0: break
        lo, hi = -30.0, 24.0
        for _ in range(13):
            mid = 0.5 * (lo + hi)
            if added_db(mid, mx) < P["target_db"]: lo = mid
            else: hi = mid
        dr = 0.5 * (lo + hi)
        pr = _apply(probe, sr, P, dr, mx)
        pr = pr * np.float32(10 ** ((10 * np.log10(pe) - 10 * np.log10((pr.astype(np.float64) ** 2).mean() + 1e-20)) / 20.0))
        c1, s1 = probe_stats(pr)
        tries.append({"mix": round(mx, 2), "drive_db": round(dr, 1), "crest_drop_db": round(c0 - c1, 2), "sib_rise_db": round(s1 - s0_, 2)})
        if mix is not None or ((c0 - c1) <= LIMITS["crest_drop_db"] and (s1 - s0_) <= LIMITS["sib_rise_db"]):
            mix_use, drive_use = mx, dr; break
    if mix_use <= 0:
        rep = {"plan": P, "before": before, "applied": False, "note": "skipped: every amount cost crest or added sibilance beyond the limits", "mix_search": tries}
        return a, rep
    out = np.stack([_apply(c, sr, P, drive_use, mix_use) for c in a]) if a.ndim == 2 else _apply(a, sr, P, drive_use, mix_use)
    # level match on the vocal's own active level, then hold peaks
    mo = _mono(out)
    gain = float(np.clip(measure_vocal(a, sr)["active_rms_db"] - measure_vocal(mo, sr)["active_rms_db"], -1.0, 1.0))
    out = (out * np.float32(10 ** (gain / 20.0))).astype(np.float32)
    out = _peak_guard(out, float(np.abs(a).max()) * 10 ** (LIMITS["peak_rise_db"] / 20.0), sr)
    after = measure_vocal(out, sr)
    rep = {"plan": P, "applied": True, "drive_db": round(drive_use, 2), "mix": round(mix_use, 2), "mix_search": tries,
           "before": before, "after": after,
           "delta": {"active_rms_db": round(after["active_rms_db"] - before["active_rms_db"], 2), "peak_db": round(after["peak_db"] - before["peak_db"], 2),
                     "crest_short_db": round(after["crest_short_db"] - before["crest_short_db"], 2), "sib_p95_db": round(after["sib_p95_db"] - before["sib_p95_db"], 2),
                     "bright_db": round(after["bright_db"] - before["bright_db"], 2), "air_db": round(after["air_db"] - before["air_db"], 2)},
           "oversampling": _OS}
    return out, rep
