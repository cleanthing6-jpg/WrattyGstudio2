import numpy as np, librosa, json, sys

PITCHES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
MAJOR = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
MINOR = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])

def estimate_key(chroma_mean):
    best, sc = None, -2
    for i in range(12):
        for prof, mode in ((MAJOR, 'major'), (MINOR, 'minor')):
            r = np.corrcoef(chroma_mean, np.roll(prof, i))[0, 1]
            if r > sc:
                sc, best = r, (PITCHES[i], mode)
    return best, sc

def analyze(path):
    y, sr = librosa.load(path, sr=22050, mono=True)
    bpm = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr)[0])[0])
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    (key, mode), conf = estimate_key(chroma)
    return {"bpm": round(bpm), "key": f"{key} {mode}", "key_confidence": round(float(conf), 2)}

if __name__ == "__main__":
    print(json.dumps(analyze(sys.argv[1]), indent=2))
