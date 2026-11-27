"""level_guard.py v2 - adaptive beat + vocal LEVEL measurement and gain staging (standalone: numpy + scipy).

MEASURES (ITU-R BS.1770-4 / EBU R128): K-weighted integrated LUFS (400 ms blocks, -70 LUFS absolute gate, -10 LU
relative gate), 4x-oversampled true peak, noise floor, and the loudness of each stem inside the vocal band
(250-4000 Hz) - that band is where a beat actually competes with a vocal, so the balance is judged there.

DECIDES, per song (the engine keeps control of anything that is already in the normal range):
  beat  VERY LOW  -> raised to a normal beat level, chosen RELATIVE to the vocal (vocal-band ratio) when the vocal
                     is normal, or to the profile's normal level when the vocal is also very low
  beat  normal / hot -> untouched (the engine decides)
  vocal VERY LOW  -> raised to a normal vocal level RELATIVE to the beat; every vocal stem gets the same dB lift
  vocal normal / hot -> untouched
SAFETY: nothing is ever lowered; silence/hiss is never lifted; peaks are capped (look-ahead limiter on the beat,
peak and noise caps on the vocal); any failure returns the input unchanged. Thresholds are starting points (PROFILES).

API   new_groups, rep = apply_to_groups({role: array | [arrays]}, sr, profile="afrobeats")
      rep = analyze_groups(groups, sr, profile)          # measure + decide only, audio untouched
      python3 level_guard.py --selftest                  # built-in checks
rep keys: ok, version, profile, thresholds, beat{class, action, lufs_before, target_lufs, gain_db, lufs_after, ...},
          vocal{class, action, lufs_before, target_lufs, gain_db, lufs_after, ...}, balance{...}, summary."""
import sys
import numpy as np
from scipy import signal as sg
from scipy.ndimage import minimum_filter1d, uniform_filter1d

__version__ = "2.0"
__all__ = ["apply_to_groups", "analyze_groups", "measure", "lufs", "true_peak_db", "explain"]

_BASE = {"beat_floor": -16.0, "beat_target": -12.0, "beat_clamp": (-14.0, -10.5),
         "vocal_floor": -24.0, "vocal_clamp": (-20.0, -14.0), "band_ratio": 2.0}
PROFILES = {
    # beat_floor / vocal_floor: below this integrated LUFS the stem counts as VERY LOW and is raised
    # *_clamp: the normal range a raised stem lands in;  band_ratio: vocal minus beat loudness in the 250-4000 Hz band
    "default": dict(_BASE),
    "afrobeats": dict(_BASE),
    "rap": dict(_BASE, band_ratio=3.0, vocal_clamp=(-19.0, -13.0)),
    "pop": dict(_BASE, band_ratio=2.5),
}
ALIASES = {"amapiano": "afrobeats", "dancehall": "afrobeats", "gospel": "afrobeats", "highlife": "afrobeats",
           "hiphop": "rap", "hip hop": "rap", "rnb": "pop", "r&b": "pop"}
LIMITS = {"max_beat_boost_db": 18.0, "max_vocal_boost_db": 18.0, "ceiling_dbtp": -1.0, "max_limiter_gr_db": 3.0,
          "vocal_peak_ceiling_db": -1.5, "noise_cap_db": -55.0, "silence_lufs": -55.0, "min_move_db": 0.5}
BAND = (250.0, 4000.0)
BEAT_KEYS = ("beat", "instrumental", "inst", "instrument", "music", "2track", "two track")
IGNORE_KEYS = ("other", "mix", "master", "fx", "sfx")


# ------------------------------------------------------------------------------------------------ measurement
def _k_filters(sr):
    """BS.1770-4 K-weighting: stage 1 high shelf (+4 dB), stage 2 high-pass (RLB), any sample rate."""
    f0, G, Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = np.tan(np.pi * f0 / sr)
    Vh = 10 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1 + K / Q + K * K
    b1 = [(Vh + Vb * K / Q + K * K) / a0, 2 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0]
    a1 = [1.0, 2 * (K * K - 1) / a0, (1 - K / Q + K * K) / a0]
    f1, Q2 = 38.13547087602444, 0.5003270373238773
    K = np.tan(np.pi * f1 / sr)
    d = 1 + K / Q2 + K * K
    b2 = [1.0, -2.0, 1.0]
    a2 = [1.0, 2 * (K * K - 1) / d, (1 - K / Q2 + K * K) / d]
    return sg.tf2sos(b1, a1), sg.tf2sos(b2, a2)


