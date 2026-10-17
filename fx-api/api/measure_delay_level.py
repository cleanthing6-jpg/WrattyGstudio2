"""Measure delay-to-dry ratio using KNOWN tap times per ref.

Tap times measured by detect_effects.py on the same vocal set.
No auto-detection — the values are fixed and verified.
"""
import numpy as np
import subprocess
import os

FRAME_MS = 5.0

# Known tap times from detect_effects.py (verified by envelope autocorrelation
# with a wider range and tighter thresholds)
REF_TAPS_MS = {
    'fola':       100.0,
    'boi chase':  100.0,
    'davido':     100.0,
    'burna boy':  150.0,
    'rema':       270.0,
    'shallipopi': None,    # not measured earlier
}

def load(path, sr=44100):
    r = subprocess.run(
        ['ffmpeg','-v','quiet','-i',path,'-f','f32le','-ac','1','-ar',str(sr),'-'],
        capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError('ffmpeg fail')
    return np.frombuffer(r.stdout, dtype=np.float32), sr

def measure(path, tap_ms):
    x, sr = load(path)
    w = int(sr * FRAME_MS / 1000.0)
    k = len(x) // w
    env = np.abs(x[:k*w].reshape(k, w)).max(axis=1)
    env_db = 20 * np.log10(env + 1e-12)

    tap_frames = int(round(tap_ms / FRAME_MS))

    loud_thr = np.percentile(env_db, 90)
    is_word = env_db > loud_thr - 3
    word_energy = float(env_db[is_word].mean())

    aligned_mask = np.zeros(k, dtype=bool)
    unaligned_mask = np.zeros(k, dtype=bool)

    for i in np.where(~is_word)[0]:
        if i < 1: continue
        j = i - 1
        while j >= 0 and not is_word[j]:
            j -= 1
        if j < 0: continue
        gap = i - j
        rem = gap % tap_frames
        dist = min(rem, tap_frames - rem)
        if dist <= 2:
            aligned_mask[i] = True
        elif gap > 6:
            unaligned_mask[i] = True

    if aligned_mask.sum() < 30 or unaligned_mask.sum() < 100:
        return None

    aligned_db   = float(env_db[aligned_mask].mean())
    unaligned_db = float(env_db[unaligned_mask].mean())
    delay_db     = aligned_db - unaligned_db
    ratio_db     = delay_db + unaligned_db - word_energy

    return {
        'word': word_energy, 'unalign': unaligned_db,
        'aligned': aligned_db, 'delay': delay_db, 'ratio': ratio_db,
        'n_align': int(aligned_mask.sum()),
    }

import glob
files = sorted(glob.glob('refs/vocals/*.mp3') + glob.glob('refs/vocals/*.wav'))
files = [f for f in files if os.path.getsize(f) > 100000]

print('%-24s %7s %7s %8s %8s %8s %8s' % (
    'track', 'tap', 'word', 'unalign', 'aligned', 'delay', 'ratio'))
print('-' * 76)

ratios = []
for f in files:
    base = os.path.basename(f).lower()
    tap = None
    for key, val in REF_TAPS_MS.items():
        if key in base:
            tap = val; break
    if tap is None:
        print('%-24s (no known tap — skip)' % os.path.basename(f)[:24]); continue
    try:
        r = measure(f, tap)
        if r:
            print('%-24s %7.1f %7.1f %8.1f %8.1f %+8.1f %+8.1f' % (
                os.path.basename(f)[:24], tap, r['word'],
                r['unalign'], r['aligned'], r['delay'], r['ratio']))
            ratios.append(r['ratio'])
        else:
            print('%-24s (insufficient data)' % os.path.basename(f)[:24])
    except Exception as e:
        print('%-24s ERROR %s' % (os.path.basename(f)[:24], str(e)[:40]))

if ratios:
    print()
    print('Population (%d refs):' % len(ratios))
    print('  min    %+.1f dB' % min(ratios))
    print('  median %+.1f dB' % float(np.median(ratios)))
    print('  max    %+.1f dB' % max(ratios))
    print()
    print('=> Suggested DELAY_TARGET_DB for lead: %.1f' % float(np.median(ratios)))
