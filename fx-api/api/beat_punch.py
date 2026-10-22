"""beat_punch.py -- adaptive KICK PUNCH for the beat bus (kick only: no saturator, no tone change).

The beat's crest factor and kick are measured BEFORE any punch is applied. The measurement decides how much punch
(0-3 dB, often 0) is added, and guards make sure the kick is never made worse: beat power is matched, peaks are
held at the original peak + 0.3 dB, and nothing is added if there are no real kicks.

  process(beat, sr, preset="afrobeats") -> (beat_out, report)
  measure_beat(beat, sr) / decide(meas, preset) / kick_punch(...) can be used on their own.
Pure numpy/scipy. beat: (2, n) or (n,) float32.
"""
import numpy as np
import scipy.signal as sg

PRESETS = {
    "afrobeats": dict(max_punch_db=3.0, click_ratio=0.35),
    "club":      dict(max_punch_db=4.0, click_ratio=0.40),
    "streaming": dict(max_punch_db=2.0, click_ratio=0.30),
}
LIMITS = dict(rms_rise_db=0.3, peak_rise_db=0.3, min_kicks=8)


def _mono(x):
    a = np.asarray(x, np.float32)
    return a.mean(axis=0) if a.ndim == 2 else a


def _sos(kind, f, sr, order=4):
    return sg.butter(order, f, kind, fs=sr, output="sos")


def _zp(x, sos):
    return sg.sosfiltfilt(sos, x).astype(np.float32)


def _db(v):
    return 20.0 * np.log10(np.asarray(v, np.float64) + 1e-12)


def _smooth(x, sr, tau):
    a = float(np.exp(-1.0 / (tau * sr)))
    return sg.lfilter([1.0 - a], [1.0, -a], x).astype(np.float32)


# ----------------------------------------------------------------- 1. measure (BEFORE any punch)
def measure_beat(beat, sr):
    a = np.asarray(beat, np.float32)
    m = _mono(a)
    peak_db = float(_db(np.abs(a).max()))
    rms_db = float(10 * np.log10((m.astype(np.float64) ** 2).mean() + 1e-20))
    out = {"peak_db": round(peak_db, 2), "rms_db": round(rms_db, 2), "crest_db": round(peak_db - rms_db, 2)}
    w = int(0.4 * sr); k = len(m) // w
    if k > 4:
        fr = m[:k * w].reshape(k, w); r = np.sqrt((fr ** 2).mean(1) + 1e-14); p = np.abs(fr).max(1)
        loud = _db(r) > np.percentile(_db(r), 50)
        out["crest_short_db"] = round(float(np.median((_db(p) - _db(r))[loud])), 2)
    kb = _zp(m, _sos("bandpass", [40, 120], sr, 3))
    low_share = float(10 * np.log10((kb.astype(np.float64) ** 2).mean() / ((m.astype(np.float64) ** 2).mean() + 1e-20) + 1e-20))
    out["low_share_db"] = round(low_share, 1)
    ab = np.abs(kb)
    fast, slow = _smooth(ab, sr, 0.004), _smooth(ab, sr, 0.08)
    cond = (fast > 2.0 * slow) & (fast > 0.6 * np.percentile(fast, 85))
    edges = np.flatnonzero(cond[1:] & ~cond[:-1]) + 1
    if low_share < -20.0:                       # almost no 40-120 Hz energy: nothing to punch (also rejects noise)
        edges = edges[:0]
    ev, last = [], -10 ** 9
    for i in edges:
        if i - last >= int(0.15 * sr) and i > int(0.01 * sr) and i + int(0.2 * sr) < len(kb):
            ev.append(int(i)); last = int(i)
    kc, kp = [], []
    for i in ev:
        s = kb[i - int(0.005 * sr): i + int(0.15 * sr)]
        pk = np.abs(s).max(); rm = np.sqrt((s.astype(np.float64) ** 2).mean() + 1e-20)
        kc.append(float(_db(pk) - _db(rm))); kp.append(float(_db(pk)))
    mid = _zp(m, _sos("bandpass", [300, 3000], sr, 3))
    h = int(0.1 * sr); kk = len(mid) // h
    mid_pk = float(np.percentile(np.abs(mid[:kk * h].reshape(kk, h)).max(1), 95)) if kk > 4 else 1e-6
    out.update({"kick_count": len(ev), "events": ev})
    if ev:
        out["kick_crest_db"] = round(float(np.median(kc)), 2)
        out["kick_to_mid_db"] = round(float(np.median(kp) - _db(mid_pk)), 2)
    return out


# ----------------------------------------------------------------- 2. decide
def decide(meas, preset="afrobeats", strength=1.0):
    P = PRESETS[preset] if isinstance(preset, str) else preset
    n = meas.get("kick_count", 0)
    if n < LIMITS["min_kicks"] or "kick_crest_db" not in meas:
        return {"punch_db": 0.0, "click_db": 0.0, "need": 0.0, "reason": "fewer than %d kicks found, no punch added" % LIMITS["min_kicks"]}
    # reference masters (Boi Chase, Burna, Davido, Fola, Rema): kick crest 8.4-10.5 dB (median 9.7), kick-to-mid -0.3..+5.0 dB (median +1.0)
    need_c = float(np.clip((16.5 - meas["crest_db"]) / 6.5, 0, 1))          # squashed beat (low crest) -> needs more
    need_k = float(np.clip((9.7 - meas["kick_crest_db"]) / 3.0, 0, 1))       # kick flatter than the references -> needs more
    need_f = float(np.clip((1.0 - meas["kick_to_mid_db"]) / 4.0, 0, 1))      # kick buried under the mids -> needs more
    need = float(np.clip((0.5 * need_k + 0.3 * need_c + 0.2 * need_f) * strength, 0, 1))
    punch = round(need * P["max_punch_db"], 2)
    return {"punch_db": punch, "click_db": round(punch * P["click_ratio"], 2), "need": round(need, 2),
            "need_parts": {"crest": round(need_c, 2), "kick_crest": round(need_k, 2), "kick_level": round(need_f, 2)},
            "reason": "adaptive from crest factor and kick crest"}