def _as2d(x):
    """-> (n, ch) float64 and a function that restores the original layout/dtype."""
    a = np.asarray(x)
    dt, nd = a.dtype, a.ndim
    a = a.astype(np.float64)
    tr = False
    if nd == 1:
        a = a[:, None]
    elif a.shape[0] <= 2 and a.shape[1] > a.shape[0]:
        a, tr = a.T, True
    a = np.nan_to_num(a)

    def restore(y):
        y = y.T if tr else y
        y = y[:, 0] if nd == 1 else y
        return y.astype(dt if np.issubdtype(dt, np.floating) else np.float32)
    return a, restore


def _dual(x2):
    return np.repeat(x2[:, :1], 2, axis=1) if x2.shape[1] == 1 else x2[:, :2]


def _sum2d(arrs):
    n = max(len(a) for a in arrs)
    ch = max(a.shape[1] for a in arrs)
    out = np.zeros((n, ch))
    for a in arrs:
        out[: len(a), : a.shape[1]] += a
        if a.shape[1] < ch:
            out[: len(a), a.shape[1]:] += a[:, :1]
    return out


def _block_z(x2, sr):
    s1, s2 = _k_filters(sr)
    xk = sg.sosfilt(s2, sg.sosfilt(s1, x2, axis=0), axis=0)
    sq = (xk ** 2).sum(axis=1)
    blk, step, n = int(round(0.4 * sr)), int(round(0.1 * sr)), len(sq)
    if n < blk:
        return np.array([sq.mean()])
    c = np.concatenate(([0.0], np.cumsum(sq)))
    st = np.arange(0, n - blk + 1, step)
    return (c[st + blk] - c[st]) / blk


def _integrated(z):
    l = -0.691 + 10 * np.log10(z + 1e-20)
    k = l > -70.0
    if not k.any():
        return -120.0
    gr = -0.691 + 10 * np.log10(np.mean(z[k])) - 10.0
    k2 = k & (l > gr)
    return float(-0.691 + 10 * np.log10(np.mean(z[k2]))) if k2.any() else -120.0


def lufs(x2, sr):
    """Integrated loudness (LUFS) of an (n, ch) array."""
    return _integrated(_block_z(x2, sr))


def true_peak_db(x2):
    up = sg.resample_poly(x2, 4, 1, axis=0)
    return float(20 * np.log10(max(np.max(np.abs(up)), 1e-9)))


def measure(x, sr):
    """One stem: integrated LUFS (mono counted as dual-mono, as it plays in a stereo mix), LUFS inside the vocal band,
    true/sample peak, noise floor, bass share."""
    x2, _ = _as2d(x)
    m = _dual(x2)
    mono = x2.mean(axis=1)
    h = max(1, int(sr * 0.05))
    n = len(mono) // h * h
    r = 20 * np.log10(np.sqrt((mono[:n].reshape(-1, h) ** 2).mean(axis=1)) + 1e-9) if n else np.array([-120.0])
    f, P = sg.welch(mono, sr, nperseg=min(4096, max(256, len(mono))))
    low = float(P[(f >= 20) & (f < 150)].sum() / (P[(f >= 20) & (f < 16000)].sum() + 1e-20))
    bp = sg.butter(4, [BAND[0], min(BAND[1], 0.45 * sr)], "bandpass", fs=sr, output="sos")
    return {"lufs": lufs(m, sr), "band_lufs": lufs(sg.sosfilt(bp, m, axis=0), sr),
            "true_peak_db": true_peak_db(m), "sample_peak_db": float(20 * np.log10(max(np.max(np.abs(x2)), 1e-9))),
            "noise_floor_db": float(np.percentile(r, 10)), "low_share": low, "seconds": len(x2) / sr}


