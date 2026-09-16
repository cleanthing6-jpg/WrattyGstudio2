"""wratty-fx mixer: sums stems, glue bus, LUFS master. Replaces RoEx."""
import gc, json, os, shutil, tempfile, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import requests
from pedalboard import Pedalboard, HighpassFilter, PeakFilter, Compressor, Limiter
from pedalboard.io import AudioFile

import auto

try:
    import pyloudnorm as pyln
except Exception:
    pyln = None

BLOB = "https://blob.vercel-storage.com"
TARGET = {"LOW": -16.0, "MEDIUM": -14.0, "HIGH": -11.5}
JOBS, LK = {}, threading.Lock()

BUS = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                  PeakFilter(cutoff_frequency_hz=250, gain_db=0.0, q=0.9),
                  PeakFilter(cutoff_frequency_hz=3000, gain_db=0.0, q=1.0),
                  Compressor(threshold_db=-16, ratio=1.8, attack_ms=25, release_ms=150)])
LIM = Limiter(threshold_db=-1.0, release_ms=100)


def rmsdb(x):
    m = float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))
    return 20.0 * np.log10(m + 1e-12)


def peakdb(x):
    return 20.0 * np.log10(float(np.max(np.abs(x))) + 1e-12)


def lufs(x, sr):
    """Real gated K-weighted loudness (BS.1770-4), from the engine."""
    try:
        return auto.integrated_lufs(x, sr)
    except Exception:
        return None


def load(p, max_sec=0.0):
    with AudioFile(p) as f:
        n = int(f.frames)
        if max_sec:
            cap = max(1, int(float(max_sec) * float(f.samplerate)))
            if cap < n:
                n = cap
        return f.read(n), int(f.samplerate)


def save16(p, a, sr):
    a = np.ascontiguousarray(a, dtype=np.float32)
    np.clip(a, -1.0, 1.0, out=a)
    rng = np.random.default_rng()
    flat = a.reshape(-1)
    for i in range(0, flat.size, 1 << 20):
        part = flat[i:i + (1 << 20)]
        noise = rng.random(part.size, dtype=np.float32)
        noise -= rng.random(part.size, dtype=np.float32)
        noise *= np.float32(1.0 / 32768.0)
        part += noise
        np.clip(part, -1.0, 1.0, out=part)
    with AudioFile(p, "w", int(sr), a.shape[0]) as f:
        try:
            f.bit_depth = 16
        except Exception:
            pass
        f.write(a)


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


def rss_mb():
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024.0, 1)
    except Exception:
        pass
    return None


def setjob(jid, status, url=""):
    with LK:
        j = JOBS.get(jid) or {}
        j["status"] = status
        j["rss_mb"] = rss_mb()
        if url:
            j["url"] = url
        JOBS[jid] = j
        _st, _rss = j.get("status"), j.get("rss_mb")
    print("[job %s] %-18s rss=%s MB" % (jid[:8], _st, _rss), flush=True)


def do_mix(stems, loud, jid, max_sec=0):
    tmp = tempfile.mkdtemp()
    try:
        sr = None
        groups = {"beat": [], "lead": [], "adlib": [], "backing": [], "other": []}
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
            if max_sec:
                a = a[:, : max(1, int(max_sec * sr))]
            if a.shape[0] == 1:
                a = np.repeat(a, 2, axis=0)
            a = np.ascontiguousarray(a[:2].astype(np.float32))
            role = s.get("role") or s.get("name") or "stem"
            groups[auto.bucket(role)].append(a)

        setjob(jid, "analysing")
        try:
            mixed, report = auto.mix(groups, sr)
        except Exception as e:
            mixed = auto.plain_sum(groups)
            report = {"mode": "fallback", "error": str(e)[:300]}

        mode = report.get("mode")
        n = mixed.shape[1]
        want = str(loud or "MEDIUM").upper()

        if mode != "passthrough":
            mixed = mixed * (10.0 ** ((-6.0 - peakdb(mixed)) / 20.0))
            setjob(jid, "glue bus")
            _thr = float(np.clip(rmsdb(mixed) - 3.0, -40.0, -6.0))
            mixed = Pedalboard([HighpassFilter(cutoff_frequency_hz=30),
                                Compressor(threshold_db=_thr, ratio=1.5,
                                           attack_ms=30.0, release_ms=130.0)])(mixed, sr).astype(np.float32)
            report["glue_thr_db"] = round(_thr, 2)

        tgt = TARGET.get(want, -14.0)
        cur = lufs(mixed, sr)
        if cur is None:
            mixed = mixed * (10.0 ** ((tgt - rmsdb(mixed)) / 20.0))
        else:
            mixed = mixed * (10.0 ** (max(-9.0, min(9.0, tgt - cur)) / 20.0))

        setjob(jid, "clip+limit")
        if mode not in ("passthrough", "two_track"):
            mixed = auto.clip(mixed, sr)
        mixed, tp, brick = auto.limit(mixed, sr, -1.0)
        for _ in range(4):
            f = lufs(mixed, sr)
            if f is None or abs(tgt - f) < 0.15:
                break
            mixed = mixed * (10.0 ** (max(-9.0, min(9.0, tgt - f)) / 20.0))
            mixed, tp, brick = auto.limit(mixed, sr, -1.0)
        report["true_peak_dbfs"] = round(tp, 2)
        report["limiter"] = "brickwall" if brick else "fallback"

        out = os.path.join(tmp, "mix.wav")
        save16(out, mixed, sr)
        del mixed
        gc.collect()
        rel, rel_sr = load(out)
        url = put(out, "fx/%s-mix-%s.wav" % (uuid.uuid4().hex, want.lower()))
        got = lufs(rel, rel_sr)
        report["loudness"] = want
        return {"url": url, "seconds": round(rel.shape[1] / float(rel_sr), 2),
                "peak_dbfs": round(peakdb(rel), 2),
                "lufs": (None if got is None else round(got, 2)),
                "sample_rate": int(rel_sr),
                "mode": mode, "report": report}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def worker(jid, stems, loud, max_sec=0):
    try:
        setjob(jid, "running")
        res = do_mix(stems, loud, jid, max_sec)
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
        if len(stems) > 12:
            return self.json_out(400, {"error": "max 12 stems"})
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
        t = threading.Thread(target=worker, args=(jid, stems, str(data.get("loudness") or "MEDIUM"), float(data.get("maxSeconds") or 0)))
        t.daemon = True
        t.start()
        return self.json_out(202, {"job": jid})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print("wratty-fx mixer on 0.0.0.0:%d" % port, flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
