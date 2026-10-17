from pathlib import Path
import ast, sys
P = Path("dsp_pro.py")
s = P.read_text(encoding="utf-8")

# ── Replace _load_ir with sample-rate-aware version
old_ir = '''def _load_ir(path, max_len=6*48000):
    if path in _IR_CACHE:
        return _IR_CACHE[path]
    if _sf is None:
        return None
    ir, sr_ir = _sf.read(path)
    if ir.ndim > 1:
        ir = np.mean(ir, axis=1)
    ir = ir[:max_len].astype(np.float32)
    fade = int(0.05 * sr_ir)
    if len(ir) > fade:
        w = np.ones(len(ir), dtype=np.float32)
        w[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        ir *= w
    _IR_CACHE[path] = ir
    return ir'''

new_ir = '''def _load_ir(path, sr_target=44100, max_len=6*48000):
    """Load + resample IR to engine sr + fade tail. Cached."""
    key = (path, sr_target)
    if key in _IR_CACHE:
        return _IR_CACHE[key]
    if _sf is None:
        return None
    ir, sr_ir = _sf.read(path)
    if ir.ndim > 1:
        ir = np.mean(ir, axis=1)
    ir = ir.astype(np.float32)
    # Resample if IR sr != engine sr (linear interp — good enough for IRs)
    if abs(sr_ir - sr_target) > 1:
        new_len = int(round(len(ir) * sr_target / sr_ir))
        ir = np.interp(
            np.linspace(0.0, len(ir) - 1, new_len),
            np.arange(len(ir), dtype=np.float64),
            ir,
        ).astype(np.float32)
    ir = ir[:max_len]
    fade = int(0.05 * sr_target)
    if len(ir) > fade:
        w = np.ones(len(ir), dtype=np.float32)
        w[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)
        ir *= w
    _IR_CACHE[key] = ir
    return ir'''

n = s.count(old_ir)
if n != 1:
    sys.exit("ABORT: _load_ir matched %d (need 1)" % n)
s = s.replace(old_ir, new_ir, 1)
print("  ok  _load_ir: sample-rate-aware resample + cache key by sr")

# ── Replace the _reverb_duck_filter core with two-stage (program-dep) release
old_duck = '''@njit(cache=True)
def _reverb_duck_filter(wet_l, wet_r, dry_mono, a_hp, a_lp, a_atk, a_rel, duck):
    n = len(wet_l)
    ol = np.zeros(n, dtype=np.float32)
    orr = np.zeros(n, dtype=np.float32)
    h_in_l = 0.0; h_out_l = 0.0; l_out_l = 0.0
    h_in_r = 0.0; h_out_r = 0.0; l_out_r = 0.0
    env = 0.0
    for s in range(n):
        r = abs(dry_mono[s])
        if r > env: env += a_atk * (r - env)
        else:       env += a_rel * (r - env)
        att = 1.0 / (1.0 + env * duck)
        wl = wet_l[s] * att
        wr = wet_r[s] * att
        chl = a_hp * (h_out_l + wl - h_in_l); h_in_l = wl; h_out_l = chl
        cll = l_out_l + a_lp * (chl - l_out_l); l_out_l = cll; ol[s] = cll
        chr_ = a_hp * (h_out_r + wr - h_in_r); h_in_r = wr; h_out_r = chr_
        clr = l_out_r + a_lp * (chr_ - l_out_r); l_out_r = clr; orr[s] = clr
    return ol, orr'''

new_duck = '''@njit(cache=True)
def _reverb_duck_filter(wet_l, wet_r, dry_mono, a_hp, a_lp,
                        a_atk, a_rel_fast, a_rel_slow, duck, prog_mix):
    """Two-stage program-dependent duck release (fast + slow blended)."""
    n = len(wet_l)
    ol = np.zeros(n, dtype=np.float32)
    orr = np.zeros(n, dtype=np.float32)
    h_in_l = 0.0; h_out_l = 0.0; l_out_l = 0.0
    h_in_r = 0.0; h_out_r = 0.0; l_out_r = 0.0
    env_f = 0.0
    env_s = 0.0
    for s in range(n):
        r = abs(dry_mono[s])
        # Fast envelope (short-term)
        if r > env_f: env_f += a_atk * (r - env_f)
        else:         env_f += a_rel_fast * (r - env_f)
        # Slow envelope (memory)
        if r > env_s: env_s += a_atk * (r - env_s)
        else:         env_s += a_rel_slow * (r - env_s)
        # Blend — more slow under sustained, more fast on transients
        env = env_f * (1.0 - prog_mix) + env_s * prog_mix
        att = 1.0 / (1.0 + env * duck)
        wl = wet_l[s] * att
        wr = wet_r[s] * att
        chl = a_hp * (h_out_l + wl - h_in_l); h_in_l = wl; h_out_l = chl
        cll = l_out_l + a_lp * (chl - l_out_l); l_out_l = cll; ol[s] = cll
        chr_ = a_hp * (h_out_r + wr - h_in_r); h_in_r = wr; h_out_r = chr_
        clr = l_out_r + a_lp * (chr_ - l_out_r); l_out_r = clr; orr[s] = clr
    return ol, orr'''