# ------------------------------------------------------------------------------------------------ processing
def _limit(x2, sr, ceil_db, look_ms=3.0, rel_ms=120.0):
    """Look-ahead peak limiter (sample peaks never exceed the ceiling). Returns (audio, stats)."""
    c = 10 ** (ceil_db / 20)
    pk = np.max(np.abs(x2), axis=1)
    if not (pk > c).any():
        return x2, {"max_gr_db": 0.0, "pct_time": 0.0}
    g = np.minimum(1.0, c / np.maximum(pk, 1e-12))
    w = max(3, int(sr * look_ms / 1000)) | 1
    gs = uniform_filter1d(minimum_filter1d(g, size=2 * w + 1, mode="nearest"), size=w + 1, mode="nearest")
    r = -20 * np.log10(np.maximum(gs, 1e-6))
    hop = max(1, int(sr * 0.001))
    nh = (len(r) + hop - 1) // hop
    rp = np.zeros(nh * hop)
    rp[: len(r)] = r
    rh = rp.reshape(nh, hop).max(axis=1)
    a = np.exp(-1.0 / rel_ms)
    rr = np.empty(nh)
    s = 0.0
    for i in range(nh):
        s = max(rh[i], s * a)
        rr[i] = s
    rf = np.maximum(np.interp(np.arange(len(r)), (np.arange(nh) + 0.5) * hop, rr), r)
    return x2 * (10 ** (-rf / 20))[:, None], {"max_gr_db": float(rf.max()), "pct_time": float((rf > 0.1).mean() * 100)}


def _raise_beat(arrs, sr, m0, target, L):
    """Raise the beat to `target` LUFS. One array: gain + look-ahead limiter (capped at max_limiter_gr_db).
    Several arrays (separate beat stems): plain gain capped so the SUM stays under the ceiling.
    Returns (new arrays, info)."""
    info = {"gain_db": 0.0}
    want = float(np.clip(target - m0["lufs"], 0.0, L["max_beat_boost_db"]))
    if len(arrs) > 1:
        g = min(want, L["ceiling_dbtp"] - m0["true_peak_db"])
        if g < L["min_move_db"]:
            info["action"] = "not raised: peaks leave no room (true peak %.1f dBTP)" % m0["true_peak_db"]
            return arrs, info
        info.update(gain_db=float(g), action="raised", lufs_after=m0["lufs"] + g)
        return [a * 10 ** (g / 20) for a in arrs], info
    b2 = arrs[0]
    g_cap = L["ceiling_dbtp"] + L["max_limiter_gr_db"] - m0["true_peak_db"]
    g = min(want, g_cap)
    if g < L["min_move_db"]:
        info["action"] = "not raised: peaks leave no room (true peak %.1f dBTP) - this beat needs compression, not gain" % m0["true_peak_db"]
        return arrs, info
    y, st, l_y = None, None, None
    for _ in range(3):
        y, st = _limit(b2 * 10 ** (g / 20), sr, L["ceiling_dbtp"])
        l_y = lufs(_dual(y), sr)
        err = target - l_y
        g_new = min(g_cap, g + err)
        if err < 0.3 or g_new <= g + 0.05:
            break
        g = g_new
    if l_y < m0["lufs"] + L["min_move_db"]:
        info["action"] = "not raised (limiting would not make it louder)"
        return arrs, info
    tp = true_peak_db(_dual(y))
    if tp > L["ceiling_dbtp"] + 0.05:
        y = y * 10 ** ((L["ceiling_dbtp"] - tp) / 20)
        l_y = lufs(_dual(y), sr)
        tp = true_peak_db(_dual(y))
    act = "raised" if l_y >= target - 0.5 else "raised (as far as peaks allow)"
    if st["pct_time"] > 50.0:
        act += " - limiter is working hard on this beat, listen for pumping"
    info.update(gain_db=float(g), lufs_after=l_y, true_peak_after_db=tp, limiter_max_gr_db=st["max_gr_db"],
                limiter_time_pct=st["pct_time"], action=act, shortfall_db=float(max(0.0, target - l_y)))
    return [y], info


def _vocal_gain(v, target, L):
    """dB lift for the vocal stems after the peak and noise caps, plus a short note."""
    g = float(np.clip(target - v["lufs"], 0.0, L["max_vocal_boost_db"]))
    note = "raised"
    room = L["vocal_peak_ceiling_db"] - v["sample_peak_db"]
    if g > room:
        g, note = max(0.0, room), "raised (capped by peak headroom)"
    room = L["noise_cap_db"] - v["noise_floor_db"]
    if g > room:
        g, note = max(0.0, room), "raised (capped so background noise stays inaudible)"
    return g, note


