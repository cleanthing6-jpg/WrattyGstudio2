"""Measure crest factor (peak-to-RMS in dB) over 100ms frames.

This is what detect_effects.py reports as 'crest'. It's the tightness of
the vocal after compression. Refs measured earlier landed at 10-12 dB.
"""
import numpy as np
import subprocess
import glob, os

def load(path, sr=44100):
    r = subprocess.run(['ffmpeg','-v','quiet','-i',path,'-f','f32le','-ac','1','-ar',str(sr),'-'],
                       capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32), sr

def crest_median(x, sr, win_ms=100):
    w = int(sr * win_ms / 1000.0)
    k = len(x) // w
    if k < 5: return None
    segs = x[:k*w].reshape(k, w)
    pk = np.abs(segs).max(axis=1)
    rms = np.sqrt((segs**2).mean(axis=1))
    mask = rms > 1e-6
    crests = 20*np.log10(pk[mask] / (rms[mask] + 1e-9))
    return float(np.median(crests)), float(np.std(crests))

files = sorted(glob.glob('refs/vocals/*.mp3') + glob.glob('refs/vocals/*.wav'))
files = [f for f in files if os.path.getsize(f) > 100000]

print('%-28s %8s %8s' % ('track', 'crest', 'std'))
print('-' * 48)
crests = []
for f in files:
    try:
        x, sr = load(f)
        r = crest_median(x, sr)
        if r:
            print('%-28s %8.2f %8.2f' % (os.path.basename(f)[:28], r[0], r[1]))
            crests.append(r[0])
    except Exception as e:
        print('%-28s ERR' % os.path.basename(f)[:28])

if crests:
    print()
    print('Population: min=%.2f  median=%.2f  max=%.2f' % (
        min(crests), float(np.median(crests)), max(crests)))
    print('=> Target vocal crest: %.2f dB' % float(np.median(crests)))
