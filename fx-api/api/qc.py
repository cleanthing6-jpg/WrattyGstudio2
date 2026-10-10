"""
qc.py - advisory audio QC for WrattyGstudio.  numpy only (no scipy).
"""
import json
import re
import subprocess
import sys

import numpy as np

QC_LIMITS = {
    "clip_level": 0.999,
    "clip_runs_flag": 20,
    "hot_peak_db": -0.1,
    "quiet_active_rms_db": -35.0,
    "noise_floor_flag_db": -50.0,
    "sparse_active_ratio": 0.35,
    "out_plr_min_db": 7.0,
    "out_mono_loss_max_db": 3.0,
    "out_corr_min": 0.20,
    "out_sub_gap_max_db": 8.0,
    "out_tp_margin_db": 0.3,
}

BANDS = [(20, 60), (60, 120), (120, 250), (250, 600),
         (600, 2000), (2000, 5500), (5500, 10000), (10000, 16000)]

_VOCAL_WORDS = ("lead", "adlib", "ad-lib", "backing", "vocal", "vox", "harmony", "bv")


def _arr(a):
    a = np.asarray(a)
    if a.ndim == 1:
        a = a[None, :]
    if a.shape[0] > a.shape[1]:
        a = a.T
    return a.astype(np.float64, copy=False)


def _db(v):
    return float(20.0 * np.log10(max(float(v), 1e-12)))


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def clip_stats(a, level=None):
    level = QC_LIMITS["clip_level"] if level is None else level
    hit = (np.abs(_arr(a)) >= level).any(axis=0)
    d = np.diff(np.concatenate([[0], hit.astype(np.int8), [0]]))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    runs = ends - starts
    return {
        "clipped_samples": int(hit.sum()),
        "clip_runs": int(runs.size),
        "clip_runs_ge3": int((runs >= 3).sum()),
        "clip_max_run": int(runs.max()) if runs.size else 0,
    }


def activity(a, sr, frame_s=0.05, gate_db=-45.0):
    m = _arr(a).mean(axis=0)
    w = max(1, int(frame_s * sr))
    k = len(m) // w
    if k < 1:
        return {"active_ratio": 0.0, "whole_rms_db": _db(_rms(m)),
                "active_rms_db": _db(_rms(m)), "noise_floor_db": None}
    seg = m[: k * w].reshape(k, w)
    fr = 20.0 * np.log10(np.sqrt((seg ** 2).mean(axis=1)) + 1e-12)
    act = fr > gate_db
    out = {
        "active_ratio": round(float(act.mean()), 3),
        "whole_rms_db": round(_db(_rms(m)), 2),
        "active_rms_db": round(_db(_rms(seg[act])) if act.any() else _db(_rms(m)), 2),
    }
    out["noise_floor_db"] = round(float(np.percentile(fr[~act], 10)), 1) if (~act).any() else None
    return out


