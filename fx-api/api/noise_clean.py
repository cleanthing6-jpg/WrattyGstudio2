"""
noise_clean.py (v2, merged)  -  adaptive noise / rumble / hum cleaner for vocal STEMS (lead, backing, adlib). Never the beat.

Keeps everything from v1 (learn -> decide -> clean -> check itself) and adds:
  * RUMBLE HIGH-PASS  (zero-phase, 70 Hz): mic-stand thump, AC/fan/street rumble. Only applied when cleaning happens,
    so stems that are skipped stay bit-identical.
  * CONTINUOUS NOISE TRACKER (minimum-statistics style) used automatically when a stem has no clear gaps to learn from
    (singer barely pauses) - v1 had to give up there. When gaps exist, the gap profile + level tracker is used as before.
  * REAL HUM DETECTOR: narrow peaks (>=10 dB over their immediate neighbours, >=2 harmonics of 50/60 Hz) measured at
    3 Hz resolution on the quiet audio, removed with narrow zero-phase notches. A broad rumble hump is NOT hum.
  * GAIN RULE option: "wiener" (v1 behaviour, default - best under the self-check) or "lsa" (log-MMSE, optional).
  * sample-rate fix: the 50 ms release no longer assumes 44.1 kHz.

USAGE (first on every vocal stem, before EQ / compression / saturation)
    y, rep = noise_clean.clean(stem, sr, role="lead")     # (N,) or (2,N). role "beat" is returned untouched.
    rep    = noise_clean.analyse(stem, sr)                # dry run for UI / stem QC
"""
import time
import numpy as np
import scipy.signal as sg
from scipy.ndimage import uniform_filter1d, percentile_filter
from scipy.special import exp1
from scipy.stats import gamma as _gamma

__all__ = ["clean", "analyse"]

NFFT, HOP = 2048, 512
ROLE = {"lead": 1.0, "adlib": 0.9, "backing": 0.8}
MAX_DEPTH, ACTIVE_DEPTH, MIN_DEPTH = 14.0, 8.0, 2.0
DEV_LIMIT_DB, FLUTTER_LIMIT_DB = 0.6, 3.0
HP_HZ = 70.0


def _frames(mono, sr, nt):
    rms = np.sqrt(np.maximum(uniform_filter1d(mono ** 2, size=NFFT, mode="constant"), 0.0) + 1e-24)
    idx = np.clip(np.arange(nt) * HOP, 0, len(mono) - 1)
    return 20.0 * np.log10(rms[idx] + 1e-12)


def _runs(mask, min_len):
    m = uniform_filter1d(mask.astype(float), size=min_len, mode="nearest") > 0.999
    return mask & (m | (uniform_filter1d(m.astype(float), size=min_len, mode="nearest") > 0.0))


# ----------------------------------------------------------------------------- noise tracking (no-gap fallback)
def _tracker(P, valid, window_s, sr, pct=12.0):
    """continuous noise PSD: percentile of the time-smoothed spectrogram over a sliding window + bias compensation"""
    nb, nt = P.shape
    msm = 5
    Ps = uniform_filter1d(P, size=msm, axis=1)
    E = Ps.sum(0)
    q = valid & (E <= np.percentile(E[valid], 10))
    glob = np.median(Ps[:, q], axis=1)
    Pf = Ps.copy()
    Pf[:, ~valid] = glob[:, None]
    sub = 4
    win = max(3, int(window_s * sr / HOP / sub) | 1)
    Nd = percentile_filter(Pf[:, ::sub], pct, size=(1, win), mode="nearest")
    m_eff = max(1.0, msm / 2.5)
    bias = m_eff / _gamma.ppf(pct / 100.0, m_eff)
    xs, tt = np.arange(Nd.shape[1]), np.arange(nt) / sub
    N = np.empty((nb, nt), np.float32)
    for k in range(nb):
        N[k] = np.interp(tt, xs, Nd[k])
    N = uniform_filter1d(N * bias, size=7, axis=0)
    N = uniform_filter1d(N, size=25, axis=1)
    return np.maximum(N, 1e-20).astype(np.float32)


