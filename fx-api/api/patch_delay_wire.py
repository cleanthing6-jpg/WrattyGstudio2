from pathlib import Path
import ast, sys
P = Path("auto.py")
s = P.read_text(encoding="utf-8")

old = '''        _dspec = None
        try:
            import delay_spec as _dspec
        except Exception:
            try:
                from . import delay_spec as _dspec
            except Exception:
                _dspec = None
        if _dspec is not None:
            try:
                _dy, _dinfo = _dspec.render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))'''

new = '''        _dspec = None
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
        if _spec_render is not None:
            try:
                _dy, _dinfo = _spec_render(voc, sr, bpm, preset=str(_PRESET.get("_name") or "afrobeats"))'''

n = s.count(old)
if n != 1:
    sys.exit("ABORT: delay call site matched %d (need 1) - NOTHING written" % n)
s = s.replace(old, new, 1)
P.write_text(s, encoding="utf-8"); ast.parse(s)
print("  ok  _ambience now prefers dsp_delay.delay_render, falls back to delay_spec")
print("SYNTAX OK")
