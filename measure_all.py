#!/usr/bin/env python3
"""measure_all.py YOURS [REF1 REF2 ...] - full master analysis + delta vs refs.
WAV read via stdlib wave; LUFS/LRA/true-peak via ffmpeg ebur128. Non-WAV auto-converted."""
import sys, subprocess, re, wave
from pathlib import Path
import numpy as np

NFFT, HOP, CHUNK = 8192, 4096, 1 << 18
BANDS = [("sub 20-60",20,60),("bass 60-120",60,120),("lowmid 120-250",120,250),
         ("mid 250-500",250,500),("mid 500-1k",500,1000),("mid 1-2k",1000,2000),
         ("pres 2-5k",2000,5000),("air 5-10k",5000,10000),("air 10-16k",10000,16000)]

def mask(freq, lo, hi, sr): return (freq >= lo) & (freq < min(hi, sr/2.0))
def lg(v): return 10.0*np.log10(max(float(v), 1e-20))

def ensure_wav(path):
    p = Path(path)
    if p.suffix.lower() == ".wav":
        return str(p)
    out = str(Path.home()/(".measure_" + p.stem[:24] + ".wav"))
    subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-i",str(p),
                    "-ac","2","-ar","44100",out], check=True)
    return out

def ff_loudness(path):
    try:
        r = subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",str(path),
                            "-filter_complex","ebur128=peak=true","-f","null","-"],
                           capture_output=True, text=True, timeout=900)
        t = r.stderr or ""
    except Exception:
        return None, None, None
    def last(pat):
        m = re.findall(pat, t)
        return float(m[-1]) if m else None
    return (last(r"I:\s*(-?[0-9.]+)\s*LUFS"),
            last(r"LRA:\s*(-?[0-9.]+)\s*LU"),
            last(r"Peak:\s*(-?[0-9.]+)\s*dBFS"))

def read_wav(path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate(); ch = w.getnchannels(); sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32)/32768.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32)/2147483648.0
    elif sw == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32)-128.0)/128.0
    elif sw == 3:
        b3 = np.frombuffer(raw, dtype=np.uint8).reshape(-1,3).astype(np.int32)
        v = b3[:,0] | (b3[:,1]<<8) | (b3[:,2]<<16)
        v = np.where(v >= (1<<23), v-(1<<24), v).astype(np.float32)/8388608.0
        a = v
    else:
        raise ValueError("unsupported sample width %d" % sw)
    if ch > 1:
        a = a.reshape(-1, ch).T[:2]
    else:
        a = a[None, :]
    return np.ascontiguousarray(a, dtype=np.float32), sr

