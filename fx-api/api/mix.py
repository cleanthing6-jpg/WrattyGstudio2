"""wratty-fx mixer: sums stems, glue bus, LUFS master. Replaces RoEx."""
import gc, json, os, shutil, tempfile, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import requests
from pedalboard import Pedalboard, HighpassFilter, PeakFilter, Compressor
from limiter import Limiter
try:
    from pedalboard import BrickwallLimiter
except Exception:  # pedalboard < 0.9.25
    BrickwallLimiter = None
from pedalboard.io import AudioFile

import auto

def _dyn9010(x, sr, win=0.4):
    x = np.asarray(x)
    if x.ndim > 1:
        x = x.mean(axis=0 if x.shape[0] <= x.shape[1] else 1)
    x = x.reshape(-1).astype(np.float64)
    """Macro-dynamics: 90th-10th percentile of 0.4s RMS (dB).
    Same metric compare.py prints, so the log is directly comparable."""
    x = np.asarray(x)
    if x.ndim > 1:                    # (ch, samples) or (samples, ch) -> mono
        ax = 0 if x.shape[0] <= x.shape[1] else 1
        x = x.mean(axis=ax)
    x = x.reshape(-1).astype(np.float64)
    w = max(1, int(win * sr))
    n = len(x) // w
    if n < 5:
        return None
    seg = x[:n * w].reshape(n, w)
    r = 20.0 * np.log10(np.sqrt((seg ** 2).mean(axis=1)) + 1e-12)
    r = r[r > -60.0]
    if len(r) < 5:
        return None
    return float(np.percentile(r, 90) - np.percentile(r, 10))

try:
    import pyloudnorm as pyln
except Exception:
    pyln = None

TARGET = {"LOW": -16.0, "MEDIUM": -14.0, "HIGH": -11.5}
JOBS, LK = {}, threading.Lock()



def rmsdb(x):
    m = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    return 20.0 * np.log10(m + 1e-12)


def peakdb(x):
    return 20.0 * np.log10(float(np.max(np.abs(x))) + 1e-12)


def lufs(x, sr):
    """Real gated K-weighted loudness (BS.1770-4), from the engine."""
    try:
        return auto.integrated_lufs(x, sr)
    except Exception:
        return None


def load(p, max_sec=0.0):
    with AudioFile(p) as f:
        n = int(f.frames)
        if max_sec:
            cap = max(1, int(float(max_sec) * float(f.samplerate)))
            if cap < n:
                n = cap
        return f.read(n), int(f.samplerate)


def save16(p, a, sr):
    a = np.ascontiguousarray(a, dtype=np.float32)
    np.clip(a, -1.0, 1.0, out=a)
    rng = np.random.default_rng()
    flat = a.reshape(-1)
    for i in range(0, flat.size, 1 << 20):
        part = flat[i:i + (1 << 20)]
        noise = rng.random(part.size, dtype=np.float32)
        noise -= rng.random(part.size, dtype=np.float32)
        noise *= np.float32(1.0 / 32768.0)
        part += noise
        np.clip(part, -1.0, 1.0, out=part)
    with AudioFile(p, "w", int(sr), a.shape[0]) as f:
        try:
            f.bit_depth = 16
        except Exception:
            pass
        f.write(a)


def to_sr(a, si, so):
    if si == so:
        return a
    n = int(round(a.shape[1] * so / float(si)))
    x = np.linspace(0.0, a.shape[1] - 1.0, n)
    i = np.arange(a.shape[1], dtype=np.float64)
    return np.stack([np.interp(x, i, c.astype(np.float64)).astype(np.float32) for c in a])


def _fx_ticket(scope="read", ttl=600):
    import hashlib
    import hmac
    import os
    import time

    key = os.environ.get("FX_INTERNAL_SECRET", "")
    if not key:
        return ""
    exp = int(time.time()) + ttl
    sig = hmac.new(
        key.encode(), f"{scope}|{exp}".encode(), hashlib.sha256
    ).hexdigest()
    return f"{exp}.{sig}"


def _reject_private(url):
    """The submitted host is checked in the API, but a redirect can land
    anywhere. Re-check the FINAL url after requests has followed any
    redirects, so a public host cannot bounce us at the metadata endpoint."""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if not host or host == "localhost" or host.endswith((".local", ".internal")):
        raise RuntimeError("refusing to fetch a private host")
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        raise RuntimeError("could not resolve stem host")
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise RuntimeError("refusing to fetch a private address")

