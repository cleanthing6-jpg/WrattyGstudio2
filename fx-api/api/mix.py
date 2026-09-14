"""wratty-fx mixer: sums stems, glue bus, LUFS master. Replaces RoEx."""
import json, os, shutil, tempfile, threading, uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import requests
from pedalboard import Pedalboard, HighpassFilter, PeakFilter, Compressor, Limiter
from pedalboard.io import AudioFile

try:
    import pyloudnorm as pyln
except Exception:
    pyln = None

BLOB = "https://blob.vercel-storage.com"
TARGET = {"LOW": -16.0, "MEDIUM": -14.0, "HIGH": -11.0}
JOBS, LK = {}, threading.Lock()

BUS = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                  PeakFilter(cutoff_frequency_hz=250, gain_db=1.0, q=0.9),
                  PeakFilter(cutoff_frequency_hz=3000, gain_db=1.5, q=1.0),
                  Compressor(threshold_db=-16, ratio=1.8, attack_ms=25, release_ms=150)])
LIM = Limiter(threshold_db=-1.0, release_ms=100)


def rmsdb(x):
    m = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    return 20.0 * np.log10(m + 1e-12)


def peakdb(x):
    return 20.0 * np.log10(float(np.max(np.abs(x))) + 1e-12)


def lufs(x, sr):
    if pyln is None or x.shape[1] < int(sr * 0.4):
        return None
    try:
        v = float(pyln.Meter(sr).integrated_loudness(x.T.astype(np.float64)))
        return v if np.isfinite(v) else None
    except Exception:
        return None


def load(p):
    with AudioFile(p) as f:
        return f.read(f.frames), int(f.samplerate)


def save16(p, a, sr):
    a = np.clip(a, -1.0, 1.0).astype(np.float32)
    d = np.random.uniform(-1.0, 1.0, a.shape).astype(np.float32) / 32768.0
    with AudioFile(p, "w", sr, a.shape[0]) as f:
        try:
            f.bit_depth = 16
        except Exception:
            pass
        f.write(np.clip(a + d, -1.0, 1.0).astype(np.float32))


def to_sr(a, si, so):
    if si == so:
        return a
    n = int(round(a.shape[1] * so / float(si)))
    x = np.linspace(0.0, a.shape[1] - 1.0, n)
    i = np.arange(a.shape[1], dtype=np.float64)
    return np.stack([np.interp(x, i, c.astype(np.float64)).astype(np.float32) for c in a])


def grab(u, dst):
    with requests.get(u, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dst, "wb") as fh:
            for c in r.iter_content(1 << 16):
                fh.write(c)


def put(p, name):
    t = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not t:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN missing")
    with open(p, "rb") as fh:
        r = requests.put(BLOB + "/" + name, data=fh, timeout=600,
                         headers={"authorization": "Bearer " + t,
                                  "x-api-version": "7", "x-content-type": "audio/wav",
                                  "x-add-random-suffix": "1", "Content-Type": "audio/wav"})
    if r.status_code >= 300:
        raise RuntimeError("blob " + r.text[:150])
    return r.json().get("url", "")


def setjob(jid, status, url=""):
    with LK:
        j = JOBS.get(jid) or {}
        j["status"] = status
        if url:
            j["url"] = url
        JOBS[jid] = j


def do_mix(stems, loud, jid):
    tmp = tempfile.mkdtemp()
    try:
        sr = None
        m = np.zeros((2, 0), dtype=np.float32)
        for i, s in enumerate(stems):
            setjob(jid, "stem %d of %d" % (i + 1, len(stems)))
            p = os.path.join(tmp, "%d.wav" % i)
            grab(s["url"], p)
            a, s0 = load(p)
            os.remove(p)
            if len(a[0]) / float(s0) > 480:
                raise ValueError("stem longer than 8 minutes")
            if sr is None:
                sr = s0
            elif s0 != sr:
                a = to_sr(a, s0, sr)
            if a.shape[0] == 1:
                a = np.repeat(a, 2, axis=0)
            a = np.ascontiguousarray(a[:2].astype(np.float32))
            need = a.shape[1]
            if m.shape[1] < need:
                g = np.zeros((2, need), dtype=np.float32)
                g[:, :m.shape[1]] = m
                m = g
            m += a
            del a
        n = m.shape[1]
        m = m * (10.0 ** ((-6.0 - peakdb(m)) / 20.0))
        setjob(jid, "glue bus")
        m = BUS(m, sr).astype(np.float32)
        want = str(loud or "MEDIUM").upper()
        cur = lufs(m, sr)
        tgt = TARGET.get(want, -14.0)
        if cur is None:
            m = m * (10.0 ** ((tgt + 2.5 - rmsdb(m)) / 20.0))
        else:
            m = m * (10.0 ** ((tgt - cur) / 20.0))
        m = LIM(m, sr).astype(np.float32)
        out = os.path.join(tmp, "mix.wav")
        save16(out, m, sr)
        url = put(out, "fx/%s-mix-%s.wav" % (uuid.uuid4().hex, want.lower()))
        got = lufs(m, sr)
        return {"url": url, "seconds": round(n / float(sr), 2),
                "peak_dbfs": round(peakdb(m), 2),
                "lufs": (None if got is None else round(got, 2)),
                "sample_rate": sr}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def worker(jid, stems, loud):
    try:
        setjob(jid, "running")
        res = do_mix(stems, loud, jid)
        with LK:
            JOBS[jid] = {"status": "done", "url": res["url"], "result": res}
    except Exception as e:
        with LK:
            JOBS[jid] = {"status": "failed", "error": str(e)[:300]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def json_out(self, code, payload):
        b = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass

    def do_GET(self):
        jid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
        if not jid:
            return self.json_out(200, {"ok": True, "lufs": pyln is not None})
        with LK:
            j = dict(JOBS.get(jid) or {"status": "none"})
        return self.json_out(200, j)

    def do_POST(self):
        sec = os.environ.get("FX_INTERNAL_SECRET", "")
        if not sec or self.headers.get("authorization") != "Bearer " + sec:
            return self.json_out(401, {"error": "unauthorized"})
        try:
            n = int(self.headers.get("content-length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self.json_out(400, {"error": "bad json"})
        stems = data.get("stems")
        if not isinstance(stems, list) or not stems:
            return self.json_out(400, {"error": "stems[] required"})
        if len(stems) > 8:
            return self.json_out(400, {"error": "max 8 stems"})
        for s in stems:
            if not str(s.get("url") or "").startswith("https://"):
                return self.json_out(400, {"error": "each stem needs an https url"})
        with LK:
            busy = any(v.get("status") in ("queued", "running") for v in JOBS.values())
        if busy:
            return self.json_out(429, {"error": "engine busy - try again in a minute"})
        jid = uuid.uuid4().hex
        with LK:
            JOBS[jid] = {"status": "queued"}
        t = threading.Thread(target=worker, args=(jid, stems, str(data.get("loudness") or "MEDIUM")))
        t.daemon = True
        t.start()
        return self.json_out(202, {"job": jid})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print("wratty-fx mixer on 0.0.0.0:%d" % port, flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
