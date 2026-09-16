import uuid

import modal

app = modal.App("wratty-mix")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libsndfile1")
    .pip_install("numpy", "pedalboard", "requests", "fastapi")
    .add_local_dir("fx-api/api", remote_path="/root/api")
)

SECRET = modal.Secret.from_name("wratty-mix")
jobs = modal.Dict.from_name("wratty-mix-jobs", create_if_missing=True)


@app.function(image=image, cpu=2.0, memory=8192, timeout=3600, secrets=[SECRET])
def run_mix(job_id: str, stems: list, loudness: str, max_seconds: float):
    import sys
    import traceback

    sys.path.insert(0, "/root/api")
    import mix

    jobs[job_id] = {"status": "running"}
    try:
        res = mix.do_mix(stems, loudness, job_id, max_seconds)
        jobs[job_id] = {
            "status": "done",
            "url": res.get("url", ""),
            "result": res,
        }
    except Exception as e:
        traceback.print_exc()
        jobs[job_id] = {"status": "failed", "error": str(e)[:300]}
    finally:
        if jobs.get("busy") == job_id:
            jobs["busy"] = None


@app.function(
    image=image,
    cpu=0.5,
    memory=1024,
    timeout=150,
    scaledown_window=300,
    secrets=[SECRET],
)
@modal.asgi_app()
def api():
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
        return jobs.get(jid) or {"status": "none"}

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
        if jobs.get("busy"):
            return JSONResponse(
                {"error": "engine busy - try again in a minute"}, status_code=429
            )

        jid = uuid.uuid4().hex
        jobs["busy"] = jid
        jobs[jid] = {"status": "queued"}
        run_mix.spawn(
            jid,
            stems,
            str(body.get("loudness") or "MEDIUM"),
            float(body.get("maxSeconds") or 0),
        )
        return {"job": jid}

    return web
