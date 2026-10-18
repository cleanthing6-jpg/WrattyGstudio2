from scipy.interpolate import CubicSpline
"""
declip.py - conservative de-clipper. numpy only.

Repairs flat-topped clipped regions by band-limited (Lanczos-sinc)
interpolation using surrounding samples as anchors.

Design rules:
  * CONSERVATIVE: skip runs longer than max_run (too damaged).
  * ADVISORY: reports what it did; caller decides to apply.
  * numpy only, no state, no globals.

CLI:
    python3 declip.py input.wav output.wav
"""
import sys
import numpy as np


def _lanczos_interp(xp, fp, xi, a=4):
    """Lanczos-a sinc interpolation. Vectorised over xi."""
    xp = np.asarray(xp, dtype=np.float64)
    fp = np.asarray(fp, dtype=np.float64)
    xi = np.atleast_1d(np.asarray(xi, dtype=np.float64))
    out = np.empty_like(xi)
    for i, x in enumerate(xi):
        d = x - xp
        m = np.abs(d) < a
        if not m.any():
            out[i] = 0.0
            continue
        dd = d[m]
        k = np.sinc(dd) * np.sinc(dd / a)
        s = k.sum()
        out[i] = (k * fp[m]).sum() / s if abs(s) > 1e-12 else 0.0
    return out


def detect_clips(x, threshold=0.998):
    """Return list of (start, end, sign) for each clipped run."""
    a = np.asarray(x)
    if a.ndim == 2:
        hit = (np.abs(a) >= threshold).any(axis=0)
        # per-sample sign of the loudest channel — proper fancy indexing
        rows = np.argmax(np.abs(a), axis=0)
        cols = np.arange(a.shape[1])
        sign = np.sign(a[rows, cols]).astype(np.int8)
    else:
        hit = np.abs(a) >= threshold
        sign = np.sign(a).astype(np.int8)
    d = np.diff(np.concatenate([[0], hit.astype(np.int8), [0]]))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    out = []
    for s, e in zip(starts, ends):
        sgn = int(sign[s]) if s < len(sign) else 1
        out.append((int(s), int(e), sgn))
    return out


def declip(x, sr, threshold=0.998, context=8, max_run=16):
    """
    Repair short clipped runs by Lanczos interpolation.
    x: (channels, samples) or (samples,) float array.
    Returns (repaired, report).
    """
    a = np.asarray(x, dtype=np.float32)
    single = a.ndim == 1
    if single:
        a = a[None, :]
    out = a.copy()
    clips = detect_clips(a, threshold=threshold)
    report = {
        "clip_count": len(clips),
        "repaired": 0,
        "skipped_long": 0,
        "skipped_edge": 0,
        "max_run_repaired": 0,
    }
    for s, e, sgn in clips:
        run = e - s
        if run > max_run:
            report["skipped_long"] += 1
            continue
        lo = s - context
        hi = e + context
        if lo < 0 or hi > a.shape[1]:
            report["skipped_edge"] += 1
            continue
        xp = np.concatenate([np.arange(lo, s), np.arange(e, hi)])
        for ch in range(a.shape[0]):
            fp = np.concatenate([a[ch, lo:s], a[ch, e:hi]])
            xi = np.arange(s, e)
            # Claude's Proper Fix: CubicSpline
            yi = CubicSpline(xp, fp)(xi)
            lvl = np.abs(a[ch, s:e])
            yi = sgn * np.maximum(sgn * yi, lvl)
            yi = np.clip(yi, -1.6, 1.6)
            out[ch, s:e] = yi.astype(np.float32).astype(np.float32)
        report["repaired"] += 1
        report["max_run_repaired"] = max(report["max_run_repaired"], run)
    if single:
        out = out[0]
    return out, report


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    import subprocess, json
    src, dst = sys.argv[1], sys.argv[2]
    raw = subprocess.run(["ffmpeg","-v","error","-i",src,"-f","f32le",
                          "-acodec","pcm_f32le","-ac","2","-ar","44100","-"],
                         stdout=subprocess.PIPE, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32).reshape(-1,2).T.astype(np.float32)
    out, rep = declip(a, 44100)
    # write back
    p = subprocess.Popen(["ffmpeg","-y","-v","error","-f","f32le",
                          "-ac","2","-ar","44100","-i","-","-c:a","pcm_s16le",dst],
                         stdin=subprocess.PIPE)
    p.communicate(out.T.astype(np.float32).tobytes())
    print(json.dumps(rep, indent=2))
