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

# ── CLIP-GAIN (before pedalboard) ──
old1 = "    out = Pedalboard(ch)(voc, sr).astype(np.float32)"
new1 = '''    # --- Clip-gain riding: level vocal before processing (+/-6 dB, 50 ms win)
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
                    _st = _i * _hop
                    _env[_i] = np.sqrt(np.mean(_mono[_st:_st+_win].astype(np.float64) ** 2) + 1e-12)
                _tgt = max(float(np.percentile(_env, 75.0)), 1e-6)
                _gdb = np.clip(20.0 * np.log10(_tgt / (_env + 1e-12)), -6.0, 6.0)
                _gdb = np.convolve(_gdb, np.ones(5, dtype=np.float64) / 5, mode="same")
                _centers = np.arange(_frames) * _hop + _win // 2
                _curve = np.interp(np.arange(_n), _centers, _gdb)
                _lin = (10.0 ** (_curve / 20.0)).astype(np.float32)
                voc = (voc * (_lin[None, :] if voc.ndim == 2 else _lin)).astype(np.float32)
                moves.append(["clip-gain", "target %.1f dBFS +/-6dB win50ms" % (20.0*np.log10(_tgt))])
        except Exception as _ce:
            moves.append(["clip-gain-error", str(_ce)[:80]])

    out = Pedalboard(ch)(voc, sr).astype(np.float32)'''
s = rep(s, old1, new1, 1, "clip-gain riding inserted")

# ── PARALLEL (after makeup, additive blend, 12:1 smash) ──
old2 = '''    _makeup_cap = 2.0 if role == "backing" else 4.0
    makeup = float(np.clip(_pre - _post, 0.0, _makeup_cap))
    if makeup > 0.05:
        out = (out * (10.0 ** (makeup / 20.0))).astype(np.float32)
    moves.append(["makeup", round(makeup, 2)])'''
new2 = '''    _makeup_cap = 2.0 if role == "backing" else 4.0
    makeup = float(np.clip(_pre - _post, 0.0, _makeup_cap))
    if makeup > 0.05:
        out = (out * (10.0 ** (makeup / 20.0))).astype(np.float32)
    moves.append(["makeup", round(makeup, 2)])

    # --- Parallel compression (New York style): dry at full power,
    #     smashed copy added under. 12:1, 0.5 ms attack, HPF 120 sidechain.
    if role in ("lead", "adlib", "backing"):
        try:
            from pedalboard import Pedalboard as _PB, Compressor as _C, Gain as _G
            _par_chain = _PB([
                HighpassFilter(cutoff_frequency_hz=120.0),
                _C(threshold_db=-32.0, ratio=12.0,
                   attack_ms=0.5, release_ms=60.0),
                _G(gain_db=14.0),
            ])
            _wet = _par_chain(out, int(sr)).astype(np.float32)
            _blend = 0.30
            out = (out + _wet * _blend).astype(np.float32)
            _pk = float(np.max(np.abs(out)))
            if _pk > 0.95:
                out = (out * (0.95 / _pk)).astype(np.float32)
            moves.append(["parallel", "30%% smash 12:1 0.5ms"])
        except Exception as _pe:
            moves.append(["parallel-error", str(_pe)[:80]])'''
s = rep(s, old2, new2, 1, "parallel compression inserted")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
