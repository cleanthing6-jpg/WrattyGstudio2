import uuid
import time

import modal

app = modal.App("wratty-mix")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libsndfile1", "ca-certificates")
    .pip_install("numpy", "scipy", "numba", "pedalboard>=0.9.25", "requests", "fastapi", "soundfile", "boto3", "urllib3", "certifi")
    .add_local_dir("fx-api/api", remote_path="/root/api")
)

SECRET = modal.Secret.from_name("wratty-mix")
try:
    R2_SECRET = modal.Secret.from_name("wratty-r2")
except Exception:
    R2_SECRET = None
jobs = modal.Dict.from_name("wratty-mix-jobs", create_if_missing=True)

# Mix renders are written here and served by the separate wratty-files app.
mixvol = modal.Volume.from_name("wratty-mixes", create_if_missing=True)


@app.function(image=image, cpu=2.0, memory=8192, timeout=3600, secrets=[SECRET] + ([R2_SECRET] if R2_SECRET else []),
              volumes={"/mixes": mixvol})
def run_mix(job_id: str, stems: list, loudness: str, preset: str = "neutral", max_seconds: float = 0):
    import sys
    import traceback
    import os
    sys.path.insert(0, "/root/api")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fx-api/api"))
    import mix
    jobs[job_id] = {"status": "running"}
    try:
        res = mix.do_mix(stems, loudness, job_id, max_seconds, preset)
        try:
            mixvol.commit()      # publish the render to wratty-files
        except Exception as _e:
            print("volume commit failed: %s" % _e, flush=True)
        try:
            import json as _j
            _safe = {}
            for _k, _v in (res or {}).items():
                try:
                    _j.dumps(_v); _safe[_k] = _v
                except Exception:
                    _safe[_k] = str(_v)[:200]
            _rpt = _j.dumps(_safe, default=str)
            print("MIXREPORT " + _rpt[:6000], flush=True)
            try:
                _rp = os.path.join("/mixes", "reports", "%s.json" % job_id)
                os.makedirs(os.path.dirname(_rp), exist_ok=True)
                with open(_rp, "w") as _f:
                    _f.write(_rpt)
                print("REPORT_SAVED " + _rp, flush=True)
                try:
                    mixvol.commit()
                except Exception as _ce:
                    print("report commit failed: %s" % _ce, flush=True)
            except Exception as _re:
                print("REPORT_SAVE_ERR " + str(_re)[:200], flush=True)
        except Exception:
            pass
        jobs[job_id] = {
            "status": "done",
            "url": res.get("url", ""),
            "result": res,
        }
    except Exception as e:
        traceback.print_exc()
        jobs[job_id] = {"status": "failed", "error": str(e)[:300]}
    finally:
        pass


@app.function(
    image=image,
    cpu=4.0,
    memory=8192,
    timeout=600,
    scaledown_window=300,
    secrets=[SECRET],
)
@modal.asgi_app()
def api():
    print("Forcing clear re-sync validation channel: 1791533703")
    import os

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    web = FastAPI()
    key = os.environ.get("FX_INTERNAL_SECRET", "")

    @web.get("/")
    async def status(request: Request):
        jid = request.query_params.get("id")
        if not jid:
            return {"ok": True}
        if not key or request.headers.get("authorization") != "Bearer " + key:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return (await jobs.get.aio(jid)) or {"status": "none"}

    @web.post("/")
    async def start(request: Request):
        if not key or request.headers.get("authorization") != "Bearer " + key:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "bad json"}, status_code=400)

        stems = body.get("stems")
        if not isinstance(stems, list) or not stems:
            return JSONResponse({"error": "stems[] required"}, status_code=400)
        if len(stems) > 12:
            return JSONResponse({"error": "max 12 stems"}, status_code=400)
        for s in stems:
            if not str(s.get("url") or "").startswith("https://"):
                return JSONResponse(
                    {"error": "each stem needs an https url"}, status_code=400
                )
        # NO global lock: every render runs in its own Modal container, so
        # parallel mixes are fine. The Postgres queue is the ONLY authority
        # on how many run at once.
        jid = uuid.uuid4().hex
        await jobs.put.aio(jid, {"status": "queued"})
        await run_mix.spawn.aio(
            jid,
            stems,
            str(body.get("loudness") or "MEDIUM"),
            str(body.get("preset") or "neutral"),
            float(body.get("maxSeconds") or 0),
        )
        return {"job": jid}

    return web

# FORCE_CACHE_CLEAR_TOKEN = 1791533260


@app.function(image=image, cpu=0.5, memory=1024, timeout=180)
def engine_probe():
    import numpy as np
    import sys, os
    sys.path.insert(0, "/root/api")
    import dsp_delay
    import dsp_pro

    sr = 44100
    dur = 5.0
    n = int(sr * dur)
    t = np.arange(n) / sr
    x = (0.3 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2 * t))).astype(np.float32)
    xs = np.stack([x, x])

    out = {}
    wet, info = dsp_delay.delay_render(xs, sr, bpm=99.4, note_div=0.25)
    dry_rms = float(np.sqrt(np.mean(xs ** 2)))
    wet_rms = float(np.sqrt(np.mean(wet ** 2)))
    out["delay_dry_rms"]   = round(dry_rms, 6)
    out["delay_wet_rms"]   = round(wet_rms, 6)
    out["delay_rel_db"]    = round(20.0 * np.log10(wet_rms / dry_rms + 1e-12), 2)
    out["delay_info"]      = info

    plate = dsp_pro.plate_wet(xs, sr, mix=1.0, duck_depth=0.25)
    if plate is None:
        out["plate"] = "returned None"
    else:
        p_rms = float(np.sqrt(np.mean(plate ** 2)))
        out["plate_dry_rms"] = round(dry_rms, 6)
        out["plate_wet_rms"] = round(p_rms, 6)
        out["plate_rel_db"]  = round(20.0 * np.log10(p_rms / dry_rms + 1e-12), 2)
    return out
# force deploy Mon Oct 19 01:21:54 WAT 2026

# Force deploy 1792369458.6986084
# force deploy Mon Oct 19 01:39:44 WAT 2026
# force deploy Mon Oct 19 09:25:15 WAT 2026
# revert Mon Oct 19 11:37:15 WAT 2026
# deploy master trim Mon Oct 19 17:14:16 WAT 2026
# deploy mix trim off Mon Oct 19 17:21:02 WAT 2026
# master_bus: fix top trim tolerance Mon Oct 19 18:15:24 WAT 2026
# disable top trim Mon Oct 19 18:39:28 WAT 2026
# ultimate safe rap chain Mon Oct 19 19:55:22 WAT 2026
# fixed treat_for for new roles Mon Oct 19 20:22:08 WAT 2026
# pro gain staging fixed (adlibs untouched) Mon Oct 19 20:42:23 WAT 2026
# inserted pro intro/outro/response roles Mon Oct 19 20:44:28 WAT 2026
# fully adaptive new roles Mon Oct 19 20:49:59 WAT 2026
# master presets all genres Mon Oct 19 21:20:06 WAT 2026

# revert my changes
# vocal_space integration
# capture vocal_space error
# log claude report
# restore vocal_sat and beat_punch
# inject vocal space rep into report
# surgical echo fix
# boost delay vol
# boost delay vol
# wire beat_punch
# wire vocal_sat
# wire vocal_polish
# adjust delay volume and restore ducking
# fix r2 ssl handshake