# ------------------------------------------------------------------------------------------------ decisions
def _prof(name):
    k = str(name or "default").lower().strip()
    k = ALIASES.get(k, k)
    k = k if k in PROFILES else "default"
    return k, dict(PROFILES[k])


def _items(v):
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _cls(lufs_v, floor, L):
    return "silent" if lufs_v < L["silence_lufs"] else ("very_low" if lufs_v < floor else "normal")


def explain(rep):
    """One readable line for logs."""
    if not rep.get("ok"):
        return "level_guard: not applied (%s)" % (rep.get("error") or rep.get("note") or "n/a")
    parts = []
    for k in ("beat", "vocal"):
        r = rep.get(k) or {}
        if "lufs_before" in r:
            tail = ("%+.1f dB -> %.1f LUFS" % (r["gain_db"], r.get("lufs_after", r["lufs_before"]))) if r.get("gain_db", 0) > 0 else "untouched"
            parts.append("%s %.1f LUFS (%s) %s" % (k, r["lufs_before"], r.get("class", "?").replace("_", " "), tail))
        else:
            parts.append("%s: %s" % (k, r.get("action", "n/a")))
    b = rep.get("balance") or {}
    if "band_ratio_before" in b:
        parts.append("vocal-vs-beat in the vocal band %.1f -> %.1f LU (normal ~%.1f)" % (
            b["band_ratio_before"], b.get("band_ratio_after", b["band_ratio_before"]), b["band_ratio_normal"]))
    return "level_guard: " + "; ".join(parts)


