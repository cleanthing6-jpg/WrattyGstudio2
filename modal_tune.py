import os, uuid, tempfile, urllib.request, shutil
import numpy as np
import modal

image = (modal.Image.debian_slim(python_version="3.11")
         .apt_install("ffmpeg")
         .pip_install("numpy", "scipy", "boto3", "fastapi[standard]")
         .add_local_python_source("vocal_dsp", "beat_key", "flat_fix", "key_lock"))
app = modal.App("wratty-autotune", image=image)
progress = modal.Dict.from_name("autotune-progress", create_if_missing=True)
mixvol = modal.Volume.from_name("wratty-mixes", create_if_missing=True)

KEY_CONF_MIN = 0.20
OFFSET_CONF_MIN = 0.05

def _download(url, d, name):
    path = os.path.join(d, name)
    req = urllib.request.Request(url, headers={"User-Agent": "autotune/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path

@app.function(volumes={"/mixes": mixvol}, timeout=900, cpu=2, memory=4096)
def tune_job(job_id: str, lead_url: str, beat_url: str | None, preset: str = "natural", manual_key: str | None = None):
    from vocal_dsp import PitchCorrector, read_audio, write_audio, peak_limit
    from flat_fix import fix_flat
    import key_lock

    last = {"pct": -1}
    def put(**kw):
        progress[job_id] = {**progress.get(job_id, {}), **kw}

    try:
        put(status="running", pct=0, stage="Starting")
        with tempfile.TemporaryDirectory() as d:
            x, sr = read_audio(_download(lead_url, d, "lead_in"))
            key_src, key_name = "unsure", "unsure"
            ref_cents = 0.0
            allowed_pcs = None
            global_offset = None

            r = None
            try:
                if manual_key:
                    r = key_lock.parse_key(manual_key)
                elif beat_url:
                    put(stage="Reading beat key", pct=2)
                    bx, bsr = read_audio(_download(beat_url, d, "beat_in"))
                    bc = key_lock.key_chroma(bx, bsr)
                    _, ref_cents = key_lock.chroma(bx, bsr)
                    vc, _ = key_lock.chroma(x, sr)
                    r = key_lock.detect_allowed(bc, vc)
                else:
                    vc, _ = key_lock.chroma(x, sr)
                    r = key_lock.detect_allowed(np.zeros(12), vc)
                print(f"=== KEY LOCK ===\n{r}\n=================")

                if r["confidence"] >= KEY_CONF_MIN:
                    allowed_pcs = [int(i) for i in np.where(r["allowed"])[0]]
                    key_src, key_name = r["source"], r["name"]
                    off_c, off_conf = key_lock.estimate_global_offset(x, sr, r["allowed"], min_conf=OFFSET_CONF_MIN)
                    print(f"=== GLOBAL OFFSET ===\noffset={off_c:.1f}c confidence={off_conf:.2f}\n=====================")
                    if off_conf >= OFFSET_CONF_MIN and abs(off_c) >= 5.0:
                        global_offset = float(off_c)
                else:
                    print(f"⚠️ Key unsure ({r['confidence']:.2f}): no mask, no offset, no key name forced")
                    put(needsKey=True, keyCandidates=r.get("candidates", []))
            except Exception as e:
                print("Key lock failed:", e)
                import traceback; traceback.print_exc()

            def cb_fix(frac, stage):
                pct = int(4 + frac * 45)
                if pct != last["pct"]: last["pct"] = pct; put(pct=pct, stage=stage)
            def cb_tune(frac, stage):
                pct = int(50 + frac * 49)
                if pct != last["pct"]: last["pct"] = pct; put(pct=pct, stage=stage)

            y, info = fix_flat(x, sr, ref_cents=ref_cents, key="auto", progress_cb=cb_fix,
                               allowed_pcs=allowed_pcs, global_offset_cents=global_offset)

            _preset = preset if preset in ("natural", "hard", "pop", "transparent") else "natural"
            max_corr = 2.0 if global_offset is not None else 4.0
            tuner = PitchCorrector(preset=_preset, key="auto", allowed_pcs=allowed_pcs, max_correction_semitones=max_corr)
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
            print("=== FLAT FIX RESULTS ===")
            print(info)
            print(f"=== AUTO TUNE KEY ===\nKey: {key_name} (tuner label: {tune_info.get('key')}), Key Source: {key_src}, "
                  f"global_offset: {global_offset}\n=====================")
            put(status="done", pct=100, stage="Done", url=url, key=key_name, keySource=key_src,
                globalOffsetCents=global_offset, notes=tune_info.get("n_notes"), flat_info=info)
    except Exception as e:
        import traceback
        traceback.print_exc()
        put(status="error", error=str(e)[:300])

@app.function(min_containers=1)
@modal.fastapi_endpoint(method="POST")
def start(body: dict):
    job_id = uuid.uuid4().hex
    progress[job_id] = {"status": "queued", "pct": 0, "stage": "Queued"}
    tune_job.spawn(job_id, body["url"], body.get("beatUrl"), body.get("preset", "natural"), body.get("key"))
    return {"jobId": job_id}

@app.function()
@modal.fastapi_endpoint(method="GET")
def status(job_id: str):
    return progress.get(job_id) or {"status": "unknown"}
