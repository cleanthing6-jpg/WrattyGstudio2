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

# ── 1. CLIP-GAIN RIDING — before the pedalboard, +/-6 dB, 50 ms window
old1 = "    out = Pedalboard(ch)(voc, sr).astype(np.float32)"
new1 = '''    # --- Clip-gain riding: level the vocal BEFORE processing (+/-6 dB, 50 ms win)
    if role in ("lead", "adlib", "backing"):
        try:
            _v = voc if voc.ndim == 2 else voc[None, :]
            _mono = np.abs(_v).max(axis=0)
            _win = max(1, int(sr * 0.050))
            _hop = max(1, int(sr * 0.010))
            _n = len(_mono)
            if _n > _win:
                _frames = max(1, (_n - _win) // _hop + 1)
                _env = np.zeros(_frames, dtype=np.float64)
                for _i in range(_frames):
                    _s = _i * _hop
                    _env[_i] = np.sqrt(np.mean(_mono[_s:_s+_win].astype(np.float64) ** 2) + 1e-12)
                _tgt = max(float(np.percentile(_env, 75.0)), 1e-6)
                _gdb = np.clip(20.0 * np.log10(_tgt / (_env + 1e-12)), -6.0, 6.0)
                _k = 5
                _gdb = np.convolve(_gdb, np.ones(_k, dtype=np.float64) / _k, mode="same")
                _centers = np.arange(_frames) * _hop + _win // 2
                _curve = np.interp(np.arange(_n), _centers, _gdb)
                _lin = (10.0 ** (_curve / 20.0)).astype(np.float32)
                voc = (voc * (_lin[None, :] if voc.ndim == 2 else _lin)).astype(np.float32)
                moves.append(["clip-gain", "target %.1f dBFS  +/-6 dB  win 50 ms" % (20.0*np.log10(_tgt))])
        except Exception as _ce:
            moves.append(["clip-gain-error", str(_ce)[:80]])

    out = Pedalboard(ch)(voc, sr).astype(np.float32)'''
s = rep(s, old1, new1, 1, "clip-gain riding inserted")

# ── 2. PARALLEL COMPRESSION — 20% blend after makeup
old2 = '''    makeup = float(np.clip(_pre - _post, 0.0, _makeup_cap))
    if makeup > 0.05:
        out = (out * (10.0 ** (makeup / 20.0))).astype(np.float32)
        moves.append(["makeup", round(makeup, 2)])'''
new2 = '''    makeup = float(np.clip(_pre - _post, 0.0, _makeup_cap))
    if makeup > 0.05:
        out = (out * (10.0 ** (makeup / 20.0))).astype(np.float32)
        moves.append(["makeup", round(makeup, 2)])

    # --- Parallel compression: 20% blend of a heavily-squashed copy
    if role in ("lead", "adlib", "backing"):
        try:
            import opto_comp
            _par_rms = _rms_db(out)
            _par_thr = float(max(-24.0, _par_rms - 8.0))
            _par, _par_info = opto_comp.opto_compress(
                out, sr,
                threshold_db=_par_thr,
                ratio=4.0,
                attack_ms=5.0,
                release_fast_ms=80.0,
                release_slow_ms=600.0,
                makeup_db=0.0,
            )
            _par_mix = 0.20
            out = (out * (1.0 - _par_mix) + _par * _par_mix).astype(np.float32)
            moves.append(["parallel", "%.0f%% squashed  gr %.2f" % (
                _par_mix * 100.0, _par_info.get("max_gr_db", 0.0))])
        except Exception as _pe:
            moves.append(["parallel-error", str(_pe)[:80]])'''
s = rep(s, old2, new2, 1, "parallel compression inserted")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