def _learn(mono, sr, P):
    nb, nt = P.shape
    L = _frames(mono, sr, nt)
    valid = L > -110.0
    if valid.sum() < 50:
        return {"skip": "digital silence / too short"}
    p10, p90 = np.percentile(L[valid], 10), np.percentile(L[valid], 90)
    if p90 < -95.0:
        return {"skip": "stem is inaudible"}
    act = L > p90 - 20.0
    gap = _runs((L < p10 + 6.0) & valid, 8)
    if p90 - p10 >= 15.0 and gap.sum() >= 20:
        return {"L": L, "valid": valid, "gap": gap, "act": act, "mode": "gap-profile",
                "noise_dbfs": float(np.median(L[gap])),
                "rel": float(np.median(L[act]) - np.median(L[gap]))}
    # no clear gaps: track the noise continuously instead of giving up
    N = _tracker(P, valid, 3.0, sr)
    snr = 10 * np.log10((P.sum(0) + 1e-20) / (N.sum(0) + 1e-20))
    rel = float(np.median(snr[act])) if act.any() else 0.0
    q = valid & (L <= np.percentile(L[valid], 12))
    return {"L": L, "valid": valid, "gap": q, "act": act, "mode": "continuous-tracker", "N": N,
            "noise_dbfs": float(np.median(L[act]) - rel), "rel": rel}


def _plan(info, strength, role):
    if "skip" in info:
        return 0.0, info["skip"]
    if info["noise_dbfs"] < -80.0:
        return 0.0, "noise below -80 dBFS (inaudible)"
    depth = float(np.clip((72.0 - info["rel"]) / 3.0, 0.0, MAX_DEPTH)) * ROLE.get(role, 1.0) * float(np.clip(strength, 0.0, 1.0))
    return (depth, "ok") if depth >= MIN_DEPTH else (0.0, "already clean enough (SNR %.0f dB)" % info["rel"])


def _profile(P, gap, L):
    prof = np.median(P[:, gap], axis=1)
    prof = uniform_filter1d(prof, size=5, mode="nearest") + 1e-20
    gsum = P[:, gap].sum(axis=0) / prof.sum()
    gi = np.flatnonzero(gap)
    g = np.interp(np.arange(P.shape[1]), gi, np.clip(gsum, 0.25, 4.0))
    return prof, uniform_filter1d(g, size=15, mode="nearest")


def _noise_matrix(P, info):
    if info["mode"] == "continuous-tracker":
        return info["N"]
    prof, gt = _profile(P, info["gap"], info["L"])
    return (prof[:, None] * gt[None, :]).astype(np.float32)


