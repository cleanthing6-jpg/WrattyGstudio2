"""pro_space.py -- complete adaptive "close + floating + clean" vocal space system.

Needs pro_touch.py next to it (numpy/scipy only). Works per song, per user: everything is derived from
the vocal, the beat and the BPM. Nothing is applied to the beat except an optional, capped, band-limited
"pocket" duck; every added return is high-passed so the beat's low end and power are untouched, and a
guard measures the beat before/after and backs things off if it moves.
"""
import numpy as np
import scipy.signal as sg
import pro_touch as pt


def _sos(kind, f, sr, order=2):
    return sg.butter(order, f, kind, fs=sr, output="sos")


def _band(x, sr, lo, hi):
    return sg.sosfilt(_sos("bandpass", [lo, hi], sr), x, axis=-1).astype(np.float32)


def _rms_db(x):
    return float(10 * np.log10((np.asarray(x, np.float64) ** 2).mean() + 1e-20))


def _scale_to(wet, v, sr, rel_db):
    dry_db, act = pt._active_rms_db(v, sr)
    wet_db, _ = pt._active_rms_db(wet, sr, act)
    return (wet * np.float32(10 ** ((dry_db + rel_db - wet_db) / 20))).astype(np.float32)


def _modulate(w, sr, rate=0.4, depth_ms=0.35):
    n = w.shape[-1]
    idx = np.arange(n, dtype=np.float64)
    out = np.empty_like(w)
    for c in range(w.shape[0]):
        ph = 0.0 if c == 0 else 2.1
        j = idx + depth_ms * sr / 1000.0 * np.sin(2 * np.pi * rate * idx / sr + ph)
        out[c] = np.interp(j, idx, w[c]).astype(np.float32)
    return out


def clean_send(v, sr, hpf=500.0, lpf=5500.0):
    v = np.asarray(v, np.float32)
    sib = _band(v, sr, 5000.0, 9000.0)
    env = pt._smooth(np.abs(sib), sr, 0.003)
    thr = np.percentile(env[env > 1e-6], 85) if (env > 1e-6).any() else 1.0
    g = np.minimum(1.0, (thr / (env + 1e-9)) ** 0.8)
    g = pt._smooth(g, sr, 0.002)
    v = v - sib * (1.0 - g)
    return sg.sosfilt(np.vstack([_sos("highpass", hpf, sr), _sos("lowpass", lpf, sr)]), v).astype(np.float32)


def early_reflections(send, sr, rel_db=-26.0, v=None):
    n = len(send)
    tl = [11, 17, 23, 31, 38]; tr = [13, 19, 27, 34, 42]; gn = [1.0, 0.8, 0.65, 0.5, 0.4]
    out = np.zeros((2, n), np.float32)
    for c, taps in enumerate((tl, tr)):
        for ms, g in zip(taps, gn):
            d = int(sr * ms / 1000.0)
            out[c, d:] += g * send[:n - d]
    return _scale_to(out, v if v is not None else send, sr, rel_db)


def tiny_room(send, sr, v, ir_s, pre_ms, hpf, lpf, rel_db):
    w = pt._tail(send, sr, ir_s, pre_ms, hpf, lpf, 11)
    return _scale_to(w, v, sr, rel_db)


def parallel_sat(v, sr, rel_db=-16.0, drive=3.0, hpf=250.0):
    x = sg.sosfilt(_sos("highpass", hpf, sr), v).astype(np.float32)
    y = np.tanh(drive * x) / drive
    y = sg.sosfilt(_sos("highpass", hpf, sr), y).astype(np.float32)
    dry_db, act = pt._active_rms_db(v, sr)
    y_db, _ = pt._active_rms_db(y, sr, act)
    return (y * np.float32(10 ** ((dry_db + rel_db - y_db) / 20))).astype(np.float32)


def shared_room(beat, send, v, sr, ir_s=0.45, rel_db=-27.0):
    bm = beat.mean(axis=0) if beat.ndim == 2 else beat
    bh = sg.sosfilt(_sos("highpass", 450.0, sr), bm).astype(np.float32)
    feed = send + 0.5 * bh
    w = pt._tail(feed, sr, ir_s, 20.0, 450.0, 5000.0, 23)
    w *= pt._fast_duck(v, sr, 4.0, 0.1)[None, :]
    cur = _rms_db(w); ref = _rms_db(bh)
    return (w * np.float32(10 ** ((ref + rel_db - cur) / 20))).astype(np.float32)


