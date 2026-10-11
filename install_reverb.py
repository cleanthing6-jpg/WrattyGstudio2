#!/usr/bin/env python3
"""
install_reverb.py - plug reverb_fx.py into WrattyGstudio's plate + hall. Reversible.

WHAT IT CHANGES in fx-api/api/auto.py (nothing else)
  1. stores the resolved preset name in apply_preset()
  2. appends a marked block at end of auto.py that wraps _plate() and _hall():
       * old _plate / _hall still run first — their result is the fallback
       * new reverb is rendered with preset settings + song BPM
       * level-matched to the old reverb's RMS so ROLE_BUS balance stays
       * output shape/dtype/length match the old call
       * any error falls back to old reverb and prints [reverb_fx] fallback ...

USAGE
    python3 install_reverb.py             # dry run
    python3 install_reverb.py --apply
    python3 install_reverb.py --remove    # strips the block

REQUIRES reverb_fx.py in fx-api/api/ first.
"""
import os
import py_compile
import shutil
import sys
import time

APPLY = "--apply" in sys.argv
REMOVE = "--remove" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = os.path.expanduser(args[0]) if args else os.path.expanduser("~/WrattyGstudio2")
API = os.path.join(ROOT, "fx-api", "api")
AUTO = os.path.join(API, "auto.py")

BEGIN = "# --- WRATTY REVERB HOOK v1 BEGIN"
END = "# --- WRATTY REVERB HOOK v1 END ---"

OLD_NAME = '_PRESET["_deltas"] = ROLE_DELTAS.get(p, {})'
NEW_NAME = OLD_NAME + '\n    _PRESET["_name"] = p'

HOOK = '''
# --- WRATTY REVERB HOOK v1 BEGIN (python3 install_reverb.py --remove restores the original) ---
try:
    try:
        import reverb_fx as _rvx
    except ImportError:
        from . import reverb_fx as _rvx
    import os as _os_rvx
    _plate_legacy = _plate
    _hall_legacy = _hall
    _REV_NOTE_CACHE = {"bpm": None}

    def _reverb_swap(voc, sr, kind, legacy_fn):
        old = legacy_fn(voc, sr)
        if old is None:
            return None
        if _os_rvx.environ.get("WRATTY_REVERB", "1") == "0":
            return old
        try:
            ref = np.asarray(old)
            n_ref = ref.shape[-1] if ref.ndim >= 2 else ref.shape[0]
            r_old = float(np.sqrt(np.mean(np.square(ref, dtype=np.float64))))
            if r_old <= 0.0:
                return old
            # song bpm is stored by the delay hook; fall back to 100
            bpm = _PRESET.get("_bpm", 100.0)
            wet, _info = _rvx.render(voc, sr, bpm, _PRESET.get("_name", "neutral"),
                                     target_rms=r_old, out_len=n_ref)
            if wet.shape[-1] < n_ref:
                wet = np.pad(wet, ((0, 0), (0, n_ref - wet.shape[-1])))
            elif wet.shape[-1] > n_ref:
                wet = wet[:, :n_ref]
            return np.ascontiguousarray(wet, dtype=np.float32)
        except Exception as _e:
            print("[reverb_fx] fallback to legacy %s: %s" % (kind, _e))
            return old

    def _plate(voc, sr):
        return _reverb_swap(voc, sr, "plate", _plate_legacy)

    def _hall(voc, sr):
        return _reverb_swap(voc, sr, "hall", _hall_legacy)
except Exception as _e:
    print("[reverb_fx] not installed, using legacy reverb:", _e)
# --- WRATTY REVERB HOOK v1 END ---
'''


def write_checked(path, text):
    bak = "%s.bak-pre-reverb-%s" % (path, time.strftime("%m%d-%H%M%S"))
    shutil.copy2(path, bak)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        py_compile.compile(path, doraise=True)
        print("  written; compiled OK; backup: %s" % os.path.basename(bak))
        return True
    except py_compile.PyCompileError as e:
        shutil.copy2(bak, path)
        print("  !! compile failed, RESTORED backup: %s" % e)
        return False


def main():
    if not os.path.isfile(AUTO):
        print("!! %s not found" % AUTO); sys.exit(1)
    text = open(AUTO, encoding="utf-8").read()
    if REMOVE:
        if BEGIN not in text:
            print("hook not present - nothing to remove"); return
        a = text.index(BEGIN); b = text.index(END) + len(END)
        new = (text[:a].rstrip("\n") + "\n" + text[b:].lstrip("\n"))
        print("REMOVE hook block (%d chars)" % (b - a))
        if APPLY: write_checked(AUTO, new)
        else: print("DRY RUN (nothing written, add --apply)")
        return
    if not os.path.isfile(os.path.join(API, "reverb_fx.py")):
        print("!! reverb_fx.py must be copied into %s first" % API); sys.exit(1)
    new = text
    if '_PRESET["_name"] = p' in new:
        print("  ALREADY  store preset name")
    elif new.count(OLD_NAME) == 1:
        new = new.replace(OLD_NAME, NEW_NAME)
        print("  APPLY    store preset name in apply_preset()")
    else:
        print("  SKIPPED  store preset name (found %d matches)" % new.count(OLD_NAME))
    if BEGIN in new:
        print("  ALREADY  reverb hook block")
    elif "def _plate(" not in new or "def _hall(" not in new:
        print("  SKIPPED  reverb hook (no def _plate / def _hall in auto.py)")
    else:
        new = new.rstrip("\n") + "\n" + HOOK
        print("  APPLY    reverb hook block appended at end of auto.py")
    if new == text:
        print("nothing to do"); return
    if APPLY: write_checked(AUTO, new)
    else: print("DRY RUN (nothing written, add --apply)")


if __name__ == "__main__":
    main()
