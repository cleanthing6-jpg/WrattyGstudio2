import json, os, shutil, tempfile, uuid, wave
from http.server import BaseHTTPRequestHandler

import numpy as np
import requests

BLOB_HOST = "https://blob.vercel-storage.com"
MAX_BYTES = 40 * 1024 * 1024
MAX_SECONDS = 480.0
ALLOWED = (".wav", ".wave")


def read_wav(path):
    with wave.open(path, "rb") as w:
        ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sw == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 127.0
    elif sw == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError("Unsupported WAV: %d-bit" % (sw * 8))
    return a.reshape(-1, ch).T, sr


def write_wav(path, a, sr):
    a = np.clip(a, -1.0, 1.0)
    d = (a.T * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(a.shape[0]); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(d.tobytes())


def fft_convolve(x, ir):
    n_ir = len(ir); blk = 1 << 15; n_fft = 1
    while n_fft < blk + n_ir:
        n_fft <<= 1
    H = np.fft.rfft(ir, n_fft)
    out = np.zeros(len(x) + n_fft, dtype=np.float32)
    buf = np.zeros(n_fft, dtype=np.float32)
    pos = 0
    while pos < len(x):
        chunk = x[pos:pos + blk].astype(np.float32)
        buf[:blk] = 0.0
        buf[:len(chunk)] = chunk
        out[pos:pos + n_fft] += np.fft.irfft(np.fft.rfft(buf) * H, n_fft)
        pos += blk
    return out[:len(x)]


def biquad_ir(b0, b1, b2, a1, a2, n=4096):
    ir = np.zeros(n, dtype=np.float32)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(n):
        x0 = 1.0 if i == 0 else 0.0
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x0; y2, y1 = y1, y0
        ir[i] = y0
    return ir


def coef_hp(f0, sr, q=0.707):
    w = 2 * np.pi * f0 / sr; c = np.cos(w); s = np.sin(w); al = s / (2 * q)
    b0, b1, b2 = (1 + c) / 2, -(1 + c), (1 + c) / 2
    a0, a1, a2 = 1 + al, -2 * c, 1 - al
    return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0]


def coef_peak(f0, sr, gain_db, q=1.0):
    A = 10 ** (gain_db / 40.0)
    w = 2 * np.pi * f0 / sr; c = np.cos(w); s = np.sin(w); al = s / (2 * q)
    b0, b1, b2 = 1 + al * A, -2 * c, 1 - al * A
    a0, a1, a2 = 1 + al / A, -2 * c, 1 - al / A
    return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0]


def eq(x, sr, stages):
    for kind, f0, g, q in stages:
        co = coef_hp(f0, sr, q) if kind == "hp" else coef_peak(f0, sr, g, q)
        x = fft_convolve(x, biquad_ir(*co))
    return x


def compress(x, sr, thr_db=-18.0, ratio=3.0, tau_ms=60.0, makeup_db=0.0, knee_db=6.0):
    tau = max(1e-4, tau_ms / 1000.0)
    n = max(8, int(tau * sr * 4))
    t = np.arange(n) / sr
    k = np.exp(-t / tau); k /= k.sum()
    env = fft_convolve(np.abs(x), k.astype(np.float32)).astype(np.float32)
    over = 20.0 * np.log10(env + 1e-9) - thr_db
    half = knee_db / 2.0
    if knee_db > 0:
        g_db = np.where(over <= -half, 0.0,
               np.where(over >= half, -over * (1.0 - 1.0 / ratio),
                        -((over + half) ** 2) / (4.0 * half) * (1.0 - 1.0 / ratio)))
    else:
        g_db = -np.maximum(over, 0.0) * (1.0 - 1.0 / ratio)
    return x * (10.0 ** ((g_db + makeup_db) / 20.0)).astype(np.float32)


def saturate(x, amount=0.15):
    return ((1.0 - amount) * x + amount * np.tanh(2.0 * x) / np.tanh(2.0)).astype(np.float32)


def delay(x, sr, time_s, feedback=0.2, mix=0.15, repeats=4):
    d = max(1, int(time_s * sr))
    wet = np.zeros_like(x); g = 1.0
    for k in range(repeats):
        dk = d * (k + 1)
        if dk >= len(x):
            break
        tap = np.zeros_like(x)
        tap[dk:] = x[:-dk] * g
        if k:
            tap = fft_convolve(tap, np.array([0.5, 0.5], dtype=np.float32))
        wet += tap; g *= feedback
    return x * (1.0 - mix) + wet * mix


