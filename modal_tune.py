import os
import modal
import uuid
import numpy as np
import soundfile as sf

app = modal.App("wratty-autotune")
volume = modal.Volume.from_name("wratty-mixes", create_if_missing=True)

image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("numpy", "scipy", "soundfile", "requests", "fastapi[standard]")
         .add_local_python_source("vocaltune"))

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def midi_to_name(m):
    return f"{NOTE_NAMES[int(m) % 12]}{int(m) // 12 - 1}"

@app.function(image=image, volumes={"/mixes": volume}, timeout=600, cpu=2.0, memory=4096)
def tune_job(job_id: str, vocal_url: str, beat_url: str = None, preset: str = None, manual_key: str = None):
    progress_dict = modal.Dict.from_name("tuning-progress", create_if_missing=True)
    progress_dict[job_id] = {"status": "running", "pct": 10, "stage": "Initializing..."}

    try:
        from vocaltune.io_utils import read_audio, write_audio
        from vocaltune.engine import VocalTuner
        
        progress_dict[job_id] = {"status": "running", "pct": 15, "stage": "Downloading audio files..."}

        import requests
        from io import BytesIO
        vocal_res = requests.get(vocal_url)
        vocal_res.raise_for_status()
        vocal_data, sr = sf.read(BytesIO(vocal_res.content))
        if vocal_data.ndim > 1: vocal_data = np.mean(vocal_data, axis=1)

        beat_data = None
        beat_sr = None
        if beat_url:
            progress_dict[job_id] = {"status": "running", "pct": 20, "stage": "Downloading beat..."}
            beat_res = requests.get(beat_url)
            beat_res.raise_for_status()
            beat_data, beat_sr = sf.read(BytesIO(beat_res.content))
            if beat_data.ndim > 1: beat_data = np.mean(beat_data, axis=1)

        progress_dict[job_id] = {"status": "running", "pct": 40, "stage": f"Tuning ({preset})..."}

        tuner = VocalTuner()
        result = tuner.process(
            vocal_data, 
            sr, 
            genre=preset or "afrobeats", 
            beat=beat_data, 
            beat_sr=beat_sr,
            key=manual_key
        )

        progress_dict[job_id] = {"status": "running", "pct": 85, "stage": "Rendering..."}

        os.makedirs("/mixes/fx", exist_ok=True)
        out = f"/mixes/fx/tuned-{job_id}.wav"
        write_audio(out, result.audio, sr, bits=24)
        volume.commit()

        notes_list = []
        for n in result.notes:
            st = float(n.start * result.correction.hop_s)
            et = float(n.end * result.correction.hop_s)
            pm = int(n.target_midi)
            notes_list.append({
                "startTime": round(st, 4),
                "endTime": round(et, 4),
                "duration": round(et - st, 4),
                "pitchMidi": pm,
                "noteName": midi_to_name(pm)
            })

        payload = {
            "status": "done",
            "pct": 100,
            "stage": "Done",
            "url": f"https://wrattyg--wratty-files-web.modal.run/f/fx/tuned-{job_id}.wav",
            "detectedKey": result.key,
            "pianoRoll": notes_list,
            "notes": len(notes_list)
        }
        progress_dict[job_id] = payload
        return payload

    except Exception as e:
        import traceback
        traceback.print_exc()
        err = {"status": "error", "error": str(e)[:300]}
        progress_dict[job_id] = err
        raise e

@app.function(image=image, volumes={"/mixes": volume})
@modal.fastapi_endpoint(method="POST")
def start(body: dict):
    url = body.get("url")
    if not url:
        return {"error": "Missing url"}
    job_id = uuid.uuid4().hex
    progress_dict = modal.Dict.from_name("tuning-progress", create_if_missing=True)
    progress_dict[job_id] = {"status": "queued", "pct": 0, "stage": "Queued"}
    tune_job.spawn(job_id, url, body.get("beatUrl"), body.get("preset"), body.get("key"))
    return {"jobId": job_id}

@app.function(image=image, volumes={"/mixes": volume})
@modal.fastapi_endpoint(method="GET")
def status(job_id: str):
    progress_dict = modal.Dict.from_name("tuning-progress", create_if_missing=True)
    return progress_dict.get(job_id) or {"status": "unknown"}
