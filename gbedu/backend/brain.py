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

def analyze(path):
    try:
        import essentia.standard as es
        a = es.MonoLoader(filename=path, sampleRate=44100)()[:44100*ANALYZE_SECONDS]
        bpm, _, _, _, _ = es.RhythmExtractor2013(method="multifeature")(a)
        k, scale, strength = es.KeyExtractor()(a)
        return {"bpm": round(fold_bpm(float(bpm)), 2), "key": norm_key(str(k)),
                "scale": str(scale).strip().lower(),
                "confidence": round(float(strength), 3), "source": "essentia"}
    except Exception as e:
        print("essentia unavailable:", type(e).__name__, str(e)[:120], flush=True)

    import numpy as np, librosa
    y, sr = librosa.load(path, sr=22050, mono=True, duration=ANALYZE_SECONDS)
    y, _ = librosa.effects.trim(y, top_db=35)
    votes = []
    try:
        from beat_this.inference import File2Beats
        beats, _ = File2Beats(checkpoint_path="final0", device="cuda", dbn=False)(path)
        d = np.diff(np.asarray(beats)); d = d[d > 0.15]
        if len(d) >= 4: votes.append(float(60.0/np.median(d)))
    except Exception as e:
        print("beat_this skipped:", type(e).__name__, flush=True)
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    try: votes.append(float(np.median(librosa.feature.tempo(onset_envelope=env, sr=sr, aggregate=None))))
    except Exception: pass
    try: votes.append(float(np.atleast_1d(librosa.beat.beat_track(onset_envelope=env, sr=sr)[0])[0]))
    except Exception: pass
    votes = [v for v in votes if 30 < v < 250]
    bpm = fold_bpm(float(np.median(votes))) if votes else 0.0

    def corr(p, q):
        p, q = np.asarray(p,float)-np.mean(p), np.asarray(q,float)-np.mean(q)
        return float(np.dot(p,q)/((np.linalg.norm(p)*np.linalg.norm(q))+1e-9))

    chroma = librosa.feature.chroma_cens(y=y, sr=sr).mean(axis=1)
    pc = chroma
    try:
        f0, _, vp = librosa.pyin(y, fmin=librosa.note_to_hz('E2'), fmax=librosa.note_to_hz('C6'), sr=sr)
        ok = ~np.isnan(f0)
        if ok.sum() > 20:
            h = np.zeros(12)
            for m, p in zip(np.round(librosa.hz_to_midi(f0[ok])).astype(int), np.nan_to_num(vp[ok], nan=0.0)):
                h[m % 12] += max(float(p), 0.05)
            if h.sum() > 1e-6: pc = h / h.sum()
    except Exception as e:
        print("pyin skipped:", type(e).__name__, flush=True)
    ranked = sorted(((0.5*corr(chroma, np.roll(prof, i)) + 0.5*corr(pc, np.roll(prof, i)), NOTES[i], mode)
                     for i in range(12) for mode, prof in (("major", MAJ), ("minor", MIN))), reverse=True)
    return {"bpm": round(bpm, 2), "key": ranked[0][1], "scale": ranked[0][2],
            "confidence": round(float(ranked[0][0]), 3), "source": "librosa/beat_this"}

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
