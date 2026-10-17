import sys, ast
def sub(src, old, new, label):
    if src.count(old) != 1:
        sys.exit("ABORT (%s): expected 1, found %d. Nothing changed." % (label, src.count(old)))
    return src.replace(old, new)

# ── dsp_pro.py ──
p = open("dsp_pro.py").read()
p = sub(p, "predelay_ms=50.0, mod_rate_hz=0.2, mod_depth_ms=0.5):",
        "predelay_ms=50.0, mod_rate_hz=0.2, mod_depth_ms=0.5,\n              hp_hz=350.0, lp_hz=7500.0, ir_len_s=None):", "signature")
p = sub(p, '    ir_l = _load_ir(_os.path.join(_IR_DIR, "plate_L.wav"), sr_target=int(sr))\n',
        '    _irk = {} if ir_len_s is None else {"max_len": int(ir_len_s * 48000)}\n'
        '    ir_l = _load_ir(_os.path.join(_IR_DIR, "plate_L.wav"), sr_target=int(sr), **_irk)\n', "ir_l")
p = sub(p, '    ir_r = _load_ir(_os.path.join(_IR_DIR, "plate_R.wav"), sr_target=int(sr))\n',
        '    ir_r = _load_ir(_os.path.join(_IR_DIR, "plate_R.wav"), sr_target=int(sr), **_irk)\n', "ir_r")
p = sub(p, "np.float32(coeff_hpf(350.0, sr))", "np.float32(coeff_hpf(hp_hz, sr))", "hpf")
p = sub(p, "np.float32(_coeff_tau(1.0/(2*np.pi*7500.0), sr))", "np.float32(_coeff_tau(1.0/(2*np.pi*lp_hz), sr))", "lpf")
p = sub(p, "key = (path, sr_target)", "key = (path, sr_target, int(max_len))", "cache key")
open("dsp_pro.py", "w").write(p)
ast.parse(p)
print("  dsp_pro.py patched")

# ── auto.py ──
a = open("auto.py").read()
a = sub(a, '''    plate = None
    if _NEW["plate_t1"]:
        try:
            import dsp_pro
            plate = dsp_pro.plate_wet(voc, sr, mix=1.0, duck_depth=10.0)
''', '''    plate = None
    _ap = None
    _aa = None
    if _NEW["plate_t1"]:
        try:
            import dsp_pro
            if _NEW.get("adaptive_amb", False):
                try:
                    import adaptive_ambience as _aa
                    _ap = _aa.choose_params(voc, sr, bpm, role or "lead",
                                            str(_PRESET.get("ambience_style") or "clean"))
                except Exception as _ae:
                    _REVERB_LAST["adaptive_error"] = str(_ae)[:200]
                    _ap = None
            if _ap is not None:
                plate = dsp_pro.plate_wet(voc, sr, mix=1.0, duck_depth=10.0,
                                          predelay_ms=_ap["predelay_ms"], hp_hz=_ap["hpf_hz"],
                                          lp_hz=_ap["lpf_hz"], ir_len_s=_ap["ir_len_s"])
            else:
                plate = dsp_pro.plate_wet(voc, sr, mix=1.0, duck_depth=10.0)
''', "ambience plate call")
a = sub(a, "    wet = a * float(plate_scale)\n", '''    _send = float(plate_scale)
    if _ap is not None:
        try:
            _send = _aa.calibrate_send(voc, a, _ap["target_db"])
            _REVERB_LAST["adaptive"] = {k: (round(v, 3) if isinstance(v, float) else v)
                                        for k, v in _ap.items() if k != "analysis"}
            _REVERB_LAST["adaptive"]["send"] = round(_send, 4)
        except Exception as _ce:
            _REVERB_LAST["adaptive_error"] = str(_ce)[:200]
            _send = float(plate_scale)
    wet = a * _send
''', "send")
a = sub(a, '    "plate_t1":      True,\n', '    "plate_t1":      True,\n    "adaptive_amb":  True,\n', "flag")
open("auto.py", "w").write(a)
ast.parse(a)
print("  auto.py patched")
print("ALL PATCHED + COMPILES OK")
