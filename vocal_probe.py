#!/usr/bin/env python3
import sys, os, glob, wave, shutil, subprocess, tempfile
import numpy as np

DL = "/sdcard/Download"
BANDS = [(0,80),(250,600),(1500,4000),(5500,9000),(9000,16000)]
HDR   = ["rumble","mud","PRES","sib","air"]

def load(path):
    tmp = None
    if path.lower().endswith((".mp3",".m4a",".aac",".flac",".ogg")):
        if not shutil.which("ffmpeg"):
            raise SystemExit("need ffmpeg for that format:  pkg install ffmpeg")
        tmp = tempfile.mktemp(suffix=".wav")
        subprocess.run(["ffmpeg","-y","-loglevel","error","-i",path,
                        "-ac","2","-ar","44100","-sample_fmt","s16",tmp], check=True)
        path = tmp
    with wave.open(path, "rb") as w:
        ch, sr, sw, n = w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2:
        raise SystemExit("need 16-bit wav: " + path)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    x = x[:len(x) - (len(x) % ch)].reshape(-1, ch).T
    if tmp: os.unlink(tmp)
    return x, sr

def db(v):  return 20.0 * np.log10(max(float(v), 1e-12))
def rms(a): return float(np.sqrt(np.mean(a * a) + 1e-12))

def bd(a, sr, lo, hi):
    a = np.asarray(a, dtype=float); n = len(a)
    X = np.fft.rfft(a * np.hanning(n)); p = np.abs(X) ** 2
    w = np.ones_like(p); w[1:-1] = 2.0
    f = np.fft.rfftfreq(n, 1.0 / sr); k = (f >= lo) & (f < hi)
    if not k.any(): return -120.0
    return 10.0 * np.log10((np.sum(w[k] * p[k]) + 1e-30) /
                           (np.sum(w * p) + 1e-30))

def probe(path):
    x, sr = load(path); m = np.mean(x, axis=0)
    win = max(512, int(sr * 0.05))
    st = np.arange(0, max(1, len(m) - win), win)
    act = np.array([bd(m[s:s+win], sr, 1000.0, 4000.0) for s in st])
    sel = st[act >= np.percentile(act, 70)]
    acc = [[] for _ in BANDS]; cors = []
    for s in sel:
        seg = m[s:s+win]; f = db(rms(seg))
        for i, b in enumerate(BANDS):
            acc[i].append(bd(seg, sr, *b))
        if x.shape[0] >= 2:
            cors.append(float(np.corrcoef(x[0, s:s+win], x[1, s:s+win])[0, 1]))
    row = "".join("%+7.2f" % np.median(v) for v in acc)
    nm = os.path.basename(path)
    if len(nm) > 30: nm = nm[:11] + ".." + nm[-13:]
    print("%-30s %6.0fs%s %6.2f" % (nm, len(m)/sr, row,
                                    float(np.mean(cors)) if cors else 0.0))

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        fs = []
        for e in ("wav", "flac", "mp3"):
            fs += glob.glob(os.path.join(DL, "*." + e))
        fs.sort(key=os.path.getmtime, reverse=True)
        args = fs[:3]
        args += [p for p in fs if any(k in os.path.basename(p).lower()
                                      for k in ("chase", "do you", "do-you", "doyou"))][:2]
        if not args:
            raise SystemExit("no audio found in " + DL)
    print("%-30s %7s%s %6s" % ("file", "dur", "".join("%7s" % h for h in HDR), "corr"))
    for p in args:
        probe(p)
