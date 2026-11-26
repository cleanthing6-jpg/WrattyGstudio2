"""level_guard.py - adaptive beat + vocal LEVEL measurement and gain staging.
Standalone (numpy + scipy only). Measures the way broadcast/streaming standards do (ITU-R BS.1770-4 /
EBU R128: K-weighting, 400 ms blocks, -70 LUFS absolute gate, -10 LU relative gate, 4x true peak), then:
  * raises a too-quiet BEAT to a normal pro level (a small look-ahead limiter catches any peaks it creates),
  * raises a too-quiet VOCAL to a level that sits right against that beat (same boost for all vocal stems),
  * never lowers anything, never lifts silence/hiss, and never raises past a peak/noise safety cap.
All targets are engineering starting points (see PROFILES) - tune them by ear.
    new_groups, report = level_guard.apply_to_groups(groups, sr, profile="afrobeats")   # groups = {role: [arrays]}
Never raises: on any problem the input comes back unchanged and report["error"] says why."""
import numpy as np
from scipy import signal as sg
from scipy.ndimage import minimum_filter1d, uniform_filter1d

PROFILES = {
    # beat_low: below this integrated LUFS the beat counts as "too low";  beat_target: where it is raised to;
    # vocal_offset: dry lead loudness (dual-mono, gated) relative to the beat AFTER it was staged
    "default":   {"beat_low": -14.0, "beat_target": -12.0, "vocal_offset": -5.5},
    "afrobeats": {"beat_low": -14.0, "beat_target": -12.0, "vocal_offset": -5.5},
    "rap":       {"beat_low": -13.5, "beat_target": -11.5, "vocal_offset": -4.5},
}
LIMITS = {"max_beat_boost_db": 18.0, "max_vocal_boost_db": 15.0, "ceiling_dbtp": -1.0, "max_limiter_gr_db": 3.0,
          "vocal_peak_ceiling_db": -1.5, "noise_cap_db": -55.0, "vocal_tolerance_lu": 2.0, "silence_lufs": -55.0}
BEAT_ROLES = ("beat", "instrumental", "inst", "instrument", "music", "2track", "two track")


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
    dt, shape, nd = a.dtype, a.shape, a.ndim
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
    return _integrated(_block_z(x2, sr))


def true_peak_db(x2):
    up = sg.resample_poly(x2, 4, 1, axis=0)
    return float(20 * np.log10(max(np.max(np.abs(up)), 1e-9)))


def measure(x, sr, dual_mono=True):
    """Level report for one stem: integrated LUFS (mono counted as dual-mono, as it plays in a stereo mix),
    true/sample peak, PLR, noise floor, bass share."""
    x2, _ = _as2d(x)
    m = _dual(x2) if dual_mono else x2
    mono = x2.mean(axis=1)
    h = max(1, int(sr * 0.05))
    n = len(mono) // h * h
    r = 20 * np.log10(np.sqrt((mono[:n].reshape(-1, h) ** 2).mean(axis=1)) + 1e-9) if n else np.array([-120.0])
    f, P = sg.welch(mono, sr, nperseg=min(4096, max(256, len(mono))))
    low = float(P[(f >= 20) & (f < 150)].sum() / (P[(f >= 20) & (f < 16000)].sum() + 1e-20))
    L = lufs(m, sr)
    tp = true_peak_db(m)
    sp = float(20 * np.log10(max(np.max(np.abs(x2)), 1e-9)))
    return {"lufs": L, "true_peak_db": tp, "sample_peak_db": sp, "plr_db": tp - L,
            "noise_floor_db": float(np.percentile(r, 10)), "low_share": low, "seconds": len(x2) / sr}


def _limit(x2, sr, ceil_db, look_ms=3.0, rel_ms=120.0):
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
    y = x2 * (10 ** (-rf / 20))[:, None]
    return y, {"max_gr_db": float(rf.max()), "pct_time": float((rf > 0.1).mean() * 100)}


def _stage_beat(b2, sr, p, L):
    """Raise a quiet beat to the profile target. The boost is capped so the look-ahead limiter only has to take
    a few dB off the peaks; if the beat's peaks leave no room it is left alone (it needs compression, not gain)."""
    m0 = measure(b2, sr)
    info = {"lufs_before": m0["lufs"], "true_peak_before_db": m0["true_peak_db"], "gain_db": 0.0, "action": "ok"}
    if m0["lufs"] < L["silence_lufs"]:
        info["action"] = "skipped: beat is silent or almost silent"
        return b2, info
    if m0["lufs"] >= p["beat_low"]:
        info["action"] = "ok (level is in the normal range, left alone)"
        return b2, info
    want = float(np.clip(p["beat_target"] - m0["lufs"], 0.0, L["max_beat_boost_db"]))
    g_cap = L["ceiling_dbtp"] + L["max_limiter_gr_db"] - m0["true_peak_db"]
    g = min(want, g_cap)
    if g < 0.5:
        info["action"] = "not raised: peaks leave no room (true peak %.1f dBTP) - this beat needs compression, not gain" % m0["true_peak_db"]
        return b2, info
    y, st, l_y = None, None, None
    for _ in range(3):
        y, st = _limit(b2 * 10 ** (g / 20), sr, L["ceiling_dbtp"])
        l_y = lufs(_dual(y), sr)
        err = p["beat_target"] - l_y
        g_new = min(g_cap, g + err)
        if err < 0.3 or g_new <= g + 0.05:
            break
        g = g_new
    if l_y < m0["lufs"] + 0.5:
        info["action"] = "not raised (limiting would not make it louder)"
        return b2, info
    tp = true_peak_db(_dual(y))
    if tp > L["ceiling_dbtp"] + 0.05:
        y = y * 10 ** ((L["ceiling_dbtp"] - tp) / 20)
        l_y = lufs(_dual(y), sr)
        tp = true_peak_db(_dual(y))
    act = "raised" if l_y >= p["beat_target"] - 0.5 else "raised (as far as peaks allow)"
    if st["pct_time"] > 50.0:
        act += " - limiter is working hard on this beat, listen for pumping"
    info.update(gain_db=float(g), lufs_after=l_y, true_peak_after_db=tp, limiter_max_gr_db=st["max_gr_db"],
                limiter_time_pct=st["pct_time"], action=act, shortfall_db=float(max(0.0, p["beat_target"] - l_y)))
    return y, info


