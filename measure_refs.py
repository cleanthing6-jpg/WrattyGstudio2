import subprocess, json, glob, os
import numpy as np

BANDS = [(20,60),(60,120),(120,250),(250,600),
         (600,2000),(2000,5500),(5500,10000),(10000,16000)]

def decode_mono(path, sr=44100):
    """Decode any audio to mono float32 via ffmpeg pipe."""
    out = subprocess.run(
        ["ffmpeg","-hide_banner","-loglevel","error","-i",path,
         "-ac","1","-ar",str(sr),"-f","f32le","-"],
        capture_output=True)
    x = np.frombuffer(out.stdout, dtype=np.float32)
    return x, sr

def lufs_tp(path):
    out = subprocess.run(
        ["ffmpeg","-hide_banner","-nostats","-i",path,
         "-af","loudnorm=print_format=json","-f","null","-"],
        capture_output=True, text=True)
    s = out.stderr
    i, j = s.rfind("{"), s.rfind("}")
    if i < 0 or j < 0: return None, None
    try:
        d = json.loads(s[i:j+1])
        return float(d["input_i"]), float(d["input_tp"])
    except Exception:
        return None, None

def bands_db(x, sr):
    # Welch PSD manually (no scipy) — average periodograms
    nper = 32768
    if len(x) < nper: return {}
    hop = nper // 2
    win = np.hanning(nper).astype(np.float32)
    psd = np.zeros(nper // 2 + 1, dtype=np.float64)
    count = 0
    for start in range(0, len(x) - nper, hop):
        seg = x[start:start+nper] * win
        F = np.fft.rfft(seg)
        psd += (np.abs(F) ** 2)
        count += 1
    if count == 0: return {}
    psd /= count
    freqs = np.fft.rfftfreq(nper, 1.0 / sr)
    out = {}
    for lo, hi in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        out[f"{lo}-{hi}"] = round(10 * np.log10(psd[m].sum() + 1e-20), 1)
    return out

files = sorted(glob.glob("refs/*.mp3") + glob.glob("refs/*.wav") + glob.glob("refs/*.flac"))
rows = []
for path in files:
    name = os.path.basename(path)
    lufs, tp = lufs_tp(path)
    try:
        x, sr = decode_mono(path)
        bd = bands_db(x, sr)
    except Exception as e:
        print("band err:", name, e)
        bd = {}
    plr = None if (lufs is None or tp is None) else round(tp - lufs, 2)
    rows.append((name, lufs, tp, plr, bd))

hdr = f"{'track':22s} {'LUFS':>7s} {'TP':>6s} {'PLR':>5s} " + \
      " ".join(f"{b:>9s}" for b in ["20-60","60-120","120-250","250-600",
                                      "600-2k","2-5.5k","5.5-10k","10-16k"])
print(hdr)
print("-" * len(hdr))
for name, lufs, tp, plr, bd in rows:
    line = f"{name[:22]:22s} {str(lufs):>7s} {str(tp):>6s} {str(plr):>5s} "
    for b in ["20-60","60-120","120-250","250-600",
              "600-2000","2000-5500","5500-10000","10000-16000"]:
        line += f" {str(bd.get(b, '-')):>9s}"
    print(line)
