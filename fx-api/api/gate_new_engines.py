from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want:
        sys.exit("ABORT: '%s' matched %d (need %d) - NOTHING written" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

# ── 1. Insert _NEW dict right after "import pedalboard"
old_imp = "import pedalboard\n"
new_imp = '''import pedalboard

# ── Feature gates for engines added 2026-10-14. Flip one at a time to
#    isolate regressions. All False = chain runs pre-upgrade code.
_NEW = {
    "clip_gain":     False,
    "fet":           False,
    "la2a_pro":      False,
    "saturator_pro": False,
    "deess_pro":     False,
    "exciter_t1":    False,
    "adt_t1":        False,
    "delay_t1":      False,
    "plate_t1":      False,
    "parallel_ny":   False,
}
'''
s = rep(s, old_imp, new_imp, 1, "_NEW dict inserted")

# ── 2. _saturate: gate pro_saturator, restore old formula on False
old_sat = '''def _saturate(x, sr, drive_db):
    """Tier-1 C2-continuous saturator, 4x polyphase OS, Numba'd."""
    if drive_db is None or drive_db <= 0.001:
        return x
    try:
        import dsp_pro
        return dsp_pro.pro_saturator(x, sr, drive_db=float(drive_db))
    except Exception:
        return x'''
new_sat = '''def _saturate(x, sr, drive_db):
    if drive_db is None or drive_db <= 0.001:
        return x
    if _NEW["saturator_pro"]:
        try:
            import dsp_pro
            return dsp_pro.pro_saturator(x, sr, drive_db=float(drive_db))
        except Exception:
            return x
    try:
        import numpy as _np
        a = _np.asarray(x, dtype=_np.float32)
        d = 1.0 + float(drive_db) * 2.0
        b = 0.15 * float(drive_db)
        y = _np.tanh(a * d + b) - _np.tanh(b)
        y = y + 0.15 * float(drive_db) * (y ** 2) * _np.sign(y)
        ri = _np.sqrt(_np.mean(a ** 2)) + 1e-9
        ro = _np.sqrt(_np.mean(y ** 2)) + 1e-9
        return (y * (ri / ro)).astype(_np.float32)
    except Exception:
        return x'''
s = rep(s, old_sat, new_sat, 1, "_saturate gated")

# ── 3. _deess: gate pro_deesser, restore old STFT body on False
old_de = '''def _deess(voc, sr, st):
    """Tier-1 split-band lookahead de-esser (5.5kHz crossover, 5ms lookahead)."""
    try:
        import dsp_pro
        return dsp_pro.deess_drop_in(voc, sr, st, ratio=4.0)
    except Exception as _de:
        return voc, 0.0'''
new_de = '''def _deess(voc, sr, st):
    if _NEW["deess_pro"]:
        try:
            import dsp_pro
            return dsp_pro.deess_drop_in(voc, sr, st, ratio=4.0)
        except Exception:
            return voc, 0.0
    try:
        freq = np.fft.rfftfreq(N, 1.0 / sr)
        k = (freq >= 5500) & (freq < 9000)
        if not np.any(k):
            return voc, 0.0
        out = np.empty_like(voc)
        mx = 0.0
        for c in range(voc.shape[0]):
            S = _stft(voc[c])
            lev = _level_db(S, k)
            thr = float(np.median(lev)) + DEESS_OFFSET_DB
            red = _smooth(np.clip(lev - thr, 0.0, MAX_DEESS), atk=DEESS_ATK, rel=DEESS_REL)
            mx = max(mx, float(np.max(red)))
            S[:, k] *= (10.0 ** (-red / 20.0))[:, None]
            out[c] = _istft(S, voc.shape[1])
            del S
        return out, round(mx, 2)
    except Exception:
        return voc, 0.0'''
s = rep(s, old_de, new_de, 1, "_deess gated")

# ── 4. _double: gate adt_t1, restore old pedalboard pitch-shift body on False
old_dbl = '''def _double(voc, sr):
    """Tier-1 LFO ADT doubler (cubic Hermite, polyphase, live taps 14/22 ms)."""
    try:
        import dsp_tier1
        blend = 10.0 ** (DOUBLE_DB / 20.0)
        out = dsp_tier1.adt_double(
            voc, sr,
            depth_ms=14.0,
            rate_hz=0.5,
            right_offset_ms=8.0,
            pan=0.30,
            blend=blend,
        )
        _DBL["kind"] = "adt (LFO+cubic, 14/22ms, +/-0.30pan)"
        return out
    except Exception as _e:
        _DBL["error"] = repr(_e)
        return None'''
new_dbl = '''def _double(voc, sr):
    if _NEW["adt_t1"]:
        try:
            import dsp_tier1
            blend = 10.0 ** (DOUBLE_DB / 20.0)
            out = dsp_tier1.adt_double(voc, sr, depth_ms=14.0, rate_hz=0.5,
                                       right_offset_ms=8.0, pan=0.30, blend=blend)
            _DBL["kind"] = "adt (LFO+cubic, 14/22ms, +/-0.30pan)"
            return out
        except Exception as _e:
            _DBL["error"] = repr(_e)
            return None
    try:
        out = np.zeros_like(voc)
        for cents, ms, pan in ((7.0, 14.0, 0.30), (-6.0, 22.0, -0.30)):
            ch = ([] if PitchShift is None else [PitchShift(semitones=cents / 100.0)]) + [
                  HighpassFilter(cutoff_frequency_hz=150.0),
                  LowpassFilter(cutoff_frequency_hz=10000.0)]
            _opt(ch, Chorus, rate_hz=0.4, depth=0.06, mix=0.25)
            ch.append(Delay(delay_seconds=ms / 1000.0, feedback=0.0, mix=1.0))
            y = Pedalboard(ch)(voc, sr).astype(np.float32)
            y[0] *= float(np.sqrt(max(0.0, (1.0 - pan) * 0.5)) * 1.414)
            y[1] *= float(np.sqrt(max(0.0, (1.0 + pan) * 0.5)) * 1.414)
            out += y
        out *= 10.0 ** (DOUBLE_DB / 20.0)
        _DBL["kind"] = "adt (detune+delay+pan)" if PitchShift is not None else "delays+pan only (no PitchShift)"
        return out
    except Exception as _e:
        _DBL["error"] = repr(_e)
        return None'''
s = rep(s, old_dbl, new_dbl, 1, "_double gated")

# ── 5. _ambience plate call — gate plate_t1
old_pl = '''    plate = None
    try:
        import dsp_pro
        plate = dsp_pro.plate_wet(voc, sr, mix=0.089, duck_depth=0.5)
    except Exception as _pr:
        _REVERB_LAST["error"] = str(_pr)[:200]
        plate = None
    if plate is None:
        plate = _plate(voc, sr)'''
new_pl = '''    plate = None
    if _NEW["plate_t1"]:
        try:
            import dsp_pro
            plate = dsp_pro.plate_wet(voc, sr, mix=0.089, duck_depth=0.5)
        except Exception as _pr:
            _REVERB_LAST["error"] = str(_pr)[:200]
            plate = None
    if plate is None:
        plate = _plate(voc, sr)'''
s = rep(s, old_pl, new_pl, 1, "_ambience plate gated")

# ── 6. _ambience delay call — gate delay_t1
old_dl = '''        _dspec = None
        try:
            import dsp_delay as _dspec
            _spec_render = _dspec.delay_render
        except Exception:
            _spec_render = None
        if _spec_render is None:
            try:
                import delay_spec as _dspec2
                _spec_render = _dspec2.render
            except Exception:
                _spec_render = None
        if _spec_render is not None:'''
new_dl = '''        _spec_render = None
        if _NEW["delay_t1"]:
            try:
                import dsp_delay as _dspec
                _spec_render = _dspec.delay_render
            except Exception:
                _spec_render = None
        if _spec_render is None:
            try:
                import delay_spec as _dspec2
                _spec_render = _dspec2.render
            except Exception:
                _spec_render = None
        if _spec_render is not None:'''
s = rep(s, old_dl, new_dl, 1, "_ambience delay gated")

# ── 7. clip-gain block — wrap in flag
old_cg = '''    # --- Clip-gain ride: level-neutral pre-stage (relative to own average).
    if role in ("lead", "adlib", "backing"):
        try:
            import clip_gain
            _cg_in = _rms_db(voc)
            voc = clip_gain.clip_gain_ride(voc, sr, window_ms=100.0,
                                           max_gain_db=0.0,
                                           silence_threshold_db=-42.0)
            _cg_out = _rms_db(voc)
            moves.append(["clip-gain", "linked +/-3dB  100ms  mean shift %.2f dB" % (_cg_out - _cg_in)])
        except Exception as _cge:
            moves.append(["clip-gain-error", str(_cge)[:80]])
'''
new_cg = '''    # --- Clip-gain ride (gated)
    if _NEW["clip_gain"] and role in ("lead", "adlib", "backing"):
        try:
            import clip_gain
            _cg_in = _rms_db(voc)
            voc = clip_gain.clip_gain_ride(voc, sr, window_ms=100.0,
                                           max_gain_db=1.5,
                                           silence_threshold_db=-32.0)
            _cg_out = _rms_db(voc)
            moves.append(["clip-gain", "linked +/-1.5dB  100ms  mean shift %.2f dB" % (_cg_out - _cg_in)])
        except Exception as _cge:
            moves.append(["clip-gain-error", str(_cge)[:80]])
'''
s = rep(s, old_cg, new_cg, 1, "clip-gain gated")

# ── 8. FET block — wrap in flag
old_fet = '''    if role in ("lead", "adlib", "backing"):
        try:
            import fet_comp
            _fet_rms = _rms_db(out)'''
new_fet = '''    if _NEW["fet"] and role in ("lead", "adlib", "backing"):
        try:
            import fet_comp
            _fet_rms = _rms_db(out)'''
s = rep(s, old_fet, new_fet, 1, "FET gated")

# ── 9. LA-2A: dsp_pro vs opto_comp under flag
old_la = '''        out, _opto_info = dsp_pro.la2a_compress(
            out, sr,'''
new_la = '''        _la2a_fn = dsp_pro.la2a_compress if _NEW["la2a_pro"] else opto_comp.opto_compress
        out, _opto_info = _la2a_fn(
            out, sr,'''
s = rep(s, old_la, new_la, 1, "LA-2A gated")

# ── 10. _parallel — gate parallel_ny, restore old body
old_par = '''def _parallel(x, sr):
    """NY parallel — 12:1 smash, HPF 120 sidechain, additive blend."""
    try:
        import parallel_comp
        out = parallel_comp.industry_parallel_compressor(x, sr, blend_amount=0.30)
        _PAR_LAST["ran"] = True
        _PAR_LAST["mode"] = "ny 6:1 8ms hpf120 sub30"
        return out
    except Exception as _e:
        _PAR_LAST["error"] = str(_e)[:200]
        return x'''
new_par = '''def _parallel(x, sr):
    if _NEW["parallel_ny"]:
        try:
            import parallel_comp
            out = parallel_comp.industry_parallel_compressor(x, sr, blend_amount=0.30)
            _PAR_LAST["ran"] = True
            _PAR_LAST["mode"] = "ny 6:1 8ms hpf120 sub30"
            return out
        except Exception as _e:
            _PAR_LAST["error"] = str(_e)[:200]
            return x
    try:
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        crushed = Pedalboard([
            Compressor(threshold_db=-24.0, ratio=6.0, attack_ms=8.0, release_ms=90.0),
            Gain(gain_db=3.0),
        ])(a, int(sr)).astype(np.float32)
        y = (a * 0.70 + crushed * 0.30).astype(np.float32)
        _PAR_LAST["ran"] = True
        return _headroom(y, -1.0).astype(np.float32)
    except Exception as _e:
        _PAR_LAST["error"] = str(_e)[:200]
        return x'''
s = rep(s, old_par, new_par, 1, "_parallel gated")

# ── 11. _exciter — gate exciter_t1, restore old pedalboard body
old_exc = '''def _exciter(x, sr):
    """Tier-1 asymmetric 5-10k exciter (Numba + polyphase 2x)."""
    try:
        import dsp_tier1
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[1] == 0:
            return x
        y = dsp_tier1.exciter(a, int(sr), drive_db=8.0, blend=0.08)
        _EXC_LAST["ran"] = True
        return _headroom(y, -1.0).astype(np.float32)
    except Exception as _e:
        try:
            _EXC_LAST["error"] = str(_e)[:200]
        except Exception:
            pass
        return x'''
new_exc = '''def _exciter(x, sr):
    if _NEW["exciter_t1"]:
        try:
            import dsp_tier1
            a = np.asarray(x, dtype=np.float32)
            if a.ndim != 2 or a.shape[1] == 0:
                return x
            y = dsp_tier1.exciter(a, int(sr), drive_db=8.0, blend=0.08)
            _EXC_LAST["ran"] = True
            return _headroom(y, -1.0).astype(np.float32)
        except Exception as _e:
            _EXC_LAST["error"] = str(_e)[:200]
            return x
    try:
        from pedalboard import Pedalboard as _PB, HighpassFilter as _HP, LowpassFilter as _LP, Distortion as _D, Gain as _G
        a = np.asarray(x, dtype=np.float32)
        if a.ndim != 2 or a.shape[0] not in (1, 2) or a.shape[1] == 0:
            return x
        air = _PB([_HP(cutoff_frequency_hz=5000.0),
                   _D(drive_db=0.8),
                   _LP(cutoff_frequency_hz=10000.0),
                   _G(gain_db=-9.0)])(a, int(sr)).astype(np.float32)
        y = (a + air * 0.08).astype(np.float32)
        _EXC_LAST["ran"] = True
        return _headroom(y, -1.0).astype(np.float32)
    except Exception as _e:
        _EXC_LAST["error"] = str(_e)[:200]
        return x'''
s = rep(s, old_exc, new_exc, 1, "_exciter gated")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print()
print("SYNTAX OK — all 9 new engines gated, default OFF")
print("REVERT: git checkout -- fx-api/api/auto.py")