n = s.count(old_duck)
if n != 1:
    sys.exit("ABORT: _reverb_duck_filter matched %d (need 1)" % n)
s = s.replace(old_duck, new_duck, 1)
print("  ok  duck: two-stage program-dependent release")

# ── Replace plate_wet with tier-1 (predelay + modulation + two-stage duck)
old_pw = '''def plate_wet(voc, sr, mix=0.089, duck_depth=0.5):
    """Returns WET stereo tail only (matches old _plate return)."""
    a = np.asarray(voc, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    x_mono = a.mean(axis=0).astype(np.float32)
    n = len(x_mono)

    ir_l = _load_ir(_os.path.join(_IR_DIR, "plate_L.wav"))
    ir_r = _load_ir(_os.path.join(_IR_DIR, "plate_R.wav"))
    if ir_l is None or ir_r is None:
        return None

    N = n + len(ir_l) - 1
    X = _rfft(x_mono, n=N)
    rev_l = _irfft(X * _rfft(ir_l, n=N), n=N)[:n].astype(np.float32)
    rev_r = _irfft(X * _rfft(ir_r, n=N), n=N)[:n].astype(np.float32)

    a_hp  = np.float32(_coeff_tau(1.0/(2*np.pi*250.0), sr))
    a_lp  = np.float32(_coeff_tau(1.0/(2*np.pi*9000.0), sr))
    a_atk = np.float32(_coeff_tau(0.005, sr))
    a_rel = np.float32(_coeff_tau(0.100, sr))

    wl, wr = _reverb_duck_filter(rev_l, rev_r, x_mono,
                                 a_hp, a_lp, a_atk, a_rel, np.float32(duck_depth))
    wet = np.stack([wl, wr]).astype(np.float32) * np.float32(mix)
    return wet'''

new_pw = '''def plate_wet(voc, sr, mix=0.089, duck_depth=0.5,
              predelay_ms=30.0, mod_rate_hz=0.2, mod_depth_ms=0.5):
    """Tier-1 plate: real IR + resample + predelay + mod + two-stage duck."""
    a = np.asarray(voc, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    x_mono = a.mean(axis=0).astype(np.float32)
    n = len(x_mono)

    ir_l = _load_ir(_os.path.join(_IR_DIR, "plate_L.wav"), sr_target=int(sr))
    ir_r = _load_ir(_os.path.join(_IR_DIR, "plate_R.wav"), sr_target=int(sr))
    if ir_l is None or ir_r is None:
        return None

    # 1. Linear convolution at full length
    N = n + len(ir_l) - 1
    X = _rfft(x_mono, n=N)
    rev_l = _irfft(X * _rfft(ir_l, n=N), n=N)[:n].astype(np.float32)
    rev_r = _irfft(X * _rfft(ir_r, n=N), n=N)[:n].astype(np.float32)

    # 2. Predelay — pad front with silence, drop tail
    pre = int(predelay_ms / 1000.0 * sr)
    if pre > 0:
        rev_l = np.concatenate([np.zeros(pre, np.float32), rev_l[:-pre]]) if pre < len(rev_l) else np.zeros(n, np.float32)
        rev_r = np.concatenate([np.zeros(pre, np.float32), rev_r[:-pre]]) if pre < len(rev_r) else np.zeros(n, np.float32)

    # 3. Modulation — small LFO wobble on read position (plate shimmer)
    if mod_depth_ms > 0.0 and mod_rate_hz > 0.0:
        t = np.arange(n, dtype=np.float32) / float(sr)
        lfo = (mod_depth_ms / 1000.0 * sr) * np.sin(2.0 * np.pi * mod_rate_hz * t).astype(np.float32)
        idx = np.arange(n, dtype=np.float32)
        il = np.clip(idx + lfo, 0.0, float(n - 1))
        ir_ = np.clip(idx - lfo, 0.0, float(n - 1))
        rev_l = np.interp(il, idx, rev_l).astype(np.float32)
        rev_r = np.interp(ir_, idx, rev_r).astype(np.float32)

    # 4. Duck coefficients (program-dependent: 5 ms attack, fast 80 ms + slow 400 ms)
    a_hp       = np.float32(_coeff_tau(1.0/(2*np.pi*250.0), sr))
    a_lp       = np.float32(_coeff_tau(1.0/(2*np.pi*9000.0), sr))
    a_atk      = np.float32(_coeff_tau(0.005, sr))
    a_rel_fast = np.float32(_coeff_tau(0.080, sr))
    a_rel_slow = np.float32(_coeff_tau(0.400, sr))
    prog_mix   = np.float32(0.55)

    wl, wr = _reverb_duck_filter(rev_l, rev_r, x_mono,
                                 a_hp, a_lp, a_atk,
                                 a_rel_fast, a_rel_slow,
                                 np.float32(duck_depth), prog_mix)
    wet = np.stack([wl, wr]).astype(np.float32) * np.float32(mix)
    return wet'''

n = s.count(old_pw)
if n != 1:
    sys.exit("ABORT: plate_wet matched %d (need 1)" % n)
s = s.replace(old_pw, new_pw, 1)
print("  ok  plate_wet: predelay + modulation + two-stage duck")

P.write_text(s, encoding="utf-8"); ast.parse(s)
print("SYNTAX OK")