def make_ir(sr, decay_s=1.4, predelay_ms=12.0, seed=1, damp=0.55):
    n = max(64, int(decay_s * sr))
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    ir = (rng.standard_normal(n) * np.exp(-6.9 * t / decay_s)).astype(np.float32)
    wl = max(3, int(damp * sr / 4000.0))
    ir = fft_convolve(ir, np.ones(wl, dtype=np.float32) / wl)
    pre = int(predelay_ms * sr / 1000.0)
    out = np.zeros(len(ir) + pre, dtype=np.float32)
    out[pre:] = ir
    out *= 3.0 / (np.sqrt(np.sum(out ** 2)) + 1e-9)
    return out


def reverb(x, sr, mix=0.12, decay_s=1.4, seed=1):
    wet = fft_convolve(x, make_ir(sr, decay_s, 12.0, seed))
    return x * (1.0 - mix) + wet * mix


def limit(x, ceiling=0.89):
    p = float(np.max(np.abs(x)))
    return (x * (ceiling / p) if p > ceiling else x).astype(np.float32)


def chain(x, sr, bpm, preset, chan):
    d1, d2 = 45.0 / bpm, 30.0 / bpm          # dotted 1/8, 1/8
    if preset == "backing":
        x = eq(x, sr, [("hp", 120, 0, 0.707), ("peak", 2800, 1.0, 1.0)])
        x = compress(x, sr, -20, 2.5, 70, 2.0)
        x = saturate(x, 0.08)
        x = delay(x, sr, d1, 0.18, 0.12)
        x = reverb(x, sr, 0.16, 1.3, 11 + chan)
        return x * (10 ** (-6.0 / 20))
    if preset == "adlib":
        x = eq(x, sr, [("hp", 100, 0, 0.707), ("peak", 3200, 2.0, 1.0)])
        x = compress(x, sr, -18, 3.0, 50, 2.5)
        x = saturate(x, 0.20)
        x = delay(x, sr, d2, 0.28, 0.22)
        x = reverb(x, sr, 0.20, 1.6, 21 + chan)
        return x * (10 ** (-4.0 / 20))
    x = eq(x, sr, [("hp", 80, 0, 0.707), ("peak", 3000, 2.5, 1.0), ("peak", 250, 1.5, 0.9)])
    x = compress(x, sr, -18, 3.0, 60, 2.0)
    x = saturate(x, 0.15)
    x = delay(x, sr, d1, 0.22, 0.15)
    x = delay(x, sr, d2, 0.12, 0.10)
    x = reverb(x, sr, 0.12, 1.4, 31 + chan)
    return x * (10 ** (-3.0 / 20))


class handler(BaseHTTPRequestHandler):
    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        secret = os.environ.get("FX_INTERNAL_SECRET", "")
        if not secret or self.headers.get("authorization") != "Bearer " + secret:
            return self._json(401, {"error": "unauthorized"})
        try:
            n = int(self.headers.get("content-length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json(400, {"error": "bad json"})

        url = str(data.get("url") or "").strip()
        if not url.startswith("https://"):
            return self._json(400, {"error": "url required"})
        if not url.split("?")[0].lower().endswith(ALLOWED):
            return self._json(400, {"error": "send a WAV (the app converts stems to WAV)"})

        try:
            bpm = min(max(float(data.get("bpm") or 100), 40.0), 220.0)
        except Exception:
            bpm = 100.0
        preset = str(data.get("preset") or "lead").lower()

        token = os.environ.get("BLOB_READ_WRITE_TOKEN")
        if not token:
            return self._json(500, {"error": "BLOB_READ_WRITE_TOKEN missing"})

        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "in.wav"); out = os.path.join(tmp, "out.wav")
        try:
            with requests.get(url, stream=True, timeout=60) as r:
                r.raise_for_status(); total = 0
                with open(src, "wb") as fh:
                    for chunk in r.iter_content(1 << 16):
                        total += len(chunk)
                        if total > MAX_BYTES:
                            return self._json(413, {"error": "source too large"})
                        fh.write(chunk)

            a, sr = read_wav(src)
            if len(a[0]) / sr > MAX_SECONDS:
                return self._json(413, {"error": "audio too long"})

            for c in range(a.shape[0]):
                a[c] = limit(chain(a[c].astype(np.float32), sr, bpm, preset, c))

            write_wav(out, a, sr)

            name = "fx/%s-%s.wav" % (uuid.uuid4().hex, preset)
            with open(out, "rb") as fh:
                blob = requests.put(
                    BLOB_HOST + "/" + name,
                    headers={"authorization": "Bearer " + token, "x-api-version": "7",
                             "x-content-type": "audio/wav", "x-add-random-suffix": "0",
                             "Content-Type": "audio/wav"},
                    data=fh, timeout=180,
                )
            if blob.status_code >= 300:
                return self._json(502, {"error": "blob upload failed", "detail": blob.text[:300]})

            return self._json(200, {"url": blob.json().get("url", ""), "bpm": bpm,
                                    "preset": preset, "seconds": round(len(a[0]) / sr, 2)})
        except Exception as e:
            return self._json(500, {"error": str(e)[:300]})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
