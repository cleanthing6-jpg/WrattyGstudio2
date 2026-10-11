#!/usr/bin/env python3
import os, py_compile, shutil, sys, time

APPLY = "--apply" in sys.argv
REMOVE = "--remove" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = os.path.expanduser(args[0]) if args else os.path.expanduser("~/WrattyGstudio2")
API = os.path.join(ROOT, "fx-api", "api")
AUTO = os.path.join(API, "auto.py")

BEGIN = "# --- WRATTY DELAY HOOK v1 BEGIN"
END = "# --- WRATTY DELAY HOOK v1 END ---"

OLD_NAME = '_PRESET["_deltas"] = ROLE_DELTAS.get(p, {})'
NEW_NAME = OLD_NAME + '\n    _PRESET["_name"] = p'

HOOK = '''
# --- WRATTY DELAY HOOK v1 BEGIN (python3 install_delay.py --remove restores the original delay) ---
try:
    try:
        import delay_fx as _dfx
    except ImportError:
        from . import delay_fx as _dfx
    import os as _os_dfx
    _pingpong_legacy = _pingpong

    def _pingpong(voc, sr, bpm, note=0.75):
        old = _pingpong_legacy(voc, sr, bpm, note=note)
        if _os_dfx.environ.get("WRATTY_DELAY", "1") == "0":
            return old
        try:
            ref = np.asarray(old)
            if ref.ndim == 2 and ref.shape[0] <= 8:
                lay, n_ref = "cf", ref.shape[1]
            elif ref.ndim == 2:
                lay, n_ref = "cl", ref.shape[0]
            else:
                lay, n_ref = "m", ref.shape[0]
            r_old = float(np.sqrt(np.mean(np.square(ref, dtype=np.float64))))
            if r_old <= 0.0:
                return old
            wet, _info = _dfx.render(voc, sr, bpm, _PRESET.get("_name", "neutral"),
                                     note=note, target_rms=r_old)
            n = wet.shape[1]
            if n < n_ref:
                wet = np.pad(wet, ((0, 0), (0, n_ref - n)))
            elif n > n_ref:
                wet = wet[:, :n_ref]
            if lay == "cl":
                wet = wet.T
            elif lay == "m":
                wet = wet.mean(axis=0)
            return np.ascontiguousarray(wet, dtype=np.float32)
        except Exception as _e:
            print("[delay_fx] fallback to legacy delay:", _e)
            return old
except Exception as _e:
    print("[delay_fx] not installed, using legacy delay:", _e)
# --- WRATTY DELAY HOOK v1 END ---
'''

def write_checked(path, text):
    bak = "%s.bak-pre-delay-%s" % (path, time.strftime("%m%d-%H%M%S"))
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
        print("!! %s not found" % AUTO)
        sys.exit(1)
    text = open(AUTO, encoding="utf-8").read()
    if REMOVE:
        if BEGIN not in text:
            print("hook not present - nothing to remove")
            return
        a = text.index(BEGIN)
        b = text.index(END) + len(END)
        new = (text[:a].rstrip("\n") + "\n" + text[b:].lstrip("\n"))
        print("REMOVE hook block (%d chars)" % (b - a))
        if APPLY: write_checked(AUTO, new)
        else: print("DRY RUN (nothing written, add --apply)")
        return
    if not os.path.isfile(os.path.join(API, "delay_fx.py")):
        print("!! delay_fx.py must be copied into %s first" % API)
        sys.exit(1)
    new = text
    if '_PRESET["_name"] = p' in new:
        print("  ALREADY  store preset name")
    elif new.count(OLD_NAME) == 1:
        new = new.replace(OLD_NAME, NEW_NAME)
        print("  APPLY    store preset name in apply_preset()")
    else:
        print("  SKIPPED  store preset name (found %d matches)" % new.count(OLD_NAME))
    if BEGIN in new:
        print("  ALREADY  delay hook block")
    elif "def _pingpong(" not in new:
        print("  SKIPPED  delay hook (no def _pingpong found)")
    else:
        new = new.rstrip("\n") + "\n" + HOOK
        print("  APPLY    delay hook block appended at end of auto.py")
    if new == text:
        print("nothing to do")
        return
    if APPLY: write_checked(AUTO, new)
    else: print("DRY RUN (nothing written, add --apply)")

if __name__ == "__main__":
    main()
