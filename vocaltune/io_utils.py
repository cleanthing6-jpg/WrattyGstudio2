"""Audio I/O. Uses soundfile if installed, otherwise falls back to ffmpeg (so it runs anywhere)."""
from __future__ import annotations
import subprocess, shutil, json
import numpy as np

def read_audio(path: str, sr: int | None = None):
    try:
        import soundfile as sf
        x, fs = sf.read(path, dtype="float32", always_2d=False)
        if sr and sr != fs:
            from .dsp import resample
            x = np.stack([resample(x[:, c], fs, sr) for c in range(x.shape[1])], 1) if x.ndim == 2 else resample(x, fs, sr)
            fs = sr
        return x, fs
    except Exception:
        pass
    if not shutil.which("ffmpeg"):
        raise RuntimeError("need soundfile or ffmpeg to read audio")
    pr = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                                             "stream=sample_rate,channels", "-of", "json", path]))["streams"][0]
    fs, ch = int(pr["sample_rate"]), int(pr["channels"])
    out_fs = sr or fs
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ar", str(out_fs), "-ac", str(ch), "-"])
    x = np.frombuffer(raw, dtype=np.float32)
    return (x.reshape(-1, ch) if ch > 1 else x), out_fs

def write_audio(path: str, x: np.ndarray, sr: int, bits: int = 24):
    x = np.asarray(x, dtype=np.float32)
    try:
        import soundfile as sf
        sf.write(path, x, sr, subtype={16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}[bits]); return
    except Exception:
        pass
    ch = 1 if x.ndim == 1 else x.shape[1]
    codec = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_f32le"}[bits]
    if path.lower().endswith(".flac"):
        codec = "flac"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", str(ch), "-i", "-",
                          "-c:a", codec, path], stdin=subprocess.PIPE)
    p.communicate(x.tobytes()); assert p.returncode == 0
