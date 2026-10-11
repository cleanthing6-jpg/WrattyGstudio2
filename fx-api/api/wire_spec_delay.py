import pathlib, sys

# ============ 1. Create delay_spec.py ============
DELAY_MODULE = '''"""Spec-compliant stereo ping-pong delay for the vocal bus.

Follows afrobeats_default_preset_v1.json -> "delay" section.

  - auto-pick note value so delay_ms lands in [250, 500]
  - stereo ping-pong, feedback 0.25 (max 0.35)
  - HPF 400 / LPF 5000 on the return
  - light tape saturation
  - stereo width 0.8
  - 0.4 Hz / 2 ms chorus modulation
  - duck 6 dB / 5 ms attack / 150 ms release, keyed from source
  - send level -18 dB
"""
import numpy as np

try:
    from pedalboard import (
        Pedalboard, HighpassFilter, LowpassFilter,
        Chorus, Distortion, Gain,
    )
except Exception:
    Pedalboard = None


PRESETS = {
    "afrobeats": dict(
        feedback=0.25, feedback_max=0.35,
        send_db=-18.0,
        hpf_hz=400.0, lpf_hz=5000.0,
        saturation_drive_db=3.0,
        width=0.80,
        modulation_rate_hz=0.40, modulation_depth_ms=2.0,
        duck_db=6.0, duck_atk_ms=5.0, duck_rel_ms=150.0,
        note_factor_pref=(0.75, 0.5, 0.25, 1.0),
    ),
    "neutral": dict(
        feedback=0.25, feedback_max=0.35,
        send_db=-20.0,
        hpf_hz=400.0, lpf_hz=5000.0,
        saturation_drive_db=0.0,
        width=0.80,
        modulation_rate_hz=0.40, modulation_depth_ms=2.0,
        duck_db=6.0, duck_atk_ms=5.0, duck_rel_ms=150.0,
        note_factor_pref=(0.75, 0.5, 0.25, 1.0),
    ),
}


def _pick_note_factor(bpm, pref):
    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        bpm = 100.0
    if not (bpm > 0) or bpm != bpm:
        bpm = 100.0
    beat_ms = 60000.0 / bpm
    for f in pref:
        d_ms = beat_ms * f
        if 250.0 <= d_ms <= 500.0:
            return float(f), float(d_ms)
    best = min(pref, key=lambda f: abs(beat_ms * f - 350.0))
    return float(best), float(beat_ms * best)


def _envelope(x, sr, atk_ms, rel_ms):
    atk = max(1, int(sr * atk_ms / 1000.0))
    rel = max(1, int(sr * rel_ms / 1000.0))
    ax = np.abs(x).astype(np.float32)
    ka = np.ones(atk, dtype=np.float32) / float(atk)
    kr = np.ones(rel, dtype=np.float32) / float(rel)
    e = np.convolve(ax, ka, mode="same")
    e = np.convolve(e, kr, mode="same")
    return e.astype(np.float32)


def render(voc, sr, bpm, preset="afrobeats"):
    if Pedalboard is None:
        return None, {"error": "pedalboard unavailable"}
    p = PRESETS.get(preset, PRESETS["neutral"])
    nf, delay_ms = _pick_note_factor(bpm, p["note_factor_pref"])
    delay_s = delay_ms / 1000.0

    a = np.asarray(voc, dtype=np.float32)
    if a.ndim == 1:
        a = np.stack([a, a])
    if a.shape[0] < 2:
        a = np.stack([a[0], a[0]])
    a = a[:2]
    n = a.shape[1]
    src = ((a[0] + a[1]) * 0.5).astype(np.float32)

    d = int(round(sr * delay_s))
    if d < 1:
        return None, {"error": "delay too short"}

    fb = min(float(p["feedback"]), float(p["feedback_max"]))
    pad = d * 12
    sp = np.zeros(n + pad, dtype=np.float32)
    sp[:n] = src
    out = np.zeros((2, n + pad), dtype=np.float32)
    g = 1.0
    side = 0
    for tap in range(1, 12):
        off = d * tap
        if off >= n + pad:
            break
        out[side, off:] += sp[:n + pad - off] * g
        side = 1 - side
        g *= fb

    out = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=float(p["hpf_hz"])),
        LowpassFilter(cutoff_frequency_hz=float(p["lpf_hz"])),
    ])(out, sr).astype(np.float32)

    try:
        depth_n = float(p["modulation_depth_ms"]) / 25.0
        out = Pedalboard([
            Chorus(rate_hz=float(p["modulation_rate_hz"]),
                   depth=depth_n, mix=0.15),
        ])(out, sr).astype(np.float32)
    except Exception:
        pass

    drive = float(p["saturation_drive_db"])
    if drive > 0.01:
        try:
            out = Pedalboard([
                Distortion(drive_db=drive),
                Gain(gain_db=-drive),
            ])(out, sr).astype(np.float32)
        except Exception:
            pass

    mid = (out[0] + out[1]) * 0.5
    sd = (out[0] - out[1]) * 0.5 * float(p["width"])
    out = np.stack([mid + sd, mid - sd]).astype(np.float32)

    try:
        env = _envelope(src, sr, p["duck_atk_ms"], p["duck_rel_ms"])
        ep = float(env.max())
        if ep > 0:
            env = env / ep
        duck_lin = 10.0 ** (-(float(p["duck_db"]) * env) / 20.0)
        out = out * duck_lin[None, :]
    except Exception:
        pass

    send_lin = 10.0 ** (float(p["send_db"]) / 20.0)
    out = (out * send_lin).astype(np.float32)
    out = out[:, :n]

    try:
        _bpm_out = round(float(bpm), 1) if (isinstance(bpm, (int, float)) and bpm == bpm and bpm > 0) else 100.0
    except Exception:
        _bpm_out = 100.0

    info = {
        "preset": str(preset),
        "note_factor": round(nf, 3),
        "delay_ms": round(delay_ms, 1),
        "bpm_used": _bpm_out,
        "feedback": round(fb, 3),
        "send_db": float(p["send_db"]),
        "hpf_hz": float(p["hpf_hz"]),
        "lpf_hz": float(p["lpf_hz"]),
        "width": float(p["width"]),
        "duck_db": float(p["duck_db"]),
        "saturation_drive_db": drive,
        "modulation_rate_hz": float(p["modulation_rate_hz"]),
        "modulation_depth_ms": float(p["modulation_depth_ms"]),
    }
    return out, info
'''