def f0_percentiles(a, sr, max_frames=4000):
    x = _arr(a).mean(axis=0)
    N, H = 2048, 512
    lo, hi = int(sr / 600), int(sr / 70)
    win = np.hanning(N)
    starts = np.arange(0, len(x) - N, H)
    if starts.size == 0:
        return None
    if starts.size > max_frames * 3:
        starts = starts[:: int(starts.size // (max_frames * 3))]
    f0 = []
    for i in starts:
        s = x[i:i + N]
        if _db(_rms(s)) < -40.0:
            continue
        F = np.fft.rfft(s * win, 2 * N)
        ac = np.fft.irfft(np.abs(F) ** 2)[:N]
        ac = ac / (ac[0] + 1e-12)
        seg = ac[lo:hi]
        j = int(np.argmax(seg))
        if seg[j] > 0.5:
            f0.append(sr / (lo + j))
        if len(f0) >= max_frames:
            break
    if len(f0) < 20:
        return None
    p = np.percentile(f0, [2, 5, 50, 95])
    return {"f0_p2": round(float(p[0])), "f0_p5": round(float(p[1])),
            "f0_p50": round(float(p[2])), "f0_p95": round(float(p[3])),
            "voiced_frames": len(f0)}


def band_levels_db(a, sr, nfft=16384):
    x = _arr(a)
    w = np.hanning(nfft)
    norm = nfft * float(np.sum(w ** 2))
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    acc = np.zeros(freqs.size)
    cnt = 0
    for ch in range(x.shape[0]):
        for i in range(0, x.shape[1] - nfft, nfft // 2):
            X = np.fft.rfft(x[ch, i:i + nfft] * w)
            p = (np.abs(X) ** 2) * 2.0 / norm
            acc += p
            cnt += 1
    if cnt == 0:
        return {}
    acc /= cnt
    out = {}
    for lo, hi in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        out["%d-%d" % (lo, hi)] = round(10.0 * np.log10(float(acc[m].sum()) + 1e-20), 1)
    return out


def stereo_stats(a):
    x = _arr(a)
    if x.shape[0] < 2:
        return {"corr": 1.0, "mono_loss_db": 0.0, "side_minus_mid_db": None, "mono_file": True}
    L, R = x[0], x[1]
    d = float(np.std(L) * np.std(R))
    corr = float(np.mean((L - L.mean()) * (R - R.mean())) / d) if d > 1e-12 else 1.0
    mid, side = (L + R) / 2, (L - R) / 2
    avg = np.sqrt((_rms(L) ** 2 + _rms(R) ** 2) / 2)
    return {
        "corr": round(corr, 3),
        "mono_loss_db": round(_db(_rms(mid)) - _db(avg), 2),
        "side_minus_mid_db": round(_db(_rms(side)) - _db(_rms(mid)), 1),
        "mono_file": bool(corr > 0.999),
    }


def stem_qc(a, sr, role="stem"):
    x = _arr(a)
    L = QC_LIMITS
    out = {"role": str(role), "duration_s": round(x.shape[1] / float(sr), 2),
           "peak_db": round(_db(np.abs(x).max()), 2)}
    out.update(clip_stats(x))
    out.update(activity(x, sr))
    out.update(stereo_stats(x))
    flags = []
    if out["clip_runs_ge3"] >= L["clip_runs_flag"]:
        flags.append("clipped_input")
    if out["peak_db"] >= L["hot_peak_db"]:
        flags.append("hot_peak")
    if out["active_rms_db"] < L["quiet_active_rms_db"]:
        flags.append("very_quiet")
    if out["noise_floor_db"] is not None and out["noise_floor_db"] > L["noise_floor_flag_db"]:
        flags.append("noisy")
    if out["active_ratio"] < L["sparse_active_ratio"]:
        flags.append("sparse")
    if any(w in str(role).lower() for w in _VOCAL_WORDS):
        f0 = f0_percentiles(x, sr)
        if f0:
            out.update(f0)
            out["suggested_hpf_hz"] = int(min(110, max(70, 0.8 * f0["f0_p2"])))
    out["flags"] = flags
    return out


def output_qc(a, sr, lufs=None, true_peak_db=None, ceiling_db=-1.0):
    x = _arr(a)
    L = QC_LIMITS
    out = {"peak_db": round(_db(np.abs(x).max()), 2)}
    if lufs is not None:
        out["lufs"] = round(float(lufs), 2)
    if true_peak_db is not None:
        out["true_peak_db"] = round(float(true_peak_db), 2)
    if lufs is not None and true_peak_db is not None:
        out["plr_db"] = round(float(true_peak_db) - float(lufs), 2)
    out.update(stereo_stats(x))
    bl = band_levels_db(x, sr)
    out["bands_db"] = bl
    if bl:
        out["sub_minus_mid_db"] = round(bl["20-60"] - bl["600-2000"], 1)
        out["dip_250_600_db"] = round(bl["250-600"] - 0.5 * (bl["120-250"] + bl["600-2000"]), 1)
        out["top_minus_presence_db"] = round(bl["5500-10000"] - bl["2000-5500"], 1)
    out["full_scale_samples"] = int((np.abs(x) >= 0.9999).sum())
    flags = []
    if true_peak_db is not None and true_peak_db > ceiling_db + L["out_tp_margin_db"]:
        flags.append("true_peak_over_ceiling")
    if out["full_scale_samples"] > 0:
        flags.append("full_scale_samples")
    if "plr_db" in out and out["plr_db"] < L["out_plr_min_db"]:
        flags.append("low_plr")
    if out["mono_loss_db"] < -L["out_mono_loss_max_db"]:
        flags.append("mono_loss")
    if out["corr"] < L["out_corr_min"]:
        flags.append("low_correlation")
    if out.get("sub_minus_mid_db", 0) > L["out_sub_gap_max_db"]:
        flags.append("sub_heavy")
    out["flags"] = flags
    return out


def _decode(path):
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-acodec", "pcm_f32le",
           "-ac", "2", "-ar", "44100", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.astype(np.float64), 44100


def _ffmpeg_loudness(path):
    p = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-af", "ebur128=peak=true",
                        "-f", "null", "-"], stderr=subprocess.PIPE, text=True)
    s = p.stderr.split("Summary:")[-1]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", s)
    t = re.search(r"Peak:\s+(-?[\d.]+) dBFS", s)
    return (float(i.group(1)) if i else None, float(t.group(1)) if t else None)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    role = sys.argv[2] if len(sys.argv) > 2 else "stem"
    a, sr = _decode(path)
    if role in ("master", "mix", "output"):
        lu, tp = _ffmpeg_loudness(path)
        print(json.dumps(output_qc(a, sr, lu, tp), indent=2))
    else:
        print(json.dumps(stem_qc(a, sr, role), indent=2))