def beat_pocket(beat, v, sr, max_db=1.5, band=(1800.0, 4500.0)):
    vb = _band(v, sr, *band); bm = beat.mean(axis=0) if beat.ndim == 2 else beat
    bb = _band(bm, sr, *band)
    db, hs = pt._env10(v, sr); act, _ = pt._phrases(db, hs)
    hop = int(sr * 0.01); k = min(len(act), len(vb) // hop, len(bb) // hop)
    a = act[:k]
    if a.sum() < 10:
        return beat, {"pocket_db": 0.0, "vocal_minus_beat_2_4k_db": None}
    pv = (vb[:k * hop].reshape(k, hop) ** 2).mean(1)[a].mean(); pb = (bb[:k * hop].reshape(k, hop) ** 2).mean(1)[a].mean()
    gap = float(10 * np.log10(pv / (pb + 1e-20) + 1e-20))
    depth = float(np.clip(0.5 * (-2.0 - gap), 0.0, max_db))
    if depth < 0.2:
        return beat, {"pocket_db": 0.0, "vocal_minus_beat_2_4k_db": round(gap, 1)}
    g = pt._fast_duck(v, sr, depth, 0.12)
    bandb = _band(beat, sr, *band)
    out = (beat - bandb * (1.0 - g)[None, :]).astype(np.float32)
    return out, {"pocket_db": round(depth, 2), "vocal_minus_beat_2_4k_db": round(gap, 1)}


def beat_power(beat, sr):
    bm = beat.mean(axis=0) if beat.ndim == 2 else beat
    low = sg.sosfilt(_sos("lowpass", 150.0, sr, 4), bm)
    return {"rms_db": round(_rms_db(beat) , 2), "low_rms_db": round(_rms_db(low), 2),
            "peak_db": round(float(20 * np.log10(np.abs(beat).max() + 1e-12)), 2)}


def role_rules(role):
    r = {
        "lead":    {"gain_db": 0.0,  "hpf": 95.0,  "cut_2_4k_db": 0.0, "sat": 0.15, "delay_send": "render()", "room_db": None, "pan": 0.0},
        "double":  {"gain_db": -9.0, "hpf": 200.0, "cut_2_4k_db": 1.5, "sat": 0.15, "delay_send": None, "room_db": None, "pan": "+/-0.3 to 0.55 (L/R pair)"},
        "backing": {"gain_db": -5.0, "hpf": 220.0, "cut_2_4k_db": 2.5, "sat": 0.2,  "delay_send": None, "room_db": -30.0, "pan": "separate takes +/-0.35 to 0.55"},
        "adlib":   {"gain_db": -7.0, "hpf": 200.0, "cut_2_4k_db": 2.0, "sat": 0.2,  "delay_send": None, "room_db": -28.0, "pan": "+/-0.5 to 0.7, opposite to a backing"},
    }
    return r.get(role, r["backing"])


def build(lead, beat, sr, bpm, pocket=False, existing_carve_db=0.0):
    lead = np.asarray(lead, np.float32); beat = np.asarray(beat, np.float32)
    n = lead.shape[-1]
    if beat.shape[-1] < n:
        beat = np.pad(beat, ((0, 0), (0, n - beat.shape[-1])))
    beat = beat[:, :n]
    v = pt._mono(lead)
    send = clean_send(v, sr)
    prof = pt.analyze(lead, sr)
    f0 = prof.get("f0") or 200.0
    dens = prof["active_ratio"]
    hp = float(np.clip(2.5 * f0, 450.0, 800.0))
    lp = pt._interp(prof["bright_db"], [-24, -10], [5800.0, 4800.0])

    plate, dly, P = pt.render(lead, sr, bpm, send=send)
    early = early_reflections(send, sr, -26.0, v)
    room = tiny_room(send, sr, v, 0.25, 25.0, max(hp * 0.7, 350.0), lp, pt._interp(dens, [0.35, 0.75], [-23.0, -27.0]))
    psat = parallel_sat(v, sr, pt._interp(dens, [0.35, 0.75], [-15.0, -18.0]))
    shared = shared_room(beat, send, v, sr)

    plate = _modulate(plate, sr, 0.4, 0.35)
    room = _modulate(room, sr, 0.3, 0.25)
    shared = _modulate(shared, sr, 0.35, 0.3)
    dly = _modulate(dly, sr, 0.25, 0.15)

    before = beat_power(beat, sr)
    pk = {"pocket_db": 0.0}
    beat_out = beat
    if pocket:
        beat_out, pk = beat_pocket(beat, v, sr, max_db=max(0.0, 1.5 - float(existing_carve_db)))
    after = beat_power(beat_out, sr)
    sh_scale = 1.0
    for _ in range(6):
        added = beat_out + shared * sh_scale
        rise = _rms_db(added) - _rms_db(beat)
        if rise <= 0.3:
            break
        sh_scale *= 0.7
    shared = (shared * sh_scale).astype(np.float32)
    final = beat_power(beat_out + shared, sr)
    guard = {"beat_before": before, "beat_after_pocket": after, "beat_after_pocket_and_room": final,
             "rms_change_db": round(final["rms_db"] - before["rms_db"], 2),
             "low_end_change_db": round(final["low_rms_db"] - before["low_rms_db"], 2),
             "shared_room_scale": round(sh_scale, 2)}
    params = dict(P); params.update(pk)
    params.update({"early_db": -26.0, "room_ir_s": 0.25, "parallel_sat_db": round(pt._interp(dens, [0.35, 0.75], [-15, -18]), 1),
                   "send_hpf": 500, "send_lpf": round(lp), "mod_hz": "0.25-0.4", "f0": round(f0)})
    return {"beat_out": beat_out, "parallel": psat,
            "returns": {"early": early, "room": room, "plate": plate, "delay": dly, "shared": shared},
            "params": params, "guard": guard}


def mix_down(lead, beat, sr, bpm):
    r = build(lead, beat, sr, bpm)
    L = np.asarray(lead, np.float32)
    L = np.stack([L, L]) if L.ndim == 1 else L
    out = r["beat_out"] + L + r["parallel"][None, :]
    for w in r["returns"].values():
        out = out + w
    return out.astype(np.float32), r
