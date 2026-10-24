"""
Modal app: tune the lead vocal (optionally using the beat's key) and report live progress.
Deploy:  modal deploy modal_tune.py     -> prints the two endpoint URLs (start, status)
"""
import os, uuid, tempfile, urllib.request
import modal

image = (modal.Image.debian_slim(python_version="3.11")
         .apt_install("ffmpeg")
         .pip_install("numpy", "scipy", "boto3", "fastapi[standard]")
         .add_local_python_source("vocal_dsp", "beat_key"))
app = modal.App("wratty-autotune", image=image)
progress = modal.Dict.from_name("autotune-progress", create_if_missing=True)
r2 = modal.Secret.from_name("wratty-r2")


def _download(url, d, name):
    path = os.path.join(d, name)
    req = urllib.request.Request(url, headers={"User-Agent": "autotune/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def _upload(path, key):
    import boto3
    s3 = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT"],
                      aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
    bucket = os.environ["R2_BUCKET"]
    s3.upload_file(path, bucket, key, ExtraArgs={"ContentType": "audio/wav"})
    return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600 * 6)


@app.function(secrets=[r2], timeout=900, cpu=2, memory=4096)
def tune_job(job_id: str, lead_url: str, beat_url: str | None, preset: str):
    from vocal_dsp import PitchCorrector, read_audio, write_audio, peak_limit
    from beat_key import detect_key

    last = {"pct": -1}

    def put(**kw):
        progress[job_id] = {**progress.get(job_id, {}), **kw}

    try:
        put(status="running", pct=0, stage="Starting")
        with tempfile.TemporaryDirectory() as d:
            x, sr = read_audio(_download(lead_url, d, "lead_in"))
            key, key_src = "auto", "vocal"
            if beat_url:
                put(stage="Reading beat key", pct=2)
                try:
                    bx, bsr = read_audio(_download(beat_url, d, "beat_in"))
                    k, margin = detect_key(bx, bsr)
                    if margin >= 0.05:
                        key, key_src = k, "beat"
                except Exception:
                    pass

            tuner = PitchCorrector(preset=preset if preset in ("natural", "hard", "pop", "transparent") else "natural",
                                   key=key)

            def cb(frac, stage):
                pct = int(4 + frac * 94)
                if pct != last["pct"]:
                    last["pct"] = pct
                    put(pct=pct, stage=stage)

            tuner.progress_cb = cb
            y, info = tuner.process(x, sr)
            y = peak_limit(y, sr)
            out = os.path.join(d, "lead_tuned.wav")
            write_audio(out, y, sr, channels=1, bits=24)
            put(stage="Saving", pct=99)
            url = _upload(out, f"tuned/{job_id}.wav")
            put(status="done", pct=100, stage="Done", url=url,
                key=info.get("key"), keySource=key_src, notes=info.get("n_notes"))
    except Exception as e:
        put(status="error", error=str(e)[:300])


@app.function(keep_warm=1)
@modal.fastapi_endpoint(method="POST")
def start(body: dict):
    job_id = uuid.uuid4().hex
    progress[job_id] = {"status": "queued", "pct": 0, "stage": "Queued"}
    tune_job.spawn(job_id, body["url"], body.get("beatUrl"), body.get("preset", "natural"))
    return {"jobId": job_id}


@app.function()
@modal.fastapi_endpoint(method="GET")
def status(job_id: str):
    return progress.get(job_id) or {"status": "unknown"}
