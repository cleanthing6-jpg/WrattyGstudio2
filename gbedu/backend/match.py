"""Gbedu matching - drive the GPU worker until the beat fits the song.

    python gbedu/backend/match.py song.mp3 https://worker-url [genre]
"""
from __future__ import annotations
import json, os, pathlib, sys
import requests

try:
    from .brain import analyze, analyze_bytes, fits
except ImportError:
    from brain import analyze, analyze_bytes, fits

WORKER_KEY = os.environ.get("GBEDU_WORKER_KEY", "")

def _headers():
    return {"X-Gbedu-Key": WORKER_KEY} if WORKER_KEY else {}

def analyze_on_worker(path, worker_url, timeout=300):
    last = None
    for field in ("vocal", "file"):
        try:
            with open(path, "rb") as f:
                r = requests.post(worker_url.rstrip("/") + "/analyze",
                                  files={field: f}, headers=_headers(), timeout=timeout)
            if r.status_code == 400: continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = f"{field}: {type(e).__name__} {str(e)[:120]}"
    raise RuntimeError(f"worker analysis failed ({last})")

def request_take(spec, worker_url, genre="afrobeats", seeds=None, timeout=1500):
    payload = {"bpm": spec["bpm"], "key": spec["key"], "scale": spec["scale"], "genre": genre}
    if seeds: payload["seeds"] = seeds
    r = requests.post(worker_url.rstrip("/") + "/generate",
                      json=payload, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.content, dict(r.headers)

def _beat_from_headers(headers):
    raw = headers.get("X-Gbedu-Report")
    if not raw: return None
    try: rep = json.loads(raw)
    except Exception: return None
    p = (rep or {}).get("picked") or {}
    if not p: return None
    bits = str(p.get("key") or "").split()
    return {"bpm": p.get("bpm"), "key": bits[0] if bits else None,
            "scale": bits[1] if len(bits) > 1 else None, "_report": rep}

def produce_matched_beat(spec, worker_url, genre="afrobeats", tries=2, log=print):
    best = None
    for i in range(tries):
        log(f"[match] try {i+1}/{tries}")
        try:
            audio, headers = request_take(spec, worker_url, genre)
        except Exception as e:
            log(f"[match] worker error: {type(e).__name__} {str(e)[:200]}")
            continue
        beat = _beat_from_headers(headers)
        if not beat:
            try: beat = analyze_bytes(audio)
            except Exception: beat = {"bpm": None, "key": None, "scale": None}
        ok = bool(beat.get("bpm") and beat.get("key")) and fits(spec, beat)
        log(f"[match] beat={ {k: v for k, v in beat.items() if not k.startswith('_')} } fits={ok}")
        if ok:
            return audio, {"target": spec, "beat": beat, "matched": True,
                           "tries": i+1, "worker_report": beat.get("_report")}
        if best is None: best = (audio, beat)
    audio, beat = best
    return audio, {"target": spec, "beat": beat, "matched": False,
                   "tries": tries, "worker_report": beat.get("_report")}

def main():
    vocal, worker = sys.argv[1], sys.argv[2]
    genre = sys.argv[3] if len(sys.argv) > 3 else "afrobeats"
    try:
        spec = analyze(vocal)
    except Exception as e:
        print("local analysis unavailable, asking the worker:", type(e).__name__, flush=True)
        spec = analyze_on_worker(vocal, worker)
    print("VOCAL SPEC:", spec, flush=True)
    audio, report = produce_matched_beat(spec, worker, genre)
    out = pathlib.Path("matched_beat.wav"); out.write_bytes(audio)
    print(json.dumps(report, indent=2))
    print("SAVED:", out.resolve(), out.stat().st_size, "bytes")

if __name__ == "__main__":
    main()