def grab(u, dst):
    tk = _fx_ticket("read")
    headers = {"x-fx-ticket": tk} if tk else {}
    if not tk:
        raise RuntimeError("FX_INTERNAL_SECRET is missing in the mix worker")
    with requests.get(u, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        _reject_private(r.url)
        with open(dst, "wb") as fh:
            for c in r.iter_content(1 << 16):
                fh.write(c)


_ENCODE_ERR = None


def encode_all(src, tmp, is_preview):
    """Previews: MP3 only. Full renders: MP3 AND FLAC, both encoded from the
    SAME decoded audio - the master is never rendered twice."""
    global _ENCODE_ERR
    try:
        import soundfile as sf
        data, sr = sf.read(src, dtype="float32", always_2d=True)
        out = []
        mp3 = os.path.join(tmp, "mix.mp3")
        sf.write(mp3, data, sr, format="MP3", subtype="MPEG_LAYER_III", bitrate_mode="CONSTANT", compression_level=0.0)
        out.append((mp3, "audio/mpeg", ".mp3"))
        if not is_preview:
            flac = os.path.join(tmp, "mix.flac")
            sf.write(flac, data, sr, format="FLAC", subtype="PCM_16",
                     compression_level=0.5)
            out.append((flac, "audio/flac", ".flac"))
        return out, None
    except Exception as e:
        _ENCODE_ERR = str(e)[:200]
        return [(src, "audio/wav", ".wav")], _ENCODE_ERR


def encode_out(src, tmp, is_preview):
    """MP3 for previews, FLAC for full renders. Falls back to the WAV."""
    global _ENCODE_ERR
    try:
        import soundfile as sf
        data, sr = sf.read(src, dtype="float32", always_2d=True)
        if is_preview:
            dst = os.path.join(tmp, "mix.mp3")
            sf.write(dst, data, sr, format="MP3", subtype="MPEG_LAYER_III", bitrate_mode="CONSTANT", compression_level=0.0)
            return dst, "audio/mpeg", ".mp3", None
        dst = os.path.join(tmp, "mix.flac")
        sf.write(dst, data, sr, format="FLAC", subtype="PCM_16", compression_level=0.5)
        return dst, "audio/flac", ".flac", None
    except Exception as e:
        _ENCODE_ERR = str(e)[:200]
        return src, "audio/wav", ".wav", _ENCODE_ERR


def put(p, name, ctype="audio/wav"):
    # Modal volume ONLY. The Vercel Blob fallback is gone: it needed
    # BLOB_READ_WRITE_TOKEN, which no longer exists, so a volume hiccup used
    # to surface as a bogus "token missing" and kill the render. Fail loudly.
    import blobstore
    url = blobstore.put(p, name)
    print("PUT modal %s" % url, flush=True)
    return url


def rss_mb():
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except Exception:
        pass
    return None


def setjob(jid, status, url=""):
    with LK:
        j = JOBS.get(jid) or {}
        j["status"] = status
        j["rss_mb"] = rss_mb()
        if url:
            j["url"] = url
        JOBS[jid] = j
        _st, _rss = j.get("status"), j.get("rss_mb")
    print("[job %s] %-18s rss=%s MB" % (jid[:8], _st, _rss), flush=True)



# ---- role panning. PAN_ENABLED=False fully reverts. ----
PAN_ENABLED = True
PAN_HZ = 200.0
PAN_VALUES = {
    "backing": (-0.55, 0.55, -0.35, 0.35),
    "adlib":   (-0.70, 0.70, -0.50, 0.50),
}
_PAN_N = {"backing": 0, "adlib": 0}
_PAN_REPORT = {"backing": [], "adlib": []}

def do_mix(stems, loud, jid, max_sec=0, preset="neutral"):
    # Reset per-render state so a previous job in this warm container
    # cannot leak plate/delay/reverb data into this render's report or audio.
    try:
        auto._PLATE.clear(); auto._PLATE.update({"ir": {}, "err": "", "kind": ""})
        auto._HALL.clear(); auto._HALL.update({"ir": {}})
        auto._DBL.clear(); auto._DBL.update({"kind": ""})
        auto._REVERB_LAST.clear()
        auto._DELAY_LAST.clear()
        auto._PAR_LAST.clear()
        auto._EXC_LAST.clear()
        auto._FAST_LOUDNESS_CACHE.clear()
    except Exception:
        pass
    tmp = tempfile.mkdtemp()
    try:
        cfg = auto.apply_preset(preset)
        try:
            try:
                import qc as _qc
            except ImportError:
                from . import qc as _qc
        except Exception:
            _qc = None
        sr = None
        groups = {"beat": [], "lead": [], "adlib": [], "backing": [], "other": []}
        _qc_in = {}
        for i, s in enumerate(stems):
            setjob(jid, "stem %d of %d" % (i + 1, len(stems)))
            p = os.path.join(tmp, "%d.wav" % i)
            grab(s["url"], p)
            a, s0 = load(p)
            os.remove(p)
            if len(a[0]) / float(s0) > 480:
                raise ValueError("stem longer than 8 minutes")
            if sr is None:
                sr = s0
            elif s0 != sr:
                a = to_sr(a, s0, sr)
            if max_sec:
                a = a[:, : max(1, int(max_sec * sr))]
            if a.shape[0] == 1:
                a = np.repeat(a, 2, axis=0)
            a = np.ascontiguousarray(a[:2].astype(np.float32))
            role = s.get("role") or s.get("name") or "stem"
            if _qc is not None:
                try:
                    _qc_in[str(i)] = _qc.stem_qc(a, sr, role)
                except Exception:
                    pass
            if i == 0:
                _PAN_N.update({"backing": 0, "adlib": 0})
                _PAN_REPORT.update({"backing": [], "adlib": []})
                _PAN_NB = sum(1 for _s in stems if auto.bucket(_s.get("role") or _s.get("name") or "stem") == "backing")
            bucket = auto.bucket(role)
            if PAN_ENABLED and bucket in PAN_VALUES:
                k = _PAN_N[bucket]
                pan = PAN_VALUES[bucket][k % len(PAN_VALUES[bucket])]
                _PAN_N[bucket] += 1
                _hi = Pedalboard([HighpassFilter(
                    cutoff_frequency_hz=PAN_HZ)])(a, sr).astype(np.float32)
                _lo = (a - _hi).astype(np.float32)
                _hi[0] *= float(np.sqrt(1.0 - 0.8 * pan))
                _hi[1] *= float(np.sqrt(1.0 + 0.8 * pan))
                a = np.ascontiguousarray((_lo + _hi).astype(np.float32))
                _PAN_REPORT[bucket].append({"stem": i, "pan": pan})
                if bucket == "backing":
                    try:
                        _wm = (a[0] + a[1]) * 0.5
                        _ws = (a[0] - a[1]) * 0.5 * 1.25
                        a = np.stack([_wm + _ws, _wm - _ws]).astype(np.float32)
                    except Exception:
                        pass
            groups[bucket].append(a)

        setjob(jid, "analysing")
        mixed, report = auto.mix(groups, sr)

        # Trim trailing silence — end the render where the audio actually ends
        try:
            _orig_len = mixed.shape[1]
            _m = mixed.mean(axis=0) if mixed.ndim > 1 else mixed
            _win = max(1, int(sr * 0.05))
            _nf = len(_m) // _win
            if _nf > 4:
                _env = _m[:_nf * _win].reshape(_nf, _win).max(axis=1)
                _thr = float(_env.max()) * 0.005
                _above = np.where(_env > _thr)[0]
                if _above.size > 0:
                    _last = int((_above[-1] + 1) * _win) + int(sr * 0.5)
                    _last = min(_last, _orig_len)
                    if _last < _orig_len - sr:
                        mixed = mixed[:, :_last]
                        report["trimmed_tail_s"] = round((_orig_len - _last) / float(sr), 2)
        except Exception as _e:
            report["trim_error"] = str(_e)[:120]
        report["input_qc"] = _qc_in

        report["role_pan"] = {"on": PAN_ENABLED, "hz": PAN_HZ,
                             "backing": _PAN_REPORT["backing"],
                             "adlib": _PAN_REPORT["adlib"]}
        mode = report.get("mode")
        n = mixed.shape[1]
        want = str(loud or "MEDIUM").upper()

        # Low-mid stereo narrowing. Against two commercial references our
        # side energy was 6-8 dB high at 80-600 Hz while 0-80 Hz and
        # 1.5-4 kHz already matched. Halving the side below ~600 Hz puts the
        # kick/bass body back on centre and restores mono compatibility.
        # Skipped on master: its input is already a narrowed mix.
        if mode not in ("master", "passthrough") and mixed.shape[0] >= 2:
            _mid = (mixed[0] + mixed[1]) * 0.5
            _side = (mixed[0] - mixed[1]) * 0.5
            _hi = Pedalboard([HighpassFilter(cutoff_frequency_hz=600.0)])(
                _side[None, :], sr)[0]
            try:
                from pedalboard import LowShelfFilter as _LSF
                _mid = np.asarray(Pedalboard([_LSF(cutoff_frequency_hz=80.0, gain_db=float(cfg.get("low_mid_shelf_db", 7.0))),
                                              PeakFilter(cutoff_frequency_hz=125.0, gain_db=float(cfg.get("body_125_db", 3.0)), q=0.9)])(
                    _mid[None, :], sr)[0], dtype=np.float32)
                report["low_mid_shelf_db"] = float(cfg.get("low_mid_shelf_db", 7.0))
                report["body_125_db"] = float(cfg.get("body_125_db", 3.0))
            except Exception as _e:
                report["low_mid_mid_shelf_error"] = str(_e)[:120]
            _side = (_hi + 0.63 * (_side - _hi)).astype(np.float32)
            # 5.5-9 kHz side trim. Side energy measured ~9 dB high vs
            # Boi Chase / Omalicha / Pain (they sit -14 to -16; we were -6.0).
            # Same M/S method as the low-mid guard above, band-limited via
            # two highpasses (no LowpassFilter imported).
            try:
                # Exact FFT band trim. HP5500-HP9000 is not a flat bandpass
                # (effective gain ~0.28, and it leaked into 1.5-4 kHz), so the
                # original split could never exceed -2.9 dB. Brickwall instead.
                _SIDE_TRIM = 0.8   # 1.0 = off | 0.70 = -3.1 | 0.45 = -6.9 dB
                _n = _side.shape[-1]
                _F = np.fft.rfft(_side.astype(np.float64))
                _f = np.fft.rfftfreq(_n, 1.0 / sr)
                _m = (_f >= 5500.0) & (_f < 16000.0)
                _F[_m] *= _SIDE_TRIM
                _m2 = (_f >= 2500.0) & (_f < 5500.0)
                _F[_m2] *= 0.70
                _side = np.fft.irfft(_F, _n).astype(np.float32)
                report["top_side_trim_db"] = round(20.0 * np.log10(_SIDE_TRIM), 2)
                report["top_side_band_hz"] = [5500.0, 16000.0]
            except Exception as _e:
                report["top_side_trim_error"] = str(_e)[:120]
            mixed = np.stack([_mid + _side, _mid - _side]).astype(np.float32)
            report["low_mid_guard_hz"] = 600.0
            report["low_mid_side_trim_db"] = -4.0

        if mode != "passthrough":
            mixed = mixed * (10.0 ** ((-6.0 - peakdb(mixed)) / 20.0))
            setjob(jid, "glue bus")
            if mode in ("two_track", "master"):
                # input is already a finished mix - skip the compressor. The guard below
                # is only for an arbitrary two_track upload, not for a master.
                #
                # A "master" is our own mix fed back in and already carries the
                # 30 Hz guard from the mix pass - filtering it again costs ~0.7 dB
                # of 30-60 Hz for nothing. An arbitrary two_track upload still gets it.
                if mode != "master":
                    mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30)])(mixed, sr).astype(np.float32)
                report["glue_thr_db"] = "off (%s)" % mode
            else:
                _gr = float(cfg.get("glue_gr_db", 0.25))
                _rat = float(cfg.get("glue_ratio", 1.25))
                _over = _gr * _rat / max(0.1, _rat - 1.0)
                _thr = float(np.clip(rmsdb(mixed) - _over, -40.0, -6.0))
                mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                                    Compressor(threshold_db=_thr, ratio=_rat,
                                               attack_ms=50.0, release_ms=130.0)])(mixed, sr).astype(np.float32)
                report["glue_thr_db"] = round(_thr, 2)

        # Master target follows the beat's own loudness (audit #14):
        # forcing a finished -8.5 LUFS beat down to a fixed -14 makes the
        # mix quieter than the beat the user bought. Target = clip(beat, -11.5, -8.5)
        try:
            _beat_lufs = None
            if mode == "two_track":
                # find beat part in the arrived stems via the report keys
                _arr = report.get("arrived", {})
                _b = _arr.get("beat") or {}
                _brms = _b.get("rms_db")
                if _brms is not None:
                    # rough LUFS estimate from RMS (beat is premastered, ~3 dB RMS->LUFS offset)
                    _beat_lufs = float(_brms) - 3.0
            if _beat_lufs is not None and -16.0 < _beat_lufs < -4.0:
                tgt = float(np.clip(_beat_lufs, -11.5, -8.5))
                report["master_target_from_beat_lufs"] = round(tgt, 2)
            else:
                tgt = TARGET.get(want)
                if tgt is None:
                    tgt = float(cfg.get("target_lufs", -14.0))
        except Exception as _te:
            report["master_target_error"] = str(_te)[:120]
            tgt = TARGET.get(want)
            if tgt is None:
                tgt = float(cfg.get("target_lufs", -14.0))
        # 250-500 Hz sits forward on every render. Cut it whether
        # we're in mix mode or master mode.
        _mcs = 0.0 if mode == "master" else float(cfg.get("mid_cut_scale", 1.0))
        _mc = -2.5 * _mcs
        mixed = Pedalboard([
            PeakFilter(cutoff_frequency_hz=250.0, gain_db=_mc, q=0.9),
            PeakFilter(cutoff_frequency_hz=420.0, gain_db=-2.0 * _mcs, q=1.0),
            PeakFilter(cutoff_frequency_hz=550.0, gain_db=-1.0 * _mcs, q=1.0),
        ])(mixed, sr).astype(np.float32)
        report["mid_cut_db"] = _mc
        report["mid_cut_hz"] = 250.0
        try:
            _in_peak = peakdb(mixed)
            _in_clip = int(np.count_nonzero(np.abs(mixed) >= 0.999))
            _would_reduce = 0.0
            if _in_peak > -1.0:
                _would_reduce = -1.0 - _in_peak
            if _in_clip > 0 and _would_reduce > -0.5:
                _would_reduce = -0.5
            report["precheck_probe"] = {"peak_db_in": round(_in_peak, 2),
                                        "clipped_in": _in_clip,
                                        "would_reduce_db": round(_would_reduce, 2),
                                        "would_fire": bool(_would_reduce < -0.05)}
        except Exception as _pce:
            report["precheck_probe_error"] = str(_pce)[:120]
        if mode == "master":
            tgt = tgt + float(cfg.get("master_lift_db", 2.5))
        else:
            tgt = tgt - float(cfg.get("mix_headroom_db", 2.5))
        cur = lufs(mixed, sr)
        if cur is None:
            mixed = mixed * (10.0 ** ((tgt - rmsdb(mixed)) / 20.0))
        else:
            mixed = mixed * (10.0 ** (max(-9.0, min(9.0, tgt - cur)) / 20.0))
        # Pre-limiter soft clip: rounds peaks so limiter does less work.
        # pre-clip disabled: testing ProductionMasteringLimiter alone

        # Pre-crest guard: if input is already dense (low crest), back
        # off the loudness target so the limiter doesn't crush dynamics.
        # Can be disabled per-preset for exact LUFS targets.
        if mode == "master" and cfg.get("crest_pre_check", True):
            try:
                _crest_in = peakdb(mixed) - rmsdb(mixed)
                if _crest_in < 11.0:
                    tgt = tgt - 1.5
                    report["crest_pre_check"] = {"input_crest_db": round(_crest_in, 2), "target_reduced_db": -1.5}
                elif _crest_in < 13.0:
                    tgt = tgt - 0.5
                    report["crest_pre_check"] = {"input_crest_db": round(_crest_in, 2), "target_reduced_db": -0.5}
            except Exception as _cpe:
                report["crest_pre_check_error"] = str(_cpe)[:120]
        setjob(jid, "clip+limit")
        # ORDER MATTERS FOR DYNAMICS (chasing the FOLA reference):
        # set the gain FIRST, then clip, then limit ONCE. The old order
        # clipped, limited, then re-limited after every gain step - each
        # re-limit shaved crest (LRA 2.8 vs FOLA 4.1 at the same true peak).
        for _ in range(3):
            f = lufs(mixed, sr)
            if f is None or abs(tgt - f) < 0.15:
                break
            _step = max(-9.0, min(9.0, tgt - f))
            mixed = mixed * (10.0 ** (_step / 20.0))
        pass
        # Clipper OFF by default: shaving peaks costs kick transients and
        # adds edge. Only presets that explicitly ask for it keep it.
        _clip_on = bool(cfg.get("clip")) and mode not in ("passthrough", "master")
        _thr = 10.0 ** (-1.0 / 20.0)
        _pre = peakdb(mixed)
        _hits = int(np.count_nonzero(np.abs(mixed) > _thr))
        if _clip_on:
            mixed = auto.clip(mixed, sr)
        elif cfg.get("soft_clip") and mode not in ("passthrough", "master"):
            # Master uses knee 0.75 (threshold -2.5 dBFS): shaves transients
            # only, leaves bass fundamentals (below -2.5 dBFS) untouched.
            mixed = auto.soft_clip(mixed, sr,
                knee=float(cfg.get("master_clip_knee", 0.75)) if mode == "master" else 0.70)
            report["soft_clip"] = True
        report["clip_diag"] = {"enabled": _clip_on,
                               "pre_peak_dbfs": round(_pre, 2),
                               "post_peak_dbfs": round(peakdb(mixed), 2),
                               "samples_over_threshold": _hits}
        _dyn_pre = _dyn9010(mixed, sr)
        _lufs_before_limit = lufs(mixed, sr)
        _peak_before_limit = peakdb(mixed)
        # ---- Limiter-aware loudness targeting ----
        # The limiter's gain reduction always pulls output below target.
        # Re-limiting after gain-up just re-applies the same reduction,
        # so we do NOT iterate with the limiter in the loop. Instead:
        #   1. Dry-run the limiter to predict how much it will pull
        #   2. Raise the loudness target by that predicted cost
        #   3. Loop the pre-limiter signal to that higher target
        #   4. Apply the limiter exactly once
        _pre_limit_mix = mixed.copy()
        _test_limited, _, _ = auto.limit(_pre_limit_mix, sr, auto.CEILING_DB)
        _lufs_pre = lufs(_pre_limit_mix, sr)
        _lufs_post = lufs(_test_limited, sr)
        if _lufs_pre is not None and _lufs_post is not None:
            _gr_pred = max(0.0, _lufs_pre - _lufs_post)
        else:
            _gr_pred = 0.0
        _tgt_loop = tgt + _gr_pred * 1.56
        report["limiter_predicted_gr_db"] = round(_gr_pred, 2)
        report["loudness_target_adjusted_db"] = round(_tgt_loop, 2)
        # Loop the pre-limiter signal to the raised target
        for _ in range(4):
            f = lufs(mixed, sr)
            if f is None or abs(_tgt_loop - f) < 0.15:
                break
            _step = max(-9.0, min(9.0, _tgt_loop - f))
            mixed = mixed * (10.0 ** (_step / 20.0))
        # Apply limiter exactly once
        mixed, tp, brick = auto.limit(mixed, sr, auto.CEILING_DB)
        _fin = lufs(mixed, sr)
        _dyn_post = _dyn9010(mixed, sr)
        try:
            _gr_lufs = None if (_lufs_before_limit is None or _fin is None) else round(_lufs_before_limit - _fin, 2)
            _gr_peak = round(_peak_before_limit - peakdb(mixed), 2)
            report["limiter_probe"] = {"lufs_before": _lufs_before_limit,
                                       "lufs_after": _fin,
                                       "peak_before": round(_peak_before_limit, 2),
                                       "peak_after": round(peakdb(mixed), 2),
                                       "gr_lufs": _gr_lufs,
                                       "gr_peak": _gr_peak}
        except Exception as _le:
            report["limiter_probe_error"] = str(_le)[:120]
        report["dyn_pre_limit"] = None if _dyn_pre is None else round(_dyn_pre, 2)
        report["dyn_post_limit"] = None if _dyn_post is None else round(_dyn_post, 2)
        report["loudness_error_db"] = None if _fin is None else round(tgt - _fin, 2)
        report["true_peak_dbfs"] = round(tp, 2)
        report["limiter"] = "brickwall" if brick else "fallback"

        out = os.path.join(tmp, "mix.wav")
        save16(out, mixed, sr)
        del mixed
        gc.collect()
        rel, rel_sr = load(out)
        secs = rel.shape[1] / float(rel_sr)
        # True-peak recheck on decoded 16-bit output; if post-quantization
        # TP exceeds ceiling, attenuate and re-save before encoding.
        try:
            _tp_now = auto._true_peak_db(rel)
            if _tp_now > auto.CEILING_DB + 0.05:
                _delta = auto.CEILING_DB - _tp_now - 0.1
                rel = (rel * (10.0 ** (_delta / 20.0))).astype(np.float32)
                save16(out, rel, rel_sr)
                report["tp_recheck"] = {"measured_db": round(_tp_now, 2), "adjusted_db": round(_delta, 2)}
        except Exception as _tpe:
            report["tp_recheck_error"] = str(_tpe)[:120]
        files, enc_err = encode_all(out, tmp, secs <= 65.0)
        _stem = uuid.uuid4().hex
        urls = {}
        for _p, _ct, _ex in files:
            urls[_ex.lstrip(".")] = put(
                _p, "fx/%s-mix-%s%s" % (_stem, want.lower(), _ex), _ct)
        url = urls.get("flac") or urls.get("mp3") or ""
        got = lufs(rel, rel_sr)
        try:
            report["final_lufs"] = None if got is None else round(got, 2)
            report["final_true_peak_dbfs"] = round(auto._true_peak_db(rel), 2)
            if _qc is not None:
                report["final_qc"] = _qc.output_qc(rel, rel_sr, got, report["final_true_peak_dbfs"], auto.CEILING_DB)
        except Exception:
            pass
        report["loudness"] = want
        report["format"] = ",".join(sorted(urls.keys()))
        if enc_err:
            report["encode_error"] = enc_err
        return {"url": url, "files": urls,
                "seconds": round(rel.shape[1] / float(rel_sr), 2),
                "peak_dbfs": round(peakdb(rel), 2),
                "lufs": (None if got is None else round(got, 2)),
                "sample_rate": int(rel_sr),
                "mode": mode, "report": report, "preset": preset}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def worker(jid, stems, loud, max_sec=0, preset="neutral"):
    try:
        setjob(jid, "running")
        res = do_mix(stems, loud, jid, max_sec, preset)
        with LK:
            JOBS[jid] = {"status": "done", "url": res["url"], "result": res}
    except Exception as e:
        with LK:
            JOBS[jid] = {"status": "failed", "error": str(e)[:300]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def json_out(self, code, payload):
        b = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        jid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
        if not jid:
            return self.json_out(200, {"ok": True, "lufs": pyln is not None})
        with LK:
            j = dict(JOBS.get(jid) or {"status": "none"})
        return self.json_out(200, j)

    def do_POST(self):
        sec = os.environ.get("FX_INTERNAL_SECRET", "")
        if not sec or self.headers.get("authorization") != "Bearer " + sec:
            return self.json_out(401, {"error": "unauthorized"})
        try:
            n = int(self.headers.get("content-length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self.json_out(400, {"error": "bad json"})
        stems = data.get("stems")
        if not isinstance(stems, list) or not stems:
            return self.json_out(400, {"error": "stems[] required"})
        if len(stems) > 12:
            return self.json_out(400, {"error": "max 12 stems"})
        for s in stems:
            if not str(s.get("url") or "").startswith("https://"):
                return self.json_out(400, {"error": "each stem needs an https url"})
        jid = uuid.uuid4().hex
        with LK:
            busy = any(v.get("status") in ("queued", "running") for v in JOBS.values())
            if not busy:
                JOBS[jid] = {"status": "queued"}
        if busy:
            return self.json_out(429, {"error": "engine busy - try again in a minute"})
        t = threading.Thread(target=worker, args=(jid, stems, str(data.get("loudness") or "MEDIUM"), str(data.get("preset") or "neutral"), float(data.get("maxSeconds") or 0)))
        t.daemon = True
        t.start()
        return self.json_out(202, {"job": jid})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print("wratty-fx mixer on 0.0.0.0:%d" % port, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
