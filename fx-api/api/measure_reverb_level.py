"""Measure reverb-to-dry ratio from isolated vocal files.

For each ref vocal:
  1. Compute a short-window RMS envelope
  2. "Loud" frames = top 10% (words)
  3. "Quiet" frames = bottom 40%, above noise floor (gaps + tails)
  4. Ratio in dB = quiet_rms - loud_rms
     That's how loud the reverb tail is under the words.
"""
import numpy as np
import subprocess
import glob, os

def load(path, sr=44100):
    r = subprocess.run(
        ['ffmpeg','-v','quiet','-i',path,'-f','f32le','-ac','1','-ar',str(sr),'-'],
        capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError('ffmpeg fail')
    return np.frombuffer(r.stdout, dtype=np.float32), sr

def measure(path):
    x, sr = load(path)
    win = int(sr * 0.02)          # 20 ms frames
    k = len(x) // win
    if k < 50:
        return None
    e = np.sqrt((x[:k*win].reshape(k, win) ** 2).mean(axis=1) + 1e-18)
    edb = 20 * np.log10(e)

    # Noise floor = 5th percentile (clean silence)
    floor = np.percentile(edb, 5)
    # Loud = top 10% (words)
    loud = np.percentile(edb, 90)

    # Quiet frames = below loud-15dB, above floor+5dB (real tails, not noise)
    quiet_mask = (edb < loud - 15) & (edb > floor + 5)
    if quiet_mask.sum() < 20:
        quiet_mask = (edb < loud - 12) & (edb > floor + 3)
    if quiet_mask.sum() < 10:
        return None
    quiet = float(edb[quiet_mask].mean())

    ratio = quiet - loud           # negative dB, how far under words
    return {
        'loud_db': round(float(loud), 1),
        'quiet_db': round(quiet, 1),
        'floor_db': round(float(floor), 1),
        'ratio_db': round(ratio, 1),
        'n_quiet': int(quiet_mask.sum()),
        'n_total': int(k),
    }

files = sorted(glob.glob('refs/vocals/*.mp3') + glob.glob('refs/vocals/*.wav'))
files = [f for f in files if os.path.getsize(f) > 100000]

print('%-28s %8s %8s %8s %9s' % ('track', 'loud', 'quiet', 'floor', 'ratio'))
print('-' * 65)
ratios = []
for f in files:
    try:
        r = measure(f)
        if r:
            print('%-28s %8.1f %8.1f %8.1f %+9.1f' % (
                os.path.basename(f)[:28], r['loud_db'], r['quiet_db'],
                r['floor_db'], r['ratio_db']))
            ratios.append(r['ratio_db'])
        else:
            print('%-28s (insufficient data)' % os.path.basename(f)[:28])
    except Exception as e:
        print('%-28s ERROR %s' % (os.path.basename(f)[:28], str(e)[:30]))

if ratios:
    print()
    print('Population (%d refs):' % len(ratios))
    print('  min   %.1f dB' % min(ratios))
    print('  median %.1f dB' % float(np.median(ratios)))
    print('  max   %.1f dB' % max(ratios))
    print()
    print('=> Suggested TARGET_DB for lead: %.1f' % float(np.median(ratios)))