def _vocal_gain(v_ref, beat_lufs, beat_low_share, p, L):
    """Gain (dB) for the vocal stems, or (0, reason)."""
    adj = float(np.clip((beat_low_share - 0.55) * 5.0, -1.0, 1.5))       # bass-heavy beat -> vocal needs a bit more
    target = beat_lufs + p["vocal_offset"] + adj
    info = {"lufs_before": v_ref["lufs"], "target_lufs": target, "bass_adjust_lu": adj, "gain_db": 0.0}
    if v_ref["lufs"] < L["silence_lufs"]:
        info["action"] = "skipped: vocal is silent or almost silent"
        return 0.0, info
    if v_ref["lufs"] >= target - L["vocal_tolerance_lu"]:
        info["action"] = "ok (vocal level is fine, left alone)"
        return 0.0, info
    g = float(np.clip(target - v_ref["lufs"], 0.0, L["max_vocal_boost_db"]))
    why = "raised"
    peak_room = L["vocal_peak_ceiling_db"] - v_ref["sample_peak_db"]
    if g > peak_room:
        g, why = max(0.0, peak_room), "raised (capped by peak headroom)"
    noise_room = L["noise_cap_db"] - v_ref["noise_floor_db"]
    if g > noise_room:
        g, why = max(0.0, noise_room), "raised (capped so background noise stays inaudible)"
    info.update(gain_db=g, action=why if g > 0.05 else "not raised (peak or noise cap)",
                lufs_after=v_ref["lufs"] + g)
    return g, info


def _profile(name):
    k = str(name or "default").lower()
    return dict(PROFILES.get(k, PROFILES["default"])), k if k in PROFILES else "default"


def _items(v):
    return list(v) if isinstance(v, (list, tuple)) else [v]


def apply_to_groups(groups, sr, profile="afrobeats", **limit_overrides):
    """groups: {role: array | [arrays]}. Beat roles are staged first, then every vocal role gets the same boost."""
    rep = {"module": "level_guard", "ok": False}
    try:
        sr = int(sr)
        if sr < 8000:
            raise ValueError("sample rate too low")
        p, pname = _profile(profile)
        L = dict(LIMITS, **limit_overrides)
        rep["profile"], rep["targets"] = pname, dict(p)
        out, beat_keys, voc_keys = dict(groups), [], []
        for k, v in groups.items():
            (beat_keys if str(k).lower() in BEAT_ROLES else voc_keys).append(k)
        beat_lufs, beat_low = None, 0.55
        # ---- beat
        if beat_keys:
            bl = []
            for k in beat_keys:
                arrs = _items(groups[k])
                new = []
                for a in arrs:
                    b2, restore = _as2d(a)
                    y, info = _stage_beat(b2, sr, p, L)
                    new.append(restore(y))
                    bl.append(info)
                out[k] = new if isinstance(groups[k], (list, tuple)) else new[0]
            rep["beat"] = bl[0] if len(bl) == 1 else bl
            first = bl[0]
            beat_lufs = first.get("lufs_after", first["lufs_before"])
            src = _items(out[beat_keys[0]])[0]
            beat_low = measure(src, sr)["low_share"]
        else:
            rep["beat"] = {"action": "no beat stem found"}
        # ---- vocals (reference = lead/feature, else the loudest vocal stem)
        if voc_keys and beat_lufs is not None:
            cand = []
            for k in voc_keys:
                for a in _items(groups[k]):
                    cand.append((k, measure(a, sr)))
            ref = [m for k, m in cand if str(k).lower() in ("lead", "feature")] or [m for k, m in cand]
            vref = max(ref, key=lambda m: m["lufs"])
            g, vinfo = _vocal_gain(vref, beat_lufs, beat_low, p, L)
            rep["vocal"] = vinfo
            if g > 0.05:
                for k in voc_keys:
                    arrs = _items(groups[k])
                    new = []
                    for a in arrs:
                        v2, restore = _as2d(a)
                        new.append(restore(v2 * 10 ** (g / 20)))
                    out[k] = new if isinstance(groups[k], (list, tuple)) else new[0]
        elif voc_keys:
            rep["vocal"] = {"action": "skipped: no beat to balance against"}
        rep["ok"] = True
        return out, rep
    except Exception as e:
        rep["error"] = "%s: %s" % (type(e).__name__, e)
        return groups, rep