# ----------------------------------------------------------------------------- pre-filters: rumble HP + hum notches
def _find_hum(chan, sr, info):
    """Hum is STATIONARY: it is still there in the 25th-percentile spectrum over the whole stem, while voice and
    phrase noise move around.  Narrow peaks (3 Hz resolution) on 50/60 Hz harmonics, >=2 of them, >=10 dB over neighbours."""
    nper = 16384
    if len(chan) < nper * 4:
        return []
    f, _, Z = sg.stft(chan, sr, window="hann", nperseg=nper, noverlap=nper // 2, boundary=None)
    Pw = np.abs(Z) ** 2
    keep = Pw.sum(0) > 1e-20
    if keep.sum() < 6:
        return []
    pd = 10 * np.log10(np.percentile(Pw[:, keep], 25, axis=1) + 1e-30)
    for base in (50.0, 60.0):
        hits = []
        for h in range(1, 7):
            fc = base * h
            if fc > 800:
                break
            band = (f > fc - 1.5) & (f < fc + 1.5)
            around = ((f > fc - 12) & (f < fc - 5)) | ((f > fc + 5) & (f < fc + 12))
            if band.any() and around.any() and pd[band].max() - np.median(pd[around]) > 10.0:
                hits.append(fc)
        if len(hits) >= 2:
            top = int(round(max(hits) / base))                 # notch every harmonic up to one above the highest found
            return [base * k for k in range(1, min(top + 1, 8) + 1) if base * k <= 800]
    return []


def _prefilter(chan, sr, hum):
    y = chan - np.mean(chan)
    y = sg.sosfiltfilt(sg.butter(4, HP_HZ, "hp", fs=sr, output="sos"), y)
    for fc in hum:
        b, a = sg.iirnotch(fc, Q=40, fs=sr)
        y = sg.filtfilt(b, a, y)
    return y


# ----------------------------------------------------------------------------- gain
def _gain(P, N, act_frames, depth, alpha, L, sr, rule):
    nb, nt = P.shape
    gmin_gap = np.full(nb, 10 ** (-depth / 20.0))
    gmin_act = np.full(nb, 10 ** (-min(depth, ACTIVE_DEPTH) / 20.0))
    G = np.empty((nb, nt), np.float32)
    Gp, Pp = np.ones(nb), np.zeros(nb)
    for t in range(nt):
        Nt = N[:, t]
        gamma = P[:, t] / Nt
        xi = alpha * (Gp * Gp * Pp / Nt) + (1.0 - alpha) * np.maximum(gamma - 1.0, 0.0)
        if rule == "lsa":
            xi = np.maximum(xi, 10 ** (-25 / 10))
            v = xi / (1.0 + xi) * gamma
            g = np.minimum(xi / (1.0 + xi) * np.exp(0.5 * exp1(np.maximum(v, 1e-8))), 1.0)
        else:
            g = xi / (1.0 + xi)
        g = np.maximum(g, gmin_act if act_frames[t] else gmin_gap)
        G[:, t] = g
        Gp, Pp = g, P[:, t]
    G = uniform_filter1d(G, size=3, axis=0, mode="nearest")
    decay = np.exp(-(HOP / float(sr)) / 0.050)
    for t in range(1, nt):
        G[:, t] = np.maximum(G[:, t], G[:, t - 1] * decay)
    rise = np.flatnonzero(L[3:] - L[:-3] > 6.0) + 3
    for t in rise:
        G[:, max(0, t - 1):t + 2] = np.maximum(G[:, max(0, t - 1):t + 2], 0.7)
    return G


def _bands(sr):
    c = np.array([150, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000.0])
    return [(int(f / 2 ** (1 / 6) / (sr / NFFT)), int(f * 2 ** (1 / 6) / (sr / NFFT))) for f in c]


def _guard(P, G, act, gap, sr, N):
    devs = []
    ai = np.flatnonzero(act)
    for a, b in _bands(sr):
        Pa = P[a:b][:, ai]
        m = Pa > 10.0 * N[a:b][:, ai]
        if m.sum() < 50:
            continue
        before = Pa[m].sum()
        after = ((G[a:b][:, ai] ** 2) * Pa)[m].sum()
        devs.append(abs(10 * np.log10((after + 1e-30) / (before + 1e-30))))
    devs = devs or [0.0]
    b0, b1 = _bands(sr)[0][0], _bands(sr)[-1][1]
    gdb = 20 * np.log10(G[b0:b1][:, gap] + 1e-9)
    return float(np.mean(devs)), float(np.max(devs)), float(np.mean(np.std(gdb, axis=1)))


# ----------------------------------------------------------------------------- public API
def analyse(x, sr, role="lead", strength=1.0):
    x = np.asarray(x, np.float64)
    mono = x if x.ndim == 1 else x.mean(axis=0)
    if len(mono) < 2 * sr:
        return {"plan": "skip", "reason": "too short"}
    _, _, Z = sg.stft(mono, sr, window="hann", nperseg=NFFT, noverlap=NFFT - HOP)
    info = _learn(mono, sr, (np.abs(Z) ** 2).astype(np.float32))
    depth, why = _plan(info, strength, role)
    return {"plan": "clean" if depth else "skip", "reason": why, "depth_db": round(depth, 1),
            "noise_source": info.get("mode", "n/a"),
            "noise_dbfs": round(info.get("noise_dbfs", float("nan")), 1), "snr_db": round(info.get("rel", float("nan")), 1)}


def clean(x, sr, role="lead", strength=1.0, rule="wiener", return_gain=False):
    t0 = time.time()
    x = np.asarray(x, np.float64)
    rep = {"role": role}
    if role == "beat":
        rep["action"] = "skipped (beat is never denoised)"
        return x, rep
    mono0 = x if x.ndim == 1 else x.mean(axis=0)
    n = mono0.shape[-1]
    if n < 2 * sr:
        rep["action"] = "skipped (too short)"
        return x, rep

    # 1) DECIDE on the untouched stem (rumble counts as noise here, so a rumble-only stem is still cleaned)
    _, _, Z0 = sg.stft(mono0, sr, window="hann", nperseg=NFFT, noverlap=NFFT - HOP)
    info0 = _learn(mono0, sr, (np.abs(Z0) ** 2).astype(np.float32))
    depth, why = _plan(info0, strength, role)
    rep.update(noise_dbfs=round(info0.get("noise_dbfs", float("nan")), 1), snr_db=round(info0.get("rel", float("nan")), 1))
    if depth == 0.0:
        rep["action"] = "skipped (%s)" % why
        return (x, rep) if not return_gain else (x, rep, None)

    # 2) PRE-FILTER: rumble high-pass + real hum notches
    hum = _find_hum(mono0, sr, info0)
    chans0 = [x] if x.ndim == 1 else [x[0], x[1]]
    chans = [_prefilter(c, sr, hum) for c in chans0]
    mono = chans[0] if x.ndim == 1 else 0.5 * (chans[0] + chans[1])

    # 3) LEARN again on the pre-filtered audio (depth stays as decided above)
    Zs = [sg.stft(c, sr, window="hann", nperseg=NFFT, noverlap=NFFT - HOP)[2].astype(np.complex64) for c in chans]
    P = np.mean([np.abs(Z) ** 2 for Z in Zs], axis=0).astype(np.float32)
    info = _learn(mono, sr, P)
    if "skip" in info:
        info = info0
        P = (np.abs(Z0) ** 2).astype(np.float32)
    L, gap, act = info["L"], info["gap"], info["act"]
    N = _noise_matrix(P, info)

    # 4) CLEAN with self-check (retries gentler if the voice moves or the gaps flutter)
    attempts, best = [], None

    def judge(G, rec):
        dev_mean, dev_max, flutter = _guard(P, G, act, gap, sr, N)
        rec.update(voice_change_db=round(dev_mean, 2), flutter_db=round(flutter, 2))
        attempts.append(rec)
        return max(dev_mean / DEV_LIMIT_DB, flutter / FLUTTER_LIMIT_DB), G

    G = None
    for alpha, mult in ((0.98, 1.0), (0.985, 1.0), (0.985, 0.7), (0.99, 0.5)):
        G = _gain(P, N, act, depth * mult, alpha, L, sr, rule)
        score, G = judge(G, {"depth_db": round(depth * mult, 1)})
        if best is None or score < best[0]:
            best = (score, G, dict(attempts[-1]))
        if score <= 1.0:
            break
    if best[0] > 1.0:
        base = G
        for w in (0.6, 0.4, 0.25):
            Gb = ((1.0 - w) + w * base).astype(np.float32)
            score, Gb = judge(Gb, {"depth_db": round(depth * 0.5, 1), "wet_blend": w})
            if score < best[0]:
                best = (score, Gb, dict(attempts[-1]))
            if score <= 1.0:
                break
    G = best[1]
    final = best[2]
    outs = [sg.istft(Z * G, sr, window="hann", nperseg=NFFT, noverlap=NFFT - HOP)[1][:n] for Z in Zs]
    y = outs[0] if x.ndim == 1 else np.stack(outs)
    mo = y if y.ndim == 1 else y.mean(axis=0)
    Lo = _frames(mo, sr, P.shape[1])
    rep.update(action="cleaned", noise_source=info["mode"], gain_rule=rule, highpass_hz=HP_HZ, hum_hz=hum or None,
               depth_requested_db=round(depth, 1),
               gap_noise_reduction_db=round(float(np.median(L[gap]) - np.median(Lo[gap])), 1),
               voice_change_db=final["voice_change_db"], flutter_db=final["flutter_db"], applied=final, attempts=attempts,
               quality_guard="passed" if best[0] <= 1.0 else "limits not met - the least damaging setting was used",
               seconds=round(time.time() - t0, 1))
    return (y, rep) if not return_gain else (y, rep, G)
