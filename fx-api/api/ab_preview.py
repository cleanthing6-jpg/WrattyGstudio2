"""
ab_preview.py -- the BEFORE / AFTER 30-second preview for the Studio page and for marketing.
"""
import os
import subprocess
import numpy as np
import scipy.signal as sg
from scipy import ndimage

try:
    from master_bus import lufs as _lufs_bs1770
except Exception:
    _lufs_bs1770 = None

def _cn(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return np.stack([x, x])
    return x if x.shape[0] <= 2 else x.T

def _loud(x, sr):
    if _lufs_bs1770 is not None:
        try:
            return float(_lufs_bs1770(x, sr))
        except Exception:
            pass
    return float(10 * np.log10((x ** 2).mean() + 1e-12))

def pick_window(mixed, sr, seconds=30.0, bpm=None, skip_first_s=8.0):
    n = mixed.shape[1]; total = n / sr
    if total <= seconds + 1.0:
        return 0.0
    blk = int(3 * sr); hop = int(sr)
    st = []
    for i in range(0, n - blk, hop):
        seg = mixed[:, i:i + blk]
        st.append(_loud(seg, sr) if np.abs(seg).max() > 1e-4 else -80.0)
    st = np.array(st)
    win = int(seconds)
    lo = int(min(skip_first_s, max(0.0, total - seconds - 1.0)))
    best, bs = -1e9, 0
    for s in range(lo, len(st) - win + 1):
        w = st[s:s + win]
        if (w < -50).sum() > 2:
            continue
        score = float(np.mean(np.maximum(w, -40.0)))
        if score > best:
            best, bs = score, s
    start = float(bs)
    if bpm and 50 <= bpm <= 210:
        bar = 240.0 / bpm
        start = round(start / bar) * bar
        start = float(np.clip(start, 0.0, total - seconds))
    return start

def _fade(x, sr, ms=30.0):
    k = int(ms / 1000.0 * sr)
    if k < 2 or x.shape[1] < 4 * k:
        return x
    w = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k))
    x = x.copy(); x[:, :k] *= w; x[:, -k:] *= w[::-1]
    return x

def sync_offset_ms(a, b, sr):
    bp = sg.butter(4, [150, 2500], btype="band", fs=sr, output="sos")
    ea = np.abs(sg.sosfilt(bp, a.mean(0))); eb = np.abs(sg.sosfilt(bp, b.mean(0)))
    d = max(1, int(sr / 2000))
    ea = ndimage.uniform_filter1d(ea, int(0.004 * sr))[::d]; eb = ndimage.uniform_filter1d(eb, int(0.004 * sr))[::d]
    ea = ea - ea.mean(); eb = eb - eb.mean()
    n = min(len(ea), len(eb)); W = int(0.05 * 2000)
    full = sg.fftconvolve(eb[:n], ea[:n][::-1], mode="full")
    mid = n - 1
    seg = full[mid - W: mid + W + 1]
    return float((np.argmax(seg) - W) / 2.0)

def make_ab_preview(raw_mix, mixed, sr, bpm=None, seconds=30.0, ceiling_db=-1.0, match=True):
    r = _cn(raw_mix); m = _cn(mixed)
    n = min(r.shape[1], m.shape[1]); r, m = r[:, :n], m[:, :n]
    t0 = pick_window(m, sr, seconds, bpm)
    a = int(t0 * sr); z = min(n, a + int(seconds * sr))
    r30, m30 = _fade(r[:, a:z], sr), _fade(m[:, a:z], sr)
    ceil = 10 ** (ceiling_db / 20.0)
    if np.abs(m30).max() > ceil:
        m30 = m30 * (ceil / np.abs(m30).max())
    lr, lm = _loud(r30, sr), _loud(m30, sr)
    want = float(np.clip(lm - lr, -18.0, 18.0)) if match else 0.0
    g = 10 ** (want / 20.0)
    pk = np.abs(r30).max() * g
    if pk > ceil:
        g *= ceil / pk
    r30 = r30 * g
    got = 20 * np.log10(g)
    mixed_gain = 0.0
    gap = float(_loud(m30, sr) - _loud(r30, sr))
    if match and gap > 0.7:
        mixed_gain = -gap
        m30 = m30 * 10 ** (mixed_gain / 20.0)
    info = {"start_s": round(t0, 2), "seconds": round((z - a) / sr, 2), "raw_lufs": round(_loud(r30, sr), 2),
            "mixed_lufs": round(_loud(m30, sr), 2), "raw_gain_db": round(float(got), 2), "mixed_gain_db": round(float(mixed_gain), 2),
            "level_gap_db": round(float(_loud(m30, sr) - _loud(r30, sr)), 2), "sync_ms": sync_offset_ms(r30, m30, sr)}
    info["fair_ab"] = bool(abs(info["level_gap_db"]) <= 0.7 and abs(info["sync_ms"]) <= 5.0)
    return {"raw": r30.astype(np.float32), "mixed": m30.astype(np.float32), "info": info}

def write_mp3(path, data, sr, kbps=256):
    d = np.asarray(data, dtype=np.float32)
    d = d.T if d.ndim == 2 and d.shape[0] <= 2 else d
    try:
        import soundfile as sf
        sf.write(path, d, sr, format="MP3", subtype="MPEG_LAYER_III", bitrate_mode="CONSTANT", compression_level=0.0)
        return path
    except Exception:
        tmp = path + ".wav"
        import scipy.io.wavfile as w
        w.write(tmp, sr, (np.clip(d, -1, 1) * 32767).astype(np.int16))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-b:a", "%dk" % kbps, path], check=True)
        os.remove(tmp)
        return path
