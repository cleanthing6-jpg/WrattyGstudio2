"""Measure delay feedback depth from isolated ref vocals.

At each word-end, sample the envelope at tap*1, tap*2, tap*3, tap*4, tap*5.
Successive peak ratios give the effective feedback.
  feedback (linear) = 10^((tap[n+1] - tap[n]) / 20)

For each ref, average across all words and all adjacent tap pairs.
"""
import numpy as np
import subprocess
import os
import glob

FRAME_MS = 5.0

REF_TAPS_MS = {
    'fola':       100.0,
    'boi chase':  100.0,
    'davido':     100.0,
    'burna boy':  150.0,
    'rema':       270.0,
}


def load(path, sr=44100):
    r = subprocess.run(
        ['ffmpeg','-v','quiet','-i',path,'-f','f32le','-ac','1','-ar',str(sr),'-'],
        capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError('ffmpeg fail')
    return np.frombuffer(r.stdout, dtype=np.float32), sr


def measure(path, tap_ms, n_taps=5):
    x, sr = load(path)
    w = int(sr * FRAME_MS / 1000.0)
    k = len(x) // w
    env = np.abs(x[:k*w].reshape(k, w)).max(axis=1)
    env_db = 20 * np.log10(env + 1e-12)

    tap_frames = int(round(tap_ms / FRAME_MS))
    if tap_frames < 4:
        return None

    loud_thr = np.percentile(env_db, 90)
    is_word = env_db > loud_thr - 3

    word_ends = [i for i in range(1, k) if is_word[i-1] and not is_word[i]]
    if len(word_ends) < 20:
        return None

    tap_energies = [[] for _ in range(n_taps)]
    for we in word_ends:
        for n in range(n_taps):
            pos = we + (n + 1) * tap_frames
            if pos >= k - 2:
                break
            window = env_db[max(0, pos-1):min(k, pos+2)]
            tap_energies[n].append(float(window.max()))

    min_len = min(len(t) for t in tap_energies if len(t) > 0)
    if min_len < 20:
        return None

    for i in range(n_taps):
        tap_energies[i] = tap_energies[i][:min_len]

    tap_means = [float(np.mean(t)) for t in tap_energies]

    fb_deltas = []
    for n in range(n_taps - 1):
        fb_deltas.append(tap_means[n+1] - tap_means[n])

    fb_estimates = [10 ** (d / 20.0) for d in fb_deltas]
    fb_avg = float(np.mean(fb_estimates))

    return dict(tap_db=tap_means, fb_deltas=fb_deltas, fb_avg=fb_avg, n_words=min_len)


files = sorted(glob.glob('refs/vocals/*.mp3') + glob.glob('refs/vocals/*.wav'))
files = [f for f in files if os.path.getsize(f) > 100000]

print('%-22s %5s  taps (dB rel 1st)                          fb' % ('track', 'n_wrd'))
print('-' * 88)

fbs = []
for f in files:
    base = os.path.basename(f).lower()
    tap = None
    for key, val in REF_TAPS_MS.items():
        if key in base:
            tap = val; break
    if tap is None:
        print('%-22s (skip — no known tap)' % os.path.basename(f)[:22]); continue
    try:
        r = measure(f, tap)
        if r is None:
            print('%-22s (insufficient data)' % os.path.basename(f)[:22]); continue
        tap_rel = [t - r['tap_db'][0] for t in r['tap_db']]
        tap_str = '  '.join('%+6.1f' % v for v in tap_rel)
        print('%-22s %5d  %s   → %.2f' % (
            os.path.basename(f)[:22], r['n_words'], tap_str, r['fb_avg']))
        fbs.append(r['fb_avg'])
    except Exception as e:
        print('%-22s ERROR %s' % (os.path.basename(f)[:22], str(e)[:40]))

if fbs:
    print()
    print('Population (%d refs):' % len(fbs))
    print('  min    %.3f' % min(fbs))
    print('  median %.3f' % float(np.median(fbs)))
    print('  max    %.3f' % max(fbs))
    print()
    print('=> Suggested feedback range: %.2f - %.2f, median %.2f' % (
        min(fbs), max(fbs), float(np.median(fbs))))