pathlib.Path("delay_spec.py").write_text(DELAY_MODULE)
print("wrote: delay_spec.py")

# ============ 2. Patch auto.py ============
auto = pathlib.Path("auto.py")
text = auto.read_text()

edits = []
edits.append((
    "delay global",
    "_REVERB_LAST = {}\n",
    "_REVERB_LAST = {}\n_DELAY_LAST = {}\n",
))
edits.append((
    "ambience signature",
    'def _ambience(voc, sr, bpm, scale=1.0, headroom=True, delay_scale=None, plate_scale=None, plate_from_delay=False, note_mult=0.75):',
    'def _ambience(voc, sr, bpm, scale=1.0, headroom=True, delay_scale=None, plate_scale=None, plate_from_delay=False, note_mult=0.75, role=None):',
))
edits.append((
    "ambience return",
    '''    wet = a * float(plate_scale)
    return (voc + wet).astype(np.float32), 0, "plate"''',
    '''    wet = a * float(plate_scale)

    # --- SPEC DELAY (afrobeats_default_preset_v1.json) ---
    dly_wet = None
    dly_info = {}
    if role in ("lead", "adlib") or role is None:
        _dspec = None
        try:
            import delay_spec as _dspec
        except Exception:
            try:
                from . import delay_spec as _dspec
            except Exception:
                _dspec = None
        if _dspec is not None:
            try:
                _dy, _dinfo = _dspec.render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))
                if _dy is not None:
                    if _dy.shape[1] < n_out:
                        _dy = np.concatenate([_dy, np.zeros((_dy.shape[0], n_out - _dy.shape[1]), np.float32)], axis=1)
                    elif _dy.shape[1] > n_out:
                        _dy = _dy[:, :n_out]
                    dly_wet = _dy
                    dly_info = _dinfo or {}
            except Exception as _de:
                dly_info = {"error": str(_de)[:200]}
    if role is not None:
        _DELAY_LAST[role] = dly_info
    base = (voc + wet) if dly_wet is None else (voc + wet + dly_wet)
    return base.astype(np.float32), 0, "plate"''',
))
edits.append((
    "role_buses call",
    '''            y, _ms, _kind = _ambience(y, sr, bpm, scale=_pl,
                                      plate_scale=_pl, delay_scale=_dl,
                                      plate_from_delay=_pfd, headroom=False,
                                      note_mult=_nt)''',
    '''            y, _ms, _kind = _ambience(y, sr, bpm, scale=_pl,
                                      plate_scale=_pl, delay_scale=_dl,
                                      plate_from_delay=_pfd, headroom=False,
                                      note_mult=_nt, role=r)''',
))
edits.append((
    "report writer A",
    '''        try:
            rep["reverb_last"] = dict(_REVERB_LAST)
        except Exception:
            rep["reverb_last"] = {}
        return _headroom(core), rep''',
    '''        try:
            rep["reverb_last"] = dict(_REVERB_LAST)
        except Exception:
            rep["reverb_last"] = {}
        try:
            rep["delay_last"] = dict(_DELAY_LAST)
        except Exception:
            rep["delay_last"] = {}
        return _headroom(core), rep''',
))
edits.append((
    "report writer B",
    '''    try:
        rep["reverb_last"] = dict(_REVERB_LAST)
    except Exception:
        rep["reverb_last"] = {}

    _DOUBLE_ON = False''',
    '''    try:
        rep["reverb_last"] = dict(_REVERB_LAST)
    except Exception:
        rep["reverb_last"] = {}
    try:
        rep["delay_last"] = dict(_DELAY_LAST)
    except Exception:
        rep["delay_last"] = {}

    _DOUBLE_ON = False''',
))

for label, OLD, NEW in edits:
    n = text.count(OLD)
    if n != 1:
        print("ABORT [%s]: anchor matched %d times (need exactly 1)" % (label, n))
        sys.exit(1)
print("all anchors verified")

bak = auto.with_suffix(".py.bak4")
bak.write_text(text)
print("backup:", bak)

for label, OLD, NEW in edits:
    text = text.replace(OLD, NEW)
    print("OK:", label)

auto.write_text(text)
print("done: auto.py patched (spec delay wired)")
