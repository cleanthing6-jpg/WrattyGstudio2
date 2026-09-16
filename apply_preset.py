from pathlib import Path
import ast, sys

A = Path("fx-api/api/auto.py"); M = Path("fx-api/api/mix.py"); W = Path("modal_mix.py")
for p in (A, M, W):
    if not p.exists(): sys.exit("ABORT: %s missing" % p)
a = A.read_text(encoding="utf-8"); m = M.read_text(encoding="utf-8"); w = W.read_text(encoding="utf-8")

def rep(t, old, new, want, label):
    n = t.count(old)
    if n != want: sys.exit("ABORT: '%s' matched %d times (need %d)" % (label, n, want))
    print("  ok  " + label)
    return t.replace(old, new, want)

# ---------- auto.py: preset engine ----------
BLOCK = '''
# ---------- genre presets (Deploy 1: neutral + afrobeats) ----------
PRESETS = {
    "neutral": {},
    "afrobeats": {
        "target_lufs": -12.0, "glue_ratio": 1.5, "glue_gr_db": 0.8,
        "width": 1.12, "plate_db": -15.0, "slap_db": -18.0,
    },
}
ROLE_DELTAS = {
    "afrobeats": {"lead": {"air": 0.5, "sat": 0.4}, "backing": {"pres": -0.2}},
}
_PRESET = {}


def preset_config(name):
    p = str(name or "neutral").lower()
    if p not in PRESETS:
        p = "neutral"
    return p, dict(PRESETS[p])


def apply_preset(name):
    """Activate a preset. Returns its config dict."""
    global _PRESET, SEND_PLATE, SEND_SLAP
    p, cfg = preset_config(name)
    _PRESET = dict(cfg)
    _PRESET["_deltas"] = ROLE_DELTAS.get(p, {})
    SEND_PLATE = 10.0 ** (float(cfg.get("plate_db", -14.0)) / 20.0)
    SEND_SLAP = 10.0 ** (float(cfg.get("slap_db", -14.0)) / 20.0)
    return _PRESET


def _treat_for(role):
    t = ROLE_TREAT.get(role, ROLE_TREAT["other"])
    d = _PRESET.get("_deltas", {}).get(role)
    if d:
        t = dict(t)
        t.update(d)
    return t
'''
a = rep(a, '                "sat": 1.5, "width": 1.10},\n}',
        '                "sat": 1.5, "width": 1.10},\n}\n' + BLOCK.rstrip("\n") + "\n",
        1, "preset engine added after ROLE_TREAT")
a = rep(a, '    t = ROLE_TREAT.get(role, ROLE_TREAT["other"])',
        '    t = _treat_for(role)', 2, "role chain reads preset-aware treatment")
a = rep(a, '    mixed = _widen(mixed, sr)\n    mixed = _headroom(mixed)',
        '    mixed = _widen(mixed, sr, _PRESET.get("width") or None)\n    mixed = _headroom(mixed)',
        1, "final width from preset")

# ---------- mix.py: preset plumbing ----------
m = rep(m, 'def do_mix(stems, loud, jid, max_sec=0):',
        'def do_mix(stems, loud, jid, max_sec=0, preset="neutral"):', 1, "do_mix accepts preset")
m = rep(m, '    tmp = tempfile.mkdtemp()\n    try:\n        sr = None',
        '    tmp = tempfile.mkdtemp()\n    try:\n        cfg = auto.apply_preset(preset)\n        sr = None',
        1, "preset applied at mix start")
m = rep(m, '        tgt = TARGET.get(want, -14.0)',
        '        tgt = TARGET.get(want)\n        if tgt is None:\n            tgt = float(cfg.get("target_lufs", -14.0))',
        1, "preset LUFS used when loudness is AUTO")
m = rep(m, '''            setjob(jid, "glue bus")
            _thr = float(np.clip(rmsdb(mixed) - 3.0, -40.0, -6.0))
            mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                                Compressor(threshold_db=_thr, ratio=1.5,
                                           attack_ms=30.0, release_ms=130.0)])(mixed, sr).astype(np.float32)
            report["glue_thr_db"] = round(_thr, 2)''',
'''            setjob(jid, "glue bus")
            _gr = float(cfg.get("glue_gr_db", 1.0))
            _rat = float(cfg.get("glue_ratio", 1.5))
            _over = _gr * _rat / max(0.1, _rat - 1.0)
            _thr = float(np.clip(rmsdb(mixed) - _over, -40.0, -6.0))
            mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                                Compressor(threshold_db=_thr, ratio=_rat,
                                           attack_ms=30.0, release_ms=130.0)])(mixed, sr).astype(np.float32)
            report["glue_thr_db"] = round(_thr, 2)''', 1, "glue ratio/GR from preset")
m = rep(m, 'def worker(jid, stems, loud, max_sec=0):',
        'def worker(jid, stems, loud, max_sec=0, preset="neutral"):', 1, "worker accepts preset")
m = rep(m, '        res = do_mix(stems, loud, jid, max_sec)',
        '        res = do_mix(stems, loud, jid, max_sec, preset)', 1, "worker passes preset")
m = rep(m, '        t = threading.Thread(target=worker, args=(jid, stems, str(data.get("loudness") or "MEDIUM"), float(data.get("maxSeconds") or 0)))',
        '        t = threading.Thread(target=worker, args=(jid, stems, str(data.get("loudness") or "MEDIUM"), str(data.get("preset") or "neutral"), float(data.get("maxSeconds") or 0)))',
        1, "HTTP handler forwards preset")
m = rep(m, '                "mode": mode, "report": report}',
        '                "mode": mode, "report": report, "preset": preset}', 1, "result includes preset")

# ---------- modal_mix.py: API plumbing ----------
w = rep(w, 'def run_mix(job_id: str, stems: list, loudness: str, max_seconds: float):',
        'def run_mix(job_id: str, stems: list, loudness: str, preset: str = "neutral", max_seconds: float = 0):',
        1, "run_mix accepts preset")
w = rep(w, '        res = mix.do_mix(stems, loudness, job_id, max_seconds)',
        '        res = mix.do_mix(stems, loudness, job_id, max_seconds, preset)', 1, "run_mix forwards preset")
w = rep(w, '''        run_mix.spawn(
            jid,
            stems,
            str(body.get("loudness") or "MEDIUM"),
            float(body.get("maxSeconds") or 0),
        )''',
'''        run_mix.spawn(
            jid,
            stems,
            str(body.get("loudness") or "MEDIUM"),
            str(body.get("preset") or "neutral"),
            float(body.get("maxSeconds") or 0),
        )''', 1, "web handler forwards preset")

A.write_text(a, encoding="utf-8"); M.write_text(m, encoding="utf-8"); W.write_text(w, encoding="utf-8")
ast.parse(a); ast.parse(m); ast.parse(w)
print("SYNTAX OK - revert: git checkout -- fx-api/api/auto.py fx-api/api/mix.py modal_mix.py")
