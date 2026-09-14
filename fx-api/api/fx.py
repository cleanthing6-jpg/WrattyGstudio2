import json, os, shutil, tempfile, uuid, wave
from http.server import BaseHTTPRequestHandler

import numpy as np
import requests

BLOB_HOST = "https://blob.vercel-storage.com"
MAX_BYTES = 40 * 1024 * 1024
MAX_SECONDS = 480.0
ALLOWED = (".wav", ".wave")


ENGINE = "stemfx-pb-1.0"

from pedalboard import (Pedalboard, HighpassFilter, LowShelfFilter, HighShelfFilter,
                        PeakFilter, Compressor, Limiter, Distortion, Reverb, Delay)
from pedalboard.io import AudioFile


def read_wav(path):
    with AudioFile(path) as f:
        sr = f.samplerate
        a = f.read(f.frames)
    return a.astype(np.float32), int(sr)


def write_wav(path, a, sr, bit_depth=24):
    ch = a.shape[0]
    with AudioFile(path, "w", int(sr), ch, bit_depth=bit_depth) as o:
        o.write(np.clip(a, -1.0, 1.0))


def board_for(preset, bpm):
    d1 = 45.0 / bpm
    d2 = 30.0 / bpm
    p = (preset or "lead").lower()
    if p == "backing":
        return 10 ** (-6.0 / 20), Pedalboard([
            HighpassFilter(cutoff_frequency_hz=120),
            PeakFilter(cutoff_frequency_hz=2800, gain_db=1.0, q=1.0),
            Compressor(threshold_db=-20, ratio=2.5, attack_ms=15, release_ms=70),
            Distortion(drive_db=1.0),
            Delay(delay_seconds=d1, feedback=0.18, mix=0.12),
            Reverb(room_size=0.45, damping=0.50, wet_level=0.16, dry_level=0.85, width=1.0),
            Limiter(threshold_db=-1.5, release_ms=80),
        ])
    if p == "adlib":
        return 10 ** (-4.0 / 20), Pedalboard([
            HighpassFilter(cutoff_frequency_hz=100),
            PeakFilter(cutoff_frequency_hz=3200, gain_db=2.0, q=1.0),
            Compressor(threshold_db=-18, ratio=3.0, attack_ms=12, release_ms=50),
            Distortion(drive_db=3.0),
            Delay(delay_seconds=d2, feedback=0.28, mix=0.22),
            Reverb(room_size=0.50, damping=0.45, wet_level=0.20, dry_level=0.82, width=1.0),
            Limiter(threshold_db=-1.5, release_ms=80),
        ])
    if p == "bus" or p == "mix":
        return 10 ** (-3.0 / 20), Pedalboard([
            HighpassFilter(cutoff_frequency_hz=85),
            PeakFilter(cutoff_frequency_hz=250, gain_db=1.5, q=0.9),
            PeakFilter(cutoff_frequency_hz=3000, gain_db=2.5, q=1.0),
            Compressor(threshold_db=-18, ratio=3.0, attack_ms=15, release_ms=60),
            Distortion(drive_db=2.0),
            Limiter(threshold_db=-1.0, release_ms=80),
        ])
    if p == "bus_space":
        return 10 ** (-3.0 / 20), Pedalboard([
            HighpassFilter(cutoff_frequency_hz=85),
            PeakFilter(cutoff_frequency_hz=250, gain_db=1.5, q=0.9),
            PeakFilter(cutoff_frequency_hz=3000, gain_db=2.5, q=1.0),
            Compressor(threshold_db=-18, ratio=3.0, attack_ms=15, release_ms=60),
            Distortion(drive_db=2.0),
            Reverb(room_size=0.30, damping=0.45, wet_level=0.06, dry_level=0.94, width=0.95),
            Limiter(threshold_db=-1.0, release_ms=80),
        ])
    if p == "beat":
        return 10 ** (-1.0 / 20), Pedalboard([
            LowShelfFilter(cutoff_frequency_hz=70, gain_db=2.0),
            HighShelfFilter(cutoff_frequency_hz=9000, gain_db=1.0),
            Compressor(threshold_db=-12, ratio=2.0, attack_ms=25, release_ms=200),
            Limiter(threshold_db=-1.0, release_ms=100),
        ])
    return 10 ** (-3.0 / 20), Pedalboard([
        HighpassFilter(cutoff_frequency_hz=85),
        PeakFilter(cutoff_frequency_hz=250, gain_db=1.5, q=0.9),
        PeakFilter(cutoff_frequency_hz=3000, gain_db=2.5, q=1.0),
        Compressor(threshold_db=-18, ratio=3.0, attack_ms=15, release_ms=60),
        Distortion(drive_db=2.0),
        Delay(delay_seconds=d1, feedback=0.22, mix=0.15),
        Delay(delay_seconds=d2, feedback=0.12, mix=0.10),
        Reverb(room_size=0.30, damping=0.45, wet_level=0.12, dry_level=0.88, width=0.95),
        Limiter(threshold_db=-1.0, release_ms=80),
    ])


def process_all(a, sr, bpm, preset, ceiling=0.89):
    g, board = board_for(preset, bpm)
    out = board(a.astype(np.float32), float(sr)) * g
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > ceiling:
        out = out * (ceiling / peak)
    return np.clip(out, -1.0, 1.0).astype(np.float32)


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
        preset = str(data.get("preset") or "bus").lower()

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

            a = process_all(a, sr, bpm, preset)

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

# --- run as a standalone HTTP server (Render / Koyeb) ---
if __name__ == "__main__":
    import os as _os
    from http.server import HTTPServer as _HTTPServer, BaseHTTPRequestHandler as _Base
    _Handler = next(
        _v for _v in list(globals().values())
        if isinstance(_v, type) and issubclass(_v, _Base) and _v is not _Base
    )
    if not hasattr(_Handler, "do_GET"):
        def _do_get(self):
            self._json(200, {"ok": True})
        _Handler.do_GET = _do_get
    _port = int(_os.environ.get("PORT", "8080"))
    print("fx server listening on 0.0.0.0:%d" % _port, flush=True)
    _HTTPServer(("0.0.0.0", _port), _Handler).serve_forever()
