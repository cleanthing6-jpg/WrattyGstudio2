import numpy as np
import scipy.signal
import librosa


def detect_key(beat_audio: np.ndarray, sr: int):
    """Detects root key and scale from a beat track.

    Applies a 250 Hz high-pass filter to strip bass/808 distortion
    before chroma analysis. Returns (key, scale, confidence).
    """
    if len(beat_audio) == 0:
        return "C", "Natural Minor", 0.0

    if beat_audio.ndim > 1:
        beat_audio = np.mean(beat_audio, axis=1)

    nyquist = sr * 0.5
    cutoff = min(250.0 / nyquist, 0.99)
    b, a = scipy.signal.butter(4, cutoff, btype='high')
    filtered_beat = scipy.signal.lfilter(b, a, beat_audio)

    chroma = librosa.feature.chroma_cqt(y=filtered_beat, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)

    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    best_score = -1.0
    best_key = "C"
    best_scale = "Natural Minor"

    for i in range(12):
        rot_major = np.roll(major_profile, i)
        rot_minor = np.roll(minor_profile, i)

        score_maj = np.corrcoef(chroma_mean, rot_major)[0, 1]
        score_min = np.corrcoef(chroma_mean, rot_minor)[0, 1]

        if score_maj > best_score:
            best_score = score_maj
            best_key = note_names[i]
            best_scale = "Major"

        if score_min > best_score:
            best_score = score_min
            best_key = note_names[i]
            best_scale = "Natural Minor"

    confidence = float(max(0.0, min(1.0, (best_score + 1.0) / 2.0)))
    return best_key, best_scale, confidence
