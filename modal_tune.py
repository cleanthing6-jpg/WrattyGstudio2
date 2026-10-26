"""
Modal app: flat-vocal fix + auto-tune on the lead with live progress.
"""
import os, uuid, tempfile, urllib.request, shutil, traceback
import modal

image = (modal.Image.debian_slim(python_version="3.11")
         .apt_install("ffmpeg")
         .pip_install("numpy", "scipy", "boto3", "fastapi[standard]")
         .add_local_python_source("vocal_dsp", "beat_key", "flat_fix"))
app = modal.App("wratty-autotune", image=image)
progress = modal.Dict.from_name("autotune-progress", create_if_missing=True)
mixvol = modal.Volume.from_name("wratty-mixes", create_if_missing=True)

def _download(url, d, name):
    path = os.path.join(d, name)
    req = urllib.request.Request(url, headers={"User-Agent": "autotune/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path

@app.function(volumes={"/mixes": mixvol}, timeout=900, cpu=2, memory=4096)
def tune_job(job_id: str, lead_url: str, beat_url: str | None, preset: str = "natural"):
    from vocal_dsp import PitchCorrector, read_audio, write_audio, peak_limit
    from beat_key import analyse_beat
    from flat_fix import fix_flat

    last = {"pct": -1}

    def put(**kw):
        progress[job_id] = {**progress.get(job_id, {}), **kw}

    try:
        put(status="running", pct=0, stage="Starting")
        with tempfile.TemporaryDirectory() as d:
            x, sr = read_audio(_download(lead_url, d, "lead_in"))
            key, key_src, ref_cents = "auto", "vocal", 0.0
            
            if beat_url:
                put(stage="Reading beat key", pct=2)
                try:
                    bx, bsr = read_audio(_download(beat_url, d, "beat_in"))
                    r = analyse_beat(bx, bsr)
                    ref_cents = r["ref_cents"]
                    if r["key_margin"] >= 0.05:
                        key, key_src = r["key"], "beat"
                except Exception:
                    pass

            def cb_fix(frac, stage):
                pct = int(4 + frac * 45)
                if pct != last["pct"]:
                    last["pct"] = pct
                    put(pct=pct, stage=stage)

            def cb_tune(frac, stage):
                pct = int(50 + frac * 49)
                if pct != last["pct"]:
                    last["pct"] = pct
                    put(pct=pct, stage=stage)

            # 1. Flat Fix (Runs first to prep the vocal)
            y, info = fix_flat(x, sr, ref_cents=ref_cents, key=key, progress_cb=cb_fix)

            # 2. Actual Auto-Tune (Runs second to snap the pitch)
            _preset = preset if preset in ("natural", "hard", "pop", "transparent") else "natural"
            tuner = PitchCorrector(preset=_preset, key=key)
            tuner.progress_cb = cb_tune
            y, tune_info = tuner.process(y, sr)

            y = peak_limit(y, sr)
            out = os.path.join(d, "lead_tuned.wav")
            write_audio(out, y, sr, channels=1, bits=24)
            put(stage="Saving", pct=99)
            
            os.makedirs("/mixes/fx", exist_ok=True)
            dest = f"/mixes/fx/tuned-{job_id}.wav"
            shutil.copy(out, dest)
            mixvol.commit()
            url = f"https://wrattyg--wratty-files-web.modal.run/f/fx/tuned-{job_id}.wav"
            
            put(status="done", pct=100, stage="Done", url=url,
                key=tune_info.get("key"), keySource=key_src, notes=tune_info.get("n_notes"))
    except Exception as e:
        traceback.print_exc()
        put(status="error", error=str(e)[:300])

@app.function(min_containers=1)
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
