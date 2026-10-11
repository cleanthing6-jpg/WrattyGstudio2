import pathlib, sys

src = pathlib.Path("auto.py")
text = src.read_text()

# ---- 1. module-level dict before the hook block ----
OLD_0 = "# --- WRATTY REVERB HOOK v1 BEGIN"
NEW_0 = "_REVERB_LAST = {}\n# --- WRATTY REVERB HOOK v1 BEGIN"

# ---- 2. stash _info inside _reverb_swap ----
OLD_1 = '''            wet, _info = _rvx.render(voc, sr, bpm, _PRESET.get("_name", "neutral"),
                                     target_rms=r_old, out_len=n_ref)'''
NEW_1 = '''            wet, _info = _rvx.render(voc, sr, bpm, _PRESET.get("_name", "neutral"),
                                     target_rms=r_old, out_len=n_ref)
            try:
                _REVERB_LAST[kind] = dict(_info) if _info else {}
            except Exception:
                pass'''

# ---- 3a. first report writer (8-space indent, before return) ----
OLD_2a = '''        rep["plate_error"] = plate_error()
        return _headroom(core), rep'''
NEW_2a = '''        rep["plate_error"] = plate_error()
        try:
            rep["reverb_last"] = dict(_REVERB_LAST)
        except Exception:
            rep["reverb_last"] = {}
        return _headroom(core), rep'''

# ---- 3b. second report writer (4-space indent) ----
OLD_2b = '''    rep["plate_error"] = plate_error()

    _DOUBLE_ON = False'''
NEW_2b = '''    rep["plate_error"] = plate_error()
    try:
        rep["reverb_last"] = dict(_REVERB_LAST)
    except Exception:
        rep["reverb_last"] = {}

    _DOUBLE_ON = False'''

patches = [
    ("hook dict", OLD_0, NEW_0),
    ("stash info", OLD_1, NEW_1),
    ("report writer A", OLD_2a, NEW_2a),
    ("report writer B", OLD_2b, NEW_2b),
]

for label, OLD, NEW in patches:
    n = text.count(OLD)
    if n != 1:
        print("ABORT [%s]: anchor matched %d times (need exactly 1)" % (label, n))
        sys.exit(1)

bak = src.with_suffix(".py.bak3")
bak.write_text(text)
print("backup:", bak)

for label, OLD, NEW in patches:
    text = text.replace(OLD, NEW)
    print("OK:", label)

src.write_text(text)
print("done: auto.py patched (reverb reporting)")
