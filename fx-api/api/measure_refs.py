import numpy as np
import subprocess

def _load_ffmpeg(path, sr=44100):
    r = subprocess.run(
        ['ffmpeg','-v','quiet','-i',path,'-f','f32le','-ac','1','-ar',str(sr),'-'],
        capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError('ffmpeg decode failed')
    return np.frombuffer(r.stdout, dtype=np.float32), sr
import glob, os

def _mono(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2 and x.shape[0] <= 2: return x.mean(axis=0)
    if x.ndim == 2: return x.mean(axis=1)
    return x

def _frames_db(m, sr, win=0.02):
    n = max(1, int(win * sr))
    k = len(m) // n
    e = np.sqrt((m[: k * n].reshape(k, n) ** 2).mean(axis=1) + 1e-18)
    return 20 * np.log10(e)

def analyze(voc, sr):
    m = _mono(voc)
    edb = _frames_db(m, sr)
    peak_db = 20 * np.log10(np.abs(m).max() + 1e-12)
    thr = max(np.percentile(edb, 95) - 35.0, -70.0)
    act = edb > thr
    active_frac = float(act.mean())
    runs, cur = [], 0
    for a in act:
        if not a: cur += 1
        elif cur: runs.append(cur); cur = 0
    gap_s = float(np.median(runs) * 0.02) if runs else 0.0
    n = int(0.02 * sr)
    k = len(m) // n
    fr = m[: k * n].reshape(k, n)[act[:k]]
    if len(fr) < 10: fr = m[: k * n].reshape(k, n)
    x = fr.reshape(-1)
    n_fft = 4096
    if len(x) < n_fft:
        n_fft = max(512, 1 << int(np.log2(max(len(x), 2))))
    seg = x[: (len(x) // n_fft) * n_fft].reshape(-1, n_fft)
    win = np.hanning(n_fft).astype(np.float64)
    P = (np.abs(np.fft.rfft(seg * win, axis=1)) ** 2).mean(axis=0) / (win**2).sum()
    f = np.fft.rfftfreq(n_fft, 1.0 / sr)
    band = lambda a, b: P[(f >= a) & (f < b)].sum() + 1e-18
    lowmid = band(250, 500) / band(500, 5000)
    bright = 10 * np.log10(band(5000, 9000) / band(1000, 4000))
    # Sub band, useful context
    sub = 10 * np.log10(band(40, 120) / band(500, 5000))
    return dict(peak_db=peak_db, active_frac=active_frac, gap_s=gap_s,
                lowmid=lowmid, bright_db=bright, sub_db=sub)

files = sorted(glob.glob('refs/vocals/*.mp3') + glob.glob('refs/vocals/*.wav'))
files = [f for f in files if os.path.getsize(f) > 100000]

hdr = '%-16s %8s %9s %8s %9s %9s %9s' % ('track', 'lowmid', 'bright', 'gap_s', 'active%', 'peak_db', 'sub_dB')
print(hdr); print('-' * len(hdr))
rows = []
for f in files:
    try:
        x, sr = _load_ffmpeg(f)
        a = analyze(x, sr)
        print('%-16s %8.3f %9.1f %8.3f %9.1f %9.1f %9.1f' % (
            os.path.basename(f)[:16], a['lowmid'], a['bright_db'],
            a['gap_s'], a['active_frac']*100, a['peak_db'], a['sub_db']))
        rows.append((os.path.basename(f), a))
    except Exception as e:
        print('%-16s ERROR: %s' % (os.path.basename(f)[:16], str(e)[:50]))

if rows:
    print()
    print('Population stats (%d refs):' % len(rows))
    for k in ('lowmid', 'bright_db', 'gap_s', 'active_frac'):
        vals = np.array([r[1][k] for r in rows])
        print('  %-12s min=%.3f  med=%.3f  max=%.3f  std=%.3f' % (
            k, vals.min(), np.median(vals), vals.max(), vals.std()))