def apply_to_groups(groups, sr, profile="afrobeats", dry_run=False, log=True, **limit_overrides):
    """Measure, decide and (unless dry_run) apply. Never raises; on any problem returns (groups, rep with 'error')."""
    rep = {"module": "level_guard", "version": __version__, "ok": False}
    try:
        sr = int(sr)
        if sr < 8000:
            raise ValueError("sample rate too low")
        pname, p = _prof(profile)
        L = dict(LIMITS, **limit_overrides)
        rep["profile"], rep["thresholds"], rep["dry_run"] = pname, p, bool(dry_run)
        out = dict(groups)
        bkeys = [k for k in groups if str(k).lower() in BEAT_KEYS]
        vkeys = [k for k in groups if str(k).lower() not in BEAT_KEYS and str(k).lower() not in IGNORE_KEYS]

        # ---- measure
        b_arrs = [_as2d(a) for k in bkeys for a in _items(groups[k])]
        b_m = measure(_sum2d([a for a, _ in b_arrs]), sr) if b_arrs else None
        v_items = [(k, _as2d(a)) for k in vkeys for a in _items(groups[k])]
        v_meas = [(k, measure(a, sr)) for k, (a, _) in v_items]
        pool = [m for k, m in v_meas if str(k).lower() in ("lead", "feature")] or [m for _, m in v_meas]
        v_m = max(pool, key=lambda m: m["lufs"]) if pool else None
        b_cls = _cls(b_m["lufs"], p["beat_floor"], L) if b_m else None
        v_cls = _cls(v_m["lufs"], p["vocal_floor"], L) if v_m else None

        # ---- beat
        beat_after = b_m
        if b_m is None:
            rep["beat"] = {"class": None, "action": "no beat stem found"}
        else:
            binfo = {"class": b_cls, "lufs_before": b_m["lufs"], "band_lufs_before": b_m["band_lufs"],
                     "true_peak_before_db": b_m["true_peak_db"], "gain_db": 0.0}
            if b_cls == "silent":
                binfo["action"] = "skipped: beat is silent or almost silent"
            elif b_cls == "normal":
                binfo["action"] = "left alone (normal level - the engine decides)"
            else:
                if v_m is not None and v_cls == "normal":
                    t = (v_m["band_lufs"] - p["band_ratio"]) + (b_m["lufs"] - b_m["band_lufs"])
                    binfo["basis"] = "relative to the vocal (vocal-band ratio %+.1f LU)" % p["band_ratio"]
                else:
                    t, binfo["basis"] = p["beat_target"], "profile normal beat level"
                t = float(np.clip(t, p["beat_clamp"][0], p["beat_clamp"][1]))
                binfo["target_lufs"] = t
                if dry_run:
                    g = float(np.clip(t - b_m["lufs"], 0.0, L["max_beat_boost_db"]))
                    binfo.update(action="would raise by %.1f dB" % g, gain_db=g, lufs_after=b_m["lufs"] + g)
                    beat_after = dict(b_m, lufs=b_m["lufs"] + g, band_lufs=b_m["band_lufs"] + g)
                else:
                    new, info = _raise_beat([a for a, _ in b_arrs], sr, b_m, t, L)
                    binfo.update(info)
                    if info.get("gain_db", 0.0) > 0.0:
                        beat_after = measure(_sum2d(new), sr)
                        binfo["lufs_after"] = beat_after["lufs"]
                        i = 0
                        for k in bkeys:
                            arrs = _items(groups[k])
                            res = []
                            for _a in arrs:
                                res.append(b_arrs[i][1](new[i if len(new) > 1 else 0]))
                                i += 1
                            out[k] = res if isinstance(groups[k], (list, tuple)) else res[0]
            rep["beat"] = binfo

        # ---- vocal
        if v_m is None:
            rep["vocal"] = {"class": None, "action": "no vocal stem found"}
        else:
            vinfo = {"class": v_cls, "lufs_before": v_m["lufs"], "band_lufs_before": v_m["band_lufs"], "gain_db": 0.0}
            if v_cls == "silent":
                vinfo["action"] = "skipped: vocal is silent or almost silent"
            elif v_cls == "normal":
                vinfo["action"] = "left untouched (normal level)"
            else:
                if beat_after is not None and b_cls != "silent":
                    t = (beat_after["band_lufs"] + p["band_ratio"]) + (v_m["lufs"] - v_m["band_lufs"])
                    vinfo["basis"] = "relative to the beat (vocal-band ratio %+.1f LU)" % p["band_ratio"]
                else:
                    t, vinfo["basis"] = p["vocal_clamp"][0], "bottom of the normal vocal range (no beat to balance against)"
                t = float(np.clip(t, p["vocal_clamp"][0], p["vocal_clamp"][1]))
                g, note = _vocal_gain(v_m, t, L)
                vinfo.update(target_lufs=t, reference_role="lead/feature" if any(str(k).lower() in ("lead", "feature") for k in vkeys) else "loudest vocal")
                if g < L["min_move_db"]:
                    vinfo["action"] = "not raised (peak or noise cap)" if g <= 0.0 else "no meaningful change"
                else:
                    vinfo.update(gain_db=g, action=("would raise: " if dry_run else "") + note, lufs_after=v_m["lufs"] + g)
                    if not dry_run:
                        j = 0
                        for k in vkeys:
                            res = []
                            for _a in _items(groups[k]):
                                a2, restore = v_items[j][1]
                                res.append(restore(a2 * 10 ** (g / 20)))
                                j += 1
                            out[k] = res if isinstance(groups[k], (list, tuple)) else res[0]
            rep["vocal"] = vinfo

        # ---- balance report
        if b_m is not None and v_m is not None:
            bal = {"band_ratio_normal": p["band_ratio"], "band_ratio_before": v_m["band_lufs"] - b_m["band_lufs"]}
            v_after = v_m["band_lufs"] + float((rep["vocal"] or {}).get("gain_db", 0.0))
            bal["band_ratio_after"] = v_after - beat_after["band_lufs"]
            rep["balance"] = bal
        rep["ok"] = True
        rep["summary"] = explain(rep)
        if log:
            print(rep["summary"])
        return out, rep
    except Exception as e:
        rep["error"] = "%s: %s" % (type(e).__name__, e)
        return groups, rep


def analyze_groups(groups, sr, profile="afrobeats", **limit_overrides):
    """Measure and decide only - the audio is not touched. Returns the report."""
    return apply_to_groups(groups, sr, profile, dry_run=True, log=False, **limit_overrides)[1]