# ----------------------------------------------------------------- 3. kick punch
def _event_window(n, sr, events, pre_s, post_s, ramp_s):
    w = np.zeros(n, np.float32)
    for i in events:
        s0, e0 = max(0, i - int(pre_s * sr)), min(n, i + int(post_s * sr))
        seg = np.ones(e0 - s0, np.float32); r = min(len(seg) // 2, int(ramp_s * sr))
        seg[:r] = np.linspace(0, 1, r); seg[-r:] = np.linspace(1, 0, r)
        w[s0:e0] = np.maximum(w[s0:e0], seg)
    return w


def kick_punch(beat, sr, events, punch_db, click_db, cross_hz=120.0):
    """Transient shaping on the kick only: the 40-120 Hz body gets a fast-attack lift inside each kick window, plus a
    very small 1.5-4.5 kHz click. Gains are smoothed (2 ms), so no clicks. The rest of the beat is untouched."""
    a = np.asarray(beat, np.float32); n = a.shape[-1]
    if punch_db <= 0.01 or not events:
        return a
    m = _mono(a)
    low_m = _zp(m, _sos("bandpass", [40, cross_hz], sr, 3))
    ab = np.abs(low_m)
    fast, slow = _smooth(ab, sr, 0.0015), _smooth(ab, sr, 0.025)
    r = fast / (slow + 1e-9)
    G = 10 ** (punch_db / 20.0)
    g = 1.0 + (G - 1.0) * np.clip((r - 1.0) / 1.0, 0.0, 1.0)
    win = _event_window(n, sr, events, 0.010, 0.080, 0.008)
    g = _smooth(1.0 + (g - 1.0) * win, sr, 0.002)
    body_add = low_m * (g - 1.0)
    out = a + body_add[None, :] if a.ndim == 2 else a + body_add
    if click_db > 0.01:
        click = _zp(m, _sos("bandpass", [1500, 4500], sr, 2))
        cwin = _event_window(n, sr, events, 0.002, 0.025, 0.005)
        add = click * (10 ** (click_db / 20.0) - 1.0) * cwin
        out = out + add[None, :] if a.ndim == 2 else out + add
    return out.astype(np.float32)


def _peak_guard(x, ceiling, sr, look_ms=3.0):
    """Lookahead peak guard: gain drops smoothly only around samples above `ceiling`; everything else untouched."""
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    a = np.asarray(x, np.float32)
    pk = np.abs(a).max(axis=0) if a.ndim == 2 else np.abs(a)
    L = max(3, int(look_ms / 1000.0 * sr))
    env = maximum_filter1d(pk, size=2 * L + 1)
    g = np.minimum(1.0, ceiling / (env + 1e-12)).astype(np.float32)
    g = uniform_filter1d(g, size=2 * L + 1).astype(np.float32)
    g = np.minimum(g, np.minimum(1.0, ceiling / (pk + 1e-12)))
    return (a * g[None, :] if a.ndim == 2 else a * g).astype(np.float32)


# ----------------------------------------------------------------- 4. process (kick only, with guards)
def process(beat, sr, preset="afrobeats", strength=1.0):
    P = PRESETS[preset] if isinstance(preset, str) else preset
    a = np.asarray(beat, np.float32)
    before = measure_beat(a, sr)                                   # crest factor measured BEFORE punch
    dec = decide(before, P, strength)
    out = a
    if dec["punch_db"] > 0:
        out = kick_punch(out, sr, before["events"], dec["punch_db"], dec["click_db"])
        rms0 = 10 * np.log10((a.astype(np.float64) ** 2).mean() + 1e-20); pk0 = float(np.abs(a).max())
        rms1 = 10 * np.log10((out.astype(np.float64) ** 2).mean() + 1e-20)
        gain = float(np.clip(rms0 - rms1, -LIMITS["rms_rise_db"], LIMITS["rms_rise_db"]))
        out = (out * np.float32(10 ** (gain / 20.0))).astype(np.float32)
        out = _peak_guard(out, pk0 * 10 ** (LIMITS["peak_rise_db"] / 20.0), sr)
    after = measure_beat(out, sr)
    rep = {"preset": preset if isinstance(preset, str) else "custom",
           "before": {k: v for k, v in before.items() if k != "events"}, "decision": dec,
           "after": {k: v for k, v in after.items() if k != "events"},
           "delta": {"rms_db": round(after["rms_db"] - before["rms_db"], 2), "peak_db": round(after["peak_db"] - before["peak_db"], 2),
                     "crest_short_db": round(after.get("crest_short_db", 0) - before.get("crest_short_db", 0), 2)}}
    if "kick_crest_db" in before and "kick_crest_db" in after:
        rep["delta"]["kick_crest_db"] = round(after["kick_crest_db"] - before["kick_crest_db"], 2)
        rep["delta"]["kick_to_mid_db"] = round(after["kick_to_mid_db"] - before["kick_to_mid_db"], 2)
    return out, rep
