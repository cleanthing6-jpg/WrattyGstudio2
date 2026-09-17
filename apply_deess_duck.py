from pathlib import Path
import ast, re, sys

A = Path("fx-api/api/auto.py")
s = A.read_text(encoding="utf-8")
notes = []

def rep1(text, old, new, label, required=True):
    n = text.count(old)
    if n != 1:
        if required:
            sys.exit("ABORT [%s]: matched %d times (need 1) - NOTHING written" % (label, n))
        notes.append("SKIPPED %s (matched %d)" % (label, n))
        return text
    notes.append("ok  " + label)
    return text.replace(old, new, 1)

# 1. de-ess ceiling 5.0 -> 3.0, plus its own calibration constants
s = rep1(s,
    "MAX_PRESENCE, MAX_HARSH_CUT, MAX_AIR, MAX_DEESS = 1.5, 3.0, 2.5, 5.0",
    "MAX_PRESENCE, MAX_HARSH_CUT, MAX_AIR, MAX_DEESS = 1.5, 3.0, 2.5, 3.0\n"
    "DEESS_OFFSET_DB = 6.0   # trigger this far above the band's own median\n"
    "DEESS_ATK, DEESS_REL = 1.0, 4.0",
    "MAX_DEESS 5.0 -> 3.0, DEESS_* constants added")

# 2. de-esser: remove the dead st["sib"] gate, self-calibrate
s = rep1(s,
'''def _deess(voc, sr, st):
    if st["sib"] < 3.0:
        return voc, 0.0
    freq = np.fft.rfftfreq(N, 1.0 / sr)
    k = (freq >= 5500) & (freq < 9000)
    out = np.empty_like(voc)
    mx = 0.0
    for c in range(voc.shape[0]):
        S = _stft(voc[c])
        lev = _level_db(S, k)
        red = _smooth(np.clip((lev - np.percentile(lev, 75)) * 0.6, 0.0, MAX_DEESS))''',
'''def _deess(voc, sr, st):
    """Sibilance control calibrated off the band's own level so it fires when
    sibilance is actually present. Runs BEFORE the air shelf in _role_chain."""
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
        red = _smooth(np.clip(lev - thr, 0.0, MAX_DEESS), atk=DEESS_ATK, rel=DEESS_REL)''',
    "de-esser: dead st['sib'] gate removed, median+6 dB trigger")

# 3. duck caps / targets
s = rep1(s,
    "DUCK_CAP = {BODY: 0.75, PRES: 1.5, HARSH: 1.0}\n"
    "DUCK_TARGET = {BODY: 1.0, PRES: 1.5, HARSH: 1.0}",
    "DUCK_CAP = {BODY: 1.5, PRES: 3.0, HARSH: 2.0}\n"
    "DUCK_TARGET = {BODY: 1.0, PRES: 2.5, HARSH: 1.5}",
    "duck caps -> 1.5/3.0/2.0, targets -> 1.0/2.5/1.5")

# 4. best effort: de-ess before the air shelf
pat = re.compile(
    r'(?P<sat>    out = _saturate\(out, sr, drive\)\n'
    r'    moves\.append\(\["saturate", round\(drive, 2\)\]\)\n)'
    r'(?P<air>    try:\n'
    r'        out = Pedalboard\(\[HighShelfFilter\(cutoff_frequency_hz=10000\.0,\n'
    r'                                          gain_db=min\(MAX_AIR, t\["air"\]\), q=0\.7\)\]\)\(out, sr\)\.astype\(np\.float32\)\n'
    r'    except Exception:\n        pass\n'
    r'    moves\.append\(\["air 10k", round\(min\(MAX_AIR, t\["air"\]\), 2\)\]\)\n)'
    r'(?P<dee>    out, dd = _deess\(out, sr, st\)\n'
    r'    moves\.append\(\["de-ess", dd\]\)\n)')
m = pat.search(s)
if m:
    s = s[:m.start()] + m.group('sat') + m.group('dee') + m.group('air') + s[m.end():]
    notes.append("ok  chain order: saturate -> de-ess -> air shelf")
else:
    notes.append("SKIPPED chain order (anchor differs) - de-ess still works, just after the shelf")

A.write_text(s, encoding="utf-8")
ast.parse(s)
for n in notes:
    print("  " + n)
print("SYNTAX OK - revert: git checkout -- fx-api/api/auto.py")
