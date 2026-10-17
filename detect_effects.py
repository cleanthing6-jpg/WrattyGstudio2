import subprocess, numpy as np, glob, os

def decode_stereo(path, sr=44100):
    out = subprocess.run(
        ["ffmpeg","-hide_banner","-loglevel","error","-i",path,
         "-ac","2","-ar",str(sr),"-f","f32le","-"],
        capture_output=True)
    x = np.frombuffer(out.stdout, dtype=np.float32)
    if len(x) % 2: x = x[:-1]
    return x.reshape(-1, 2).T, sr  # (2, n)

def reverb_tail(x, sr):
    """Median decay time after last word (-20 dB)."""
    mono = x.mean(0)
    # envelope 10ms
    w = sr // 100
    n = len(mono) // w * w
    env = np.abs(mono[:n].reshape(-1, w)).max(1)
    if len(env) < 10: return 0.0
    thr = np.percentile(env, 85)
    peaks = np.where(env > thr)[0]
    decays = []
    for p in peaks[:300]:
        e0 = env[p]
        if e0 < 1e-4: continue
        end = min(p + 100, len(env))
        below = np.where(env[p:end] < e0 * 0.1)[0]
        if len(below):
            decays.append(below[0] * 10)  # ms
    return round(float(np.median(decays)), 1) if decays else 0.0

def delay_detect(x, sr):
    """Autocorrelation of envelope — strong periodic peaks = delay."""
    mono = x.mean(0)
    w = sr // 100  # 10 ms
    n = len(mono) // w * w
    env = np.abs(mono[:n].reshape(-1, w)).max(1)
    if len(env) < 50: return 0.0, 0.0
    env = env - env.mean()
    ac = np.correlate(env, env, 'full')[len(env)-1:]
    ac = ac / (ac[0] + 1e-9)
    # look for peaks in 100-800 ms lag (10-80 frames of 10 ms)
    lag_range = ac[10:80]
    if lag_range.size == 0: return 0.0, 0.0
    peak_idx = int(np.argmax(lag_range)) + 10
    peak_val = float(lag_range[peak_idx - 10])
    return peak_val, round(peak_idx * 10, 1)  # (strength, lag ms)

def saturation_ratio(x, sr):
    """2nd vs 1st harmonic in low-freq region (proxy for even-harmonic sat)."""
    mono = x.mean(0)
    nfft = 1 << 15
    # find strongest fundamental in 100-500 Hz
    f = np.fft.rfftfreq(nfft, 1.0/sr)
    band = (f >= 100) & (f < 500)
    psd_total = np.zeros(len(f))
    cnt = 0
    for i in range(0, len(mono) - nfft, nfft):
        seg = mono[i:i+nfft] * np.hanning(nfft)
        if np.max(np.abs(seg)) < 1e-4: continue
        psd_total += np.abs(np.fft.rfft(seg)) ** 2
        cnt += 1
    if cnt == 0: return 0.0
    psd_total /= cnt
    fund_idx = np.argmax(psd_total[band]) + np.where(band)[0][0]
    fund_f = f[fund_idx]
    # look for 2nd harmonic bin
    h2_f = fund_f * 2
    if h2_f > f[-1]: return 0.0
    h2_idx = np.argmin(np.abs(f - h2_f))
    p_fund = psd_total[fund_idx] + 1e-20
    p_h2 = psd_total[max(0, h2_idx-2):h2_idx+3].sum() + 1e-20
    return round(10*np.log10(p_h2 / p_fund), 1)

def compression_crest_dist(x, sr):
    """Median crest factor over 100ms windows — proxy for compression depth."""
    mono = x.mean(0)
    w = sr // 10
    n = len(mono) // w * w
    crests = []
    for i in range(0, n, w):
        seg = mono[i:i+w]
        pk = np.max(np.abs(seg))
        rms = np.sqrt(np.mean(seg**2))
        if rms > 1e-5:
            crests.append(20*np.log10(pk/rms + 1e-9))
    return round(float(np.median(crests)), 1), round(float(np.std(crests)), 1)

def stereo_width(x, sr):
    """Side/mid ratio in dB."""
    if x.shape[0] < 2: return -99.0, 1.0
    mid = (x[0] + x[1]) * 0.5
    side = (x[0] - x[1]) * 0.5
    m = np.sqrt(np.mean(mid**2) + 1e-9)
    s = np.sqrt(np.mean(side**2) + 1e-9)
    sm = 20*np.log10(s / m + 1e-9)
    # correlation
    corr = float(np.corrcoef(x[0], x[1])[0, 1]) if len(x[0]) > 100 else 1.0
    return round(sm, 1), round(corr, 3)

def adt_check(x, sr):
    """L/R cross-correlation peak at 10-40 ms = doubling/ADT."""
    if x.shape[0] < 2: return 0.0, 0.0
    lo = int(sr * 0.010)
    hi = int(sr * 0.040)
    L, R = x[0], x[1]
    # sample-based correlation at lags in 10-40 ms
    L = L - L.mean(); R = R - R.mean()
    n = min(len(L), len(R))
    L = L[:n]; R = R[:n]
    nrm = np.sqrt((L**2).sum() * (R**2).sum()) + 1e-9
    best = 0.0; best_lag = 0
    for lag in range(lo, hi, 4):
        c = float((L[lag:] * R[:n-lag]).sum() / nrm)
        if abs(c) > abs(best):
            best = c; best_lag = lag
    return round(best, 3), round(best_lag * 1000.0 / sr, 1)

files = sorted(glob.glob("refs/vocals/*.mp3") + glob.glob("refs/vocals/*.wav"))
if not files:
    print("no vocal files"); raise SystemExit

hdr = f"{'track':14s} {'tail_ms':>8s} {'delay_str':>9s} {'delay_ms':>8s} {'sat2nd':>7s} {'crest':>6s} {'crestSD':>7s} {'S/M':>6s} {'corr':>6s} {'ADT':>5s} {'ADT_ms':>6s}"
print(hdr)
print("-" * len(hdr))
for path in files:
    name = os.path.basename(path).rsplit(".", 1)[0][:14]
    try:
        x, sr = decode_stereo(path)
        if x.shape[1] < sr:
            print(f"{name:14s} too short")
            continue
        tail = reverb_tail(x, sr)
        dstr, dlag = delay_detect(x, sr)
        sat = saturation_ratio(x, sr)
        crest, crestsd = compression_crest_dist(x, sr)
        sm, corr = stereo_width(x, sr)
        adt, adtms = adt_check(x, sr)
        print(f"{name:14s} {tail:>8.1f} {dstr:>9.2f} {dlag:>8.1f} {sat:>7.1f} "
              f"{crest:>6.1f} {crestsd:>7.2f} {sm:>6.1f} {corr:>6.3f} {adt:>5.2f} {adtms:>6.1f}")
    except Exception as e:
        print(f"{name:14s} error: {str(e)[:60]}")