def overs_count(seg, k=4):
    n = seg.shape[0]; up = k*n
    F = np.fft.rfft(seg.astype(np.float64))
    F2 = np.zeros(up//2+1, dtype=np.complex128); F2[:F.shape[0]] = F*k
    return int(np.count_nonzero(np.abs(np.fft.irfft(F2, up)) > 1.0))

def measure(path):
    w = ensure_wav(path)
    x, sr = read_wav(w)
    n = x.shape[1]; dur = n/float(sr); o = {}
    sp = float(np.max(np.abs(x))); sp_db = 20.0*np.log10(max(sp,1e-12))
    lu, lra, tpk = ff_loudness(w)
    o["LUFS-I"] = lu
    o["TP dBTP"] = tpk if tpk is not None else sp_db
    o["Peak dBFS"] = sp_db
    o["Headroom dB"] = -sp_db
    o["LRA LU"] = lra
    o["PLR dB"] = (o["TP dBTP"] - lu) if lu is not None else None
    o["DC L"] = float(np.mean(x[0])); o["DC R"] = float(np.mean(x[1]))

    freq = np.fft.rfftfreq(NFFT, 1.0/sr); win = np.hanning(NFFT)
    masks = [(nm, mask(freq, lo, hi, sr)) for nm, lo, hi in BANDS]
    acc_pow = np.zeros(freq.shape[0]); acc_mag = np.zeros(freq.shape[0])
    bsum = {nm:0.0 for nm,lo,hi in BANDS}; bmax = {nm:0.0 for nm,lo,hi in BANDS}
    ssum = {nm:0.0 for nm,lo,hi in BANDS}
    cLL = {nm:0.0 for nm,lo,hi in BANDS}; cRR = {nm:0.0 for nm,lo,hi in BANDS}; cLR = {nm:0.0 for nm,lo,hi in BANDS}
    tot_LL = tot_RR = tot_LR = 0.0
    env, flux = [], []; prev = None; frames = 0
    for st in range(0, n, CHUNK):
        buf = x[:, st:st+CHUNK]
        if buf.shape[1] < NFFT: break
        k = (buf.shape[1]-NFFT)//HOP + 1
        if k <= 0: continue
        idx = np.arange(k)[:,None]*HOP + np.arange(NFFT)
        F = buf[:, idx].astype(np.float64)
        env.extend(np.sqrt(np.mean(F**2, axis=(0,2))).tolist())
        L = np.fft.rfft(F[0]*win, axis=-1); R = np.fft.rfft(F[1]*win, axis=-1)
        M = 0.5*(L+R); S = 0.5*(L-R); Pm = np.abs(M)**2
        acc_pow += Pm.sum(axis=0); acc_mag += np.abs(M).sum(axis=0)
        mag = np.abs(M)
        if prev is None:
            fl = np.zeros(mag.shape[0]); fl[1:] = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
        else:
            m2 = np.concatenate([prev[None,:], mag], axis=0)
            fl = np.maximum(0.0, np.diff(m2, axis=0)).sum(axis=1)
        flux.extend(fl.tolist()); prev = mag[-1]
        for nm, mk in masks:
            if not np.any(mk): continue
            bp = Pm[:, mk].sum(axis=1)
            bsum[nm] += float(bp.sum()); bmax[nm] = max(bmax[nm], float(bp.max()))
            ssum[nm] += float(np.sum(np.abs(S[:, mk])**2))
            cL = L[:, mk]; cR = R[:, mk]
            cLL[nm] += float(np.sum(np.abs(cL)**2)); cRR[nm] += float(np.sum(np.abs(cR)**2))
            cLR[nm] += float(np.sum(np.real(cL*np.conj(cR))))
        tot_LL += float(np.sum(np.abs(L)**2)); tot_RR += float(np.sum(np.abs(R)**2))
        tot_LR += float(np.sum(np.real(L*np.conj(R))))
        frames += k

    e = 20.0*np.log10(np.maximum(np.array(env), 1e-9))
    p95, p10 = float(np.percentile(e,95)), float(np.percentile(e,10))
    o["Crest dB"] = sp_db - 20.0*np.log10(max(float(np.sqrt(np.mean(x.astype(np.float64)**2))),1e-12))
    o["Env floor dB"] = p10 - p95
    o["Sustain dB"] = float(np.median(e)) - p95
    o["Density %"] = 100.0*float(np.mean(e > p95-6.0))
    hop_s = HOP/float(sr); w1 = max(1,int(round(1.0/hop_s)))
    if len(e) > w1:
        kk = len(e)//w1; mm = e[:kk*w1].reshape(kk,w1).mean(axis=1)
        o["ST spread dB"] = float(np.percentile(mm,90)-np.percentile(mm,10))
    else: o["ST spread dB"] = 0.0
    w3 = max(1,int(round(3.0/hop_s)))
    if len(e) > w3:
        kk = len(e)//w3; mm = e[:kk*w3].reshape(kk,w3)
        dr = mm.max(axis=1)-mm.mean(axis=1)
        top = np.sort(dr)[::-1][:max(1,int(0.2*len(dr)))]
        o["DR14 proxy"] = float(np.mean(top))
    else: o["DR14 proxy"] = 0.0
    g = max(1, len(e)//8)
    ss = [e[i*g:(i+1)*g].mean() for i in range(8) if len(e[i*g:(i+1)*g])]
    o["Section spread dB"] = float(max(ss)-min(ss)) if ss else 0.0
    o["Noise floor dBFS"] = float(np.percentile(e,1))

    fl = np.array(flux); pk = np.zeros(len(fl), bool); onsets = 0
    if len(fl) > 3:
        thr = float(fl.mean() + fl.std())
        pk[1:-1] = (fl[1:-1] > fl[:-2]) & (fl[1:-1] >= fl[2:]) & (fl[1:-1] > thr)
        onsets = int(pk.sum())
    o["Onsets/s"] = onsets/dur if dur > 0 else 0.0
    op = np.where(pk)[0]; ii = op[(op+4) < len(e)]
    o["Decay370 dB"] = float(np.mean(e[ii]-e[ii+4])) if len(ii) else 0.0

    tot = acc_pow.sum()
    for nm, mk in masks:
        if not np.any(mk): o["band:"+nm]=0.0; o["side:"+nm]=-99.0; o["crest:"+nm]=0.0; continue
        o["band:"+nm] = lg(bsum[nm]/max(tot,1e-20))
        o["side:"+nm] = lg(ssum[nm]/max(bsum[nm],1e-20))
        o["crest:"+nm] = lg(bmax[nm]/max(bsum[nm]/max(frames,1),1e-20))
    o["Centroid Hz"] = float(np.sum(freq*acc_mag)/max(acc_mag.sum(),1e-20))
    cs = np.cumsum(acc_mag)/max(acc_mag.sum(),1e-20)
    o["Rolloff85 Hz"] = float(freq[min(int(np.searchsorted(cs,0.85)), len(freq)-1)])
    hf = (freq>=10000)&(freq<min(16000,sr/2.0))
    o["HF flatness"] = float(np.exp(np.mean(np.log(acc_mag[hf]+1e-12)))/max(np.mean(acc_mag[hf]),1e-20)) if np.any(hf) else 0.0
    o["Width dB"] = lg(sum(ssum.values())/max(sum(bsum.values()),1e-20))
    o["Corr overall"] = tot_LR/max(np.sqrt(tot_LL*tot_RR),1e-20)
    lL=cLL["sub 20-60"]+cLL["bass 60-120"]; lR=cRR["sub 20-60"]+cRR["bass 60-120"]; lX=cLR["sub 20-60"]+cLR["bass 60-120"]
    o["Corr LF 20-120"] = lX/max(np.sqrt(lL*lR),1e-20)
    ov = 0
    for st in range(0, n, CHUNK):
        seg = x[:, st:st+CHUNK]
        for c in range(2): ov += overs_count(seg[c])
    o["IS overs"] = ov
    return o

ORDER = [("LOUDNESS","LUFS-I","R"),("LOUDNESS","TP dBTP","R"),("LOUDNESS","Peak dBFS","R"),
 ("LOUDNESS","Headroom dB","R"),("LOUDNESS","PLR dB","R"),("LOUDNESS","LRA LU","R"),
 ("DYNAMICS","Crest dB","R"),("DYNAMICS","ST spread dB","P"),("DYNAMICS","Section spread dB","P"),
 ("DYNAMICS","Density %","P"),("DYNAMICS","Env floor dB","P"),("DYNAMICS","Sustain dB","P"),
 ("DYNAMICS","DR14 proxy","P"),("TRANSIENT","Onsets/s","P"),("TRANSIENT","Decay370 dB","P"),
 ("TRANSIENT","crest:sub 20-60","P"),("TRANSIENT","crest:bass 60-120","P"),("TRANSIENT","crest:pres 2-5k","P"),
 ("TONAL","Centroid Hz","R"),("TONAL","Rolloff85 Hz","R"),("TONAL","HF flatness","P")]
ORDER += [("TONAL","band:"+nm,"R") for nm,lo,hi in BANDS]
ORDER += [("STEREO","Width dB","R"),("STEREO","Corr overall","R"),("STEREO","Corr LF 20-120","R")]
ORDER += [("STEREO","side:"+nm,"R") for nm,lo,hi in BANDS]
ORDER += [("ARTIFACTS","IS overs","R"),("ARTIFACTS","Noise floor dBFS","P"),("ARTIFACTS","DC L","R"),("ARTIFACTS","DC R","R")]

def fmt(v):
    if v is None or not np.isfinite(v): return "n/a"
    return f"{v:.2f}" if abs(v) < 10 else f"{v:.0f}"

def main(paths):
    if len(paths) < 2: sys.exit("Usage: python3 measure_all.py YOURS [REF1 REF2 ...]")
    names = [Path(p).stem[:12] for p in paths]
    data = [measure(p) for p in paths]
    print(f"{'metric':<24}" + "".join(f"{n:>13}" for n in names) + f"{'delta':>10}")
    cur = None
    for sect, key, tag in ORDER:
        if sect != cur:
            print(f"\n-- {sect} " + "-"*max(1,40-len(sect)))
            cur = sect
        vals = [d.get(key) for d in data]
        vr = [v for v in vals[1:] if v is not None and np.isfinite(v)]
        rm = float(np.mean(vr)) if vr else None
        dl = (vals[0]-rm) if (vals[0] is not None and rm is not None) else None
        print(f"{key:<22}[{tag}]" + "".join(f"{fmt(v):>13}" for v in vals) + f"{fmt(dl):>10}")

if __name__ == "__main__":
    main(sys.argv[1:])
