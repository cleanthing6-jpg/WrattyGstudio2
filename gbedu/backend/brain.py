"""Gbedu brain - vocal in, song facts out.

Essentia when available (best), librosa + beat_this as fallback.
    python gbedu/backend/brain.py song.mp3
"""
from __future__ import annotations
import json, os, sys, tempfile

NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
ENH = {"DB":"C#","EB":"D#","GB":"F#","AB":"G#","BB":"A#","CB":"B","FB":"E","E#":"F","B#":"C"}
MAJ = [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]
MIN = [6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17]

ANALYZE_SECONDS = int(os.environ.get("GBEDU_ANALYZE_SECONDS", "90"))

def norm_key(k):
    return ENH.get((k or "").strip().upper(), (k or "").strip().upper())

def fold_bpm(bpm):
    while bpm and bpm > 150: bpm /= 2
    while bpm and bpm < 70:  bpm *= 2
    return bpm

def fold_ratio(r):
    if not r or r <= 0: return 1.0
    while r < 0.7: r *= 2
    while r > 1.4: r /= 2
    return r

def note_steps(target, got):
    if target not in NOTES or got not in NOTES: return 0
    return ((NOTES.index(target) - NOTES.index(got) + 6) % 12) - 6

def bpm_gap(t, b):
    if not b: return 99.0
    return abs(t - b * fold_ratio(t / b))

def distance(spec, beat):
    return (bpm_gap(spec["bpm"], beat.get("bpm", 0)) / 2.0
            + 2.0 * abs(note_steps(spec["key"], beat.get("key", "C")))
            + (0.0 if spec.get("scale") == beat.get("scale") else 3.0))

def fits(spec, beat, bpm_tol=2.0):
    return (bpm_gap(spec["bpm"], beat.get("bpm", 0)) <= bpm_tol
            and note_steps(spec["key"], beat.get("key", "C")) == 0
            and spec.get("scale") == beat.get("scale"))

def _window_spans(dur, n=4, win=30.0):
    if dur <= win or n <= 1:
        return [(0.0, min(dur, win))]
    first, last = dur * 0.1, dur * 0.9 - win
    if last <= first:
        return [(0.0, min(dur, win))]
    step = (last - first) / (n - 1)
    return [(max(0.0, min(first + i * step, dur - win)), win) for i in range(n)]

def _agree(a, b, tol=0.04):
    m = max(a, b)
    return min(abs(a-b), abs(a*2-b), abs(a-b*2), abs(a/2-b), abs(a-b/2)) <= tol * m

def _vote_bpm(vals):
    vals = [v for v in vals if v and 30 < v < 250]
    if not vals:
        return 0.0
    best, score = vals[0], -1
    for v in vals:
        s = sum(1 for w in vals if _agree(v, w))
        if s > score:
            best, score = v, s
    return fold_bpm(best)

def _one_window(y, sr):
    try:
        import essentia.standard as es
        bpm, _, _, _, _ = es.RhythmExtractor2013(method="multifeature")(y.astype("float32"))
        k, scale, strength = es.KeyExtractor()(y.astype("float32"))
        return {"bpm": float(bpm), "key": norm_key(str(k)),
                "scale": str(scale).strip().lower(), "confidence": float(strength),
                "source": "essentia"}
    except Exception as e:
        print("essentia window skipped:", type(e).__name__, str(e)[:100], flush=True)

    import numpy as np, librosa
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    try:
        bpm = float(np.median(librosa.feature.tempo(onset_envelope=env, sr=sr, aggregate=None)))
    except Exception:
        bpm = 0.0
    chroma = librosa.feature.chroma_cens(y=y, sr=sr).mean(axis=1)
    pc = chroma
    try:
        f0, _, vp = librosa.pyin(y, fmin=librosa.note_to_hz("E2"), fmax=librosa.note_to_hz("C6"), sr=sr)
        ok = ~np.isnan(f0)
        if ok.sum() > 20:
            h = np.zeros(12)
            for m, p in zip(np.round(librosa.hz_to_midi(f0[ok])).astype(int), np.nan_to_num(vp[ok], nan=0.0)):
                h[m % 12] += max(float(p), 0.05)
            if h.sum() > 1e-6:
                pc = h / h.sum()
    except Exception:
        pass

    def corr(p, q):
        p, q = np.asarray(p, float) - np.mean(p), np.asarray(q, float) - np.mean(q)
        return float(np.dot(p, q) / ((np.linalg.norm(p) * np.linalg.norm(q)) + 1e-9))

    ranked = sorted(((0.5 * corr(chroma, np.roll(prof, i)) + 0.5 * corr(pc, np.roll(prof, i)), NOTES[i], mode)
                     for i in range(12)
                     for mode, prof in (("major", MAJ), ("minor", MIN))), reverse=True)
    return {"bpm": bpm, "key": ranked[0][1], "scale": ranked[0][2],
            "confidence": float(ranked[0][0]), "source": "librosa"}

def analyze(path, windows=4, win=30.0):
    """Read several places in the song, then vote. Steadier than one window."""
    import librosa
    import numpy as np
    dur = float(librosa.get_duration(path=path))
    reads = []
    for off, w in _window_spans(dur, windows, win):
        try:
            y, sr = librosa.load(path, sr=44100, mono=True, offset=off, duration=w)
            if len(y) < sr:
                continue
            r = _one_window(np.ascontiguousarray(y, dtype="float32"), sr)
            r["offset"] = round(off, 1)
            reads.append(r)
            print("READ", r, flush=True)
        except Exception as e:
            print("window failed", round(off, 1), type(e).__name__, str(e)[:120], flush=True)
    if not reads:
        raise RuntimeError("could not read any window of " + str(path))

    counts = {}
    for r in reads:
        counts[(r["key"], r["scale"])] = counts.get((r["key"], r["scale"]), 0) + 1
    best = max(counts.items(), key=lambda kv: (kv[1], max(r["confidence"] for r in reads
               if (r["key"], r["scale"]) == kv[0])))[0]
    conf = max(r["confidence"] for r in reads if (r["key"], r["scale"]) == best)
    return {"bpm": round(_vote_bpm([r["bpm"] for r in reads]), 2), "key": best[0], "scale": best[1],
            "confidence": round(float(conf), 3), "source": reads[0]["source"], "windows": len(reads),
            "reads": [{"offset": r["offset"], "bpm": round(r["bpm"], 2),
                       "key": f'{r["key"]} {r["scale"]}'} for r in reads]}

def analyze_bytes(data):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(data); p = f.name
    try: return analyze(p)
    finally:
        try: os.unlink(p)
        except OSError: pass

def build_prompt(spec, genre="afrobeats"):
    mood = "dark minor chords" if spec.get("scale") == "minor" else "bright major chords"
    return (f"professional nigerian {genre} instrumental, no vocals, log drum, shaker, "
            f"talking drum, warm sub bass, clean guitar, groovy, punchy kick, "
            f"{spec['key']} {spec['scale']}, {int(round(spec['bpm']))} bpm, {mood}")

if __name__ == "__main__":
    print(json.dumps(analyze(sys.argv[1]), indent=2))
