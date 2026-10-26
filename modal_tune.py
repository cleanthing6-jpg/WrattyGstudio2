import os, uuid, tempfile, urllib.request, shutil
import modal

image = (modal.Image.debian_slim(python_version="3.11")
         .apt_install("ffmpeg")
         .pip_install("numpy", "scipy", "boto3", "fastapi[standard]")
         .add_local_python_source("vocal_dsp", "beat_key", "vocal_rescue"))
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
    from beat_key import detect_key
    import vocal_rescue

    last = {"pct": -1}
    def put(**kw):
        progress[job_id] = {**progress.get(job_id, {}), **kw}

    try:
        put(status="running", pct=0, stage="Starting")
        with tempfile.TemporaryDirectory() as d:
            x, sr = read_audio(_download(lead_url, d, "lead_in"))
            
            # --- DETECT THE KEY FROM THE BEAT ---
            key = "auto"
            if beat_url:
                put(stage="Reading beat key", pct=2)
                try:
                    bx, bsr = read_audio(_download(beat_url, d, "beat_in"))
                    k, margin = detect_key(bx, bsr)
                    if margin >= 0.05:
                        key = k
                    print(f"=== BEAT KEY DETECTED: {key} (margin {margin:.3f}) ===")
                except Exception as e:
                    print("Beat key detection failed:", e)

            def cb(frac, stage):
                pct = int(4 + frac * 94)
                if pct != last["pct"]:
                    last["pct"] = pct
                    put(pct=pct, stage=stage)

            # 1. PHONE RECORD FIX (Pre)
            put(stage="Fixing phone recording", pct=4)
            y_pre, rescue_pre = vocal_rescue.rescue(x, sr, stage="pre")

            # 2. PURE AUTO-TUNE (using the beat's key!)
            _preset = preset if preset in ("natural", "hard", "pop", "transparent") else "natural"
            tuner = PitchCorrector(preset=_preset, key=key)
            tuner.progress_cb = cb
            y_tuned, info = tuner.process(y_pre, sr)

            # 3. PHONE RECORD FIX (Post)
            put(stage="Polishing tone", pct=95)
            y_final, rescue_post = vocal_rescue.rescue(y_tuned, sr, stage="post")

            y_final = peak_limit(y_final, sr)
            out = os.path.join(d, "lead_tuned.wav")
            write_audio(out, y_final, sr, channels=1, bits=24)
            put(stage="Saving", pct=99)
            
            os.makedirs("/mixes/fx", exist_ok=True)
            dest = f"/mixes/fx/tuned-{job_id}.wav"
            shutil.copy(out, dest)
            mixvol.commit()
            url = f"https://wrattyg--wratty-files-web.modal.run/f/fx/tuned-{job_id}.wav"
            
            print(f"=== AUTO TUNE SUCCESS ===\nKey: {info.get('key')}\n=====================")
            put(status="done", pct=100, stage="Done", url=url, key=info.get("key"), notes=info.get("n_notes"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        put(status="error", error=str(e)[:300])

@app.function()
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