# ------------------------------------------------------------------------------------------------ self test
def _selftest():
    sr, dur = 48000, 20
    t = np.arange(sr * dur) / sr
    rng = np.random.default_rng(1)
    fails = []

    def check(name, ok, detail=""):
        print(("PASS  " if ok else "FAIL  ") + name + ("  " + detail if detail else ""))
        if not ok:
            fails.append(name)

    s = 0.1 * np.sin(2 * np.pi * 997 * t)
    check("997 Hz, -20 dBFS, both channels reads -20.0 LUFS", abs(lufs(np.stack([s, s], 1), sr) + 20.0) < 0.1)
    check("same tone in one channel reads -23.01 LUFS", abs(lufs(s[:, None], sr) + 23.01) < 0.1)
    g = np.concatenate([s[: sr * 10], np.zeros(sr * 10)])
    check("silence is gated out", abs(lufs(np.stack([g, g], 1), sr) + 20.0) < 0.15)

    def beat(target):
        b = np.zeros(len(t))
        for k in np.arange(0, dur - 0.6, 0.5357):
            i, tt = int(k * sr), np.arange(int(0.45 * sr)) / sr
            b[i:i + len(tt)] += 0.9 * np.sin(2 * np.pi * (48 + 90 * np.exp(-tt * 28)) * tt) * np.exp(-tt * 5)
        ch = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.2, 329.6, 440)) * 0.08
        x = np.stack([b + ch, b + ch * 0.9], 1)
        return (x * 10 ** ((target - lufs(x, sr)) / 20)).astype(np.float32)

    def voice(target):
        ph = 2 * np.pi * np.cumsum(200 + 10 * np.sin(2 * np.pi * 5.5 * t)) / sr
        v = sum(np.sin(k * ph) / k for k in range(1, 25))
        for fc, bw in [(700, 120), (1200, 150), (2800, 250)]:
            v = v + 1.5 * sg.sosfilt(sg.butter(2, [fc - bw, fc + bw], "bandpass", fs=sr, output="sos"), v)
        v = v * np.convolve(((t % 2.2) < 1.5).astype(float), np.ones(800) / 800, "same") + rng.standard_normal(len(t)) * 1e-4
        return (v * 10 ** ((target - lufs(np.stack([v, v], 1), sr)) / 20)).astype(np.float32)

    def run(bt, vt):
        b, v = beat(bt), voice(vt)
        o, r = apply_to_groups({"beat": [b], "lead": [v]}, sr, "afrobeats", log=False)
        return b, v, o, r

    b, v, o, r = run(-11.0, -17.0)
    check("normal beat + normal vocal: both untouched", np.array_equal(o["beat"][0], b) and np.array_equal(o["lead"][0], v))
    b, v, o, r = run(-20.0, -17.0)
    la = lufs(_dual(_as2d(o["beat"][0])[0]), sr)
    check("very low beat + normal vocal: beat raised into the normal range, vocal untouched",
          -14.5 < la < -9.5 and np.array_equal(o["lead"][0], v), "beat now %.1f LUFS" % la)
    b, v, o, r = run(-11.0, -32.0)
    lv = lufs(_dual(_as2d(o["lead"][0])[0]), sr)
    check("normal beat + very low vocal: vocal raised into the normal range, beat untouched",
          -20.5 < lv < -13.5 and np.array_equal(o["beat"][0], b), "vocal now %.1f LUFS" % lv)
    b, v, o, r = run(-20.0, -32.0)
    check("both very low: both raised", r["beat"]["gain_db"] > 3 and r["vocal"]["gain_db"] > 3,
          "beat %+.1f dB, vocal %+.1f dB" % (r["beat"]["gain_db"], r["vocal"]["gain_db"]))
    o2, r2 = apply_to_groups(o, sr, "afrobeats", log=False)
    check("running it twice changes nothing more", r2["beat"]["gain_db"] == 0.0 and r2["vocal"]["gain_db"] == 0.0)
    b, v, o, r = run(-7.0, -17.0)
    check("hot beat: untouched", np.array_equal(o["beat"][0], b))
    b, v, o, r = run(-20.0, -32.0)
    rd = analyze_groups({"beat": [b], "lead": [v]}, sr, "afrobeats")
    check("analyze_groups decides without touching audio", rd["ok"] and rd["beat"]["gain_db"] > 3)
    z = apply_to_groups({"beat": np.zeros(len(t), np.float32), "lead": v}, sr, log=False)[1]
    check("silent beat is skipped", z["ok"] and z["beat"]["class"] == "silent")
    bad = apply_to_groups({"beat": "nope"}, sr, log=False)
    check("bad input never raises", bad[1].get("ok") is False and "error" in bad[1])
    print("\nALL CHECKS PASSED" if not fails else "\nFAILED: " + ", ".join(fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
