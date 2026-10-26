import os
import modal
import uuid

app = modal.App("wratty-autotune")
volume = modal.Volume.from_name("wratty-mixes", create_if_missing=True)

image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("numpy", "scipy", "soundfile", "librosa", "pyworld", "requests")
         .add_local_python_source("vocal_dsp", "beat_key"))

@app.function(image=image, volumes={"/mixes": volume}, timeout=600, cpu=2.0, memory=4096)
def tune_job(job_id: str, vocal_url: str, beat_url: str = None, preset: dict = None, manual_key: str = None):
    # 🚨 ALL IMPORTS MOVED INSIDE THE FUNCTION 🚨
    import numpy as np
    import soundfile as sf
    import requests
    from io import BytesIO
    from vocal_dsp import PitchCorrector
    from beat_key import detect_key

    progress_dict = modal.Dict.from_name("tuning-progress", create_if_missing=True)
    progress_dict[job_id] = {"status": "running", "pct": 10, "stage": "Downloading audio files..."}
    
    try:
        vocal_res = requests.get(vocal_url)
        vocal_res.raise_for_status()
        vocal_data, sr = sf.read(BytesIO(vocal_res.content))
        if vocal_data.ndim > 1:
            vocal_data = np.mean(vocal_data, axis=1)

        scale_type = "Natural Minor"
        detected_key = manual_key if manual_key else "C"
        
        if not manual_key and beat_url:
            progress_dict[job_id] = {"status": "running", "pct": 30, "stage": "Analyzing beat key..."}
            beat_res = requests.get(beat_url)
            beat_res.raise_for_status()
            beat_data, beat_sr = sf.read(BytesIO(beat_res.content))
            det_k, det_s, conf = detect_key(beat_data, beat_sr)
            detected_key = det_k
            scale_type = det_s
        elif manual_key:
            parts = manual_key.split()
            detected_key = parts[0]
            if len(parts) > 1: scale_type = " ".join(parts[1:])

        progress_dict[job_id] = {"status": "running", "pct": 50, "stage": f"Tuning vocal to {detected_key} {scale_type}..."}

        preset = preset or {}
        retune_speed = float(preset.get("retuneSpeed", 25.0))
        humanize = float(preset.get("humanize", 15.0))
        dead_zone = float(preset.get("deadZone", 4.0))

        corrector = PitchCorrector(sample_rate=sr)
        tuned_audio, piano_roll_json = corrector.process_audio(
            vocal_data, key=detected_key, scale=scale_type, retune_speed=retune_speed, humanize=humanize, dead_zone=dead_zone
        )

        progress_dict[job_id] = {"status": "running", "pct": 85, "stage": "Rendering output file..."}
        os.makedirs("/mixes/fx", exist_ok=True)
        output_filename = f"/mixes/fx/tuned-{job_id}.wav"
        sf.write(output_filename, tuned_audio, sr)
        volume.commit()

        result_payload = {
            "status": "done", "pct": 100,
            "url": f"https://wrattyg--wratty-files-web.modal.run/f/fx/tuned-{job_id}.wav",
            "detectedKey": f"{detected_key} {scale_type}", "pianoRoll": piano_roll_json
        }
        progress_dict[job_id] = result_payload
        return result_payload
    except Exception as e:
        err_payload = {"status": "error", "error": str(e)}
        progress_dict[job_id] = err_payload
        raise e

@app.function(image=image)
@modal.fastapi_endpoint(method="POST")
def start(body: dict):
    url = body.get("url")
    if not url: return {"error": "Missing url"}
    job_id = uuid.uuid4().hex
    progress_dict = modal.Dict.from_name("tuning-progress", create_if_missing=True)
    progress_dict[job_id] = {"status": "queued", "pct": 0, "stage": "Queued"}
    tune_job.spawn(job_id, url, body.get("beatUrl"), body.get("preset"), body.get("key"))
    return {"jobId": job_id}

@app.function(image=image)
@modal.fastapi_endpoint(method="GET")
def status(job_id: str):
    progress_dict = modal.Dict.from_name("tuning-progress", create_if_missing=True)
    return progress_dict.get(job_id) or {"status": "unknown"}
