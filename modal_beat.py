"""Text -> beat on Modal, adapted from Modal's ACE-Step 1.5 example.

Beats land in the wratty-mixes volume, so the existing /f/... file server
plays them with no new storage or host.
"""
from pathlib import Path
from uuid import uuid4

import modal

checkpoints_dir = "/opt/ace-step/checkpoints"
MIX_MOUNT = "/mixes"
FILES_BASE = "https://wrattyg--wratty-files-web.modal.run"

# --- verbatim from Modal's example (do not get creative here) ---
image = (
    modal.Image.from_registry(
        "nvidia/cuda:13.0.0-cudnn-devel-ubuntu22.04", add_python="3.12"
    )
    .apt_install("git", "ffmpeg")
    .run_commands(
        "git clone --branch v0.1.6 --depth 1 https://github.com/ace-step/ACE-Step-1.5.git /opt/ace-step",
    )
    .uv_pip_install(
        "/opt/ace-step", "hf_transfer==0.1.9", "torchcodec==0.10.0", "torch~=2.10.0"
    )
    .env({"ACESTEP_PROJECT_ROOT": "/opt/ace-step", "HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .entrypoint([])
)

model_cache = modal.Volume.from_name("ACE-Step-v15-model-cache", create_if_missing=True)
mixvol = modal.Volume.from_name("wratty-mixes", create_if_missing=True)

app = modal.App("wratty-beat")

# l40s like the official example. Try "L4" once this works, to halve cost.
GPU = "l40s"


@app.cls(
    gpu=GPU,
    image=image,
    volumes={checkpoints_dir: model_cache, MIX_MOUNT: mixvol},
    timeout=1800,
    max_containers=1,        # never let two GPUs bill at once
    scaledown_window=120,    # short idle window: 5 min idle would cost ~$1.63
)
class BeatGenerator:
    @modal.enter()
    def init(self):
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler
        from acestep.model_downloader import ensure_lm_model, ensure_main_model

        lm_model_name = "acestep-5Hz-lm-4B"
        ensure_main_model(checkpoints_dir=checkpoints_dir)
        ensure_lm_model(model_name=lm_model_name, checkpoints_dir=checkpoints_dir)

        self.dit_handler = AceStepHandler()
        init_status, enable_generate = self.dit_handler.initialize_service(
            project_root="/opt/ace-step",
            config_path="acestep-v15-turbo",
            device="cuda",
        )
        if not enable_generate:
            raise RuntimeError("DiT init failed: %s" % init_status)

        self.llm_handler = LLMHandler()
        lm_status, lm_success = self.llm_handler.initialize(
            checkpoint_dir=checkpoints_dir,
            lm_model_path=lm_model_name,
            backend="vllm",
            device="cuda",
        )
        if not lm_success:
            raise RuntimeError("LM init failed: %s" % lm_status)

    @modal.method()
    def beat(self, prompt: str, duration: float = 45.0, seed: int = 1) -> dict:
        from acestep.inference import GenerationConfig, GenerationParams, generate_music

        params = GenerationParams(
            caption=prompt,
            lyrics="[Instrumental]",
            duration=duration,
            thinking=True,
        )
        config = GenerationConfig(
            audio_format="mp3",
            batch_size=1,
            seeds=[seed],
            use_random_seed=False,
        )
        result = generate_music(
            self.dit_handler, self.llm_handler, params, config, save_dir="/dev/shm"
        )
        if not result.success:
            raise RuntimeError("generation failed: %s" % result.error)

        data = Path(result.audios[0]["path"]).read_bytes()
        key = "fx/beat-%s.mp3" % uuid4().hex
        dst = Path(MIX_MOUNT) / key
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(dst)          # atomic
        mixvol.commit()           # publish to the file server
        return {"key": key, "bytes": len(data),
                "url": "%s/f/%s" % (FILES_BASE, key)}


@app.function(image=image, timeout=600)
def introspect():
    """Cheap, no GPU: discover what the generation API actually accepts.
    This is how we find the Vocal2BGM parameters for stage 3."""
    import dataclasses
    import inspect

    from acestep import inference

    lines = []
    for name in ("GenerationParams", "GenerationConfig"):
        cls = getattr(inference, name, None)
        if cls is not None and dataclasses.is_dataclass(cls):
            lines.append("%s: %s" % (name, ", ".join(f.name for f in dataclasses.fields(cls))))
    lines.append("generate_music: %s" % inspect.signature(inference.generate_music))
    return "\n".join(lines)


@app.local_entrypoint()
def main(
    prompt: str = "Afrobeats instrumental, log drum bass, shaker groove, 104 BPM, no vocals",
    duration: float = 45.0,
):
    res = BeatGenerator().beat.remote(prompt, duration=duration)
    print("BEAT %s  (%d bytes)" % (res["url"], res["bytes"]))


# ---------------------------------------------------------------------------
# Job API - start a beat, poll for it. Same shape as the mix engine.
# ---------------------------------------------------------------------------

BEAT_SECRET = modal.Secret.from_name("wratty-mix")   # same FX_INTERNAL_SECRET
jobs = modal.Dict.from_name("wratty-beat-jobs", create_if_missing=True)

# Slim image for the web tier. All the heavy ACE-Step imports live inside
# BeatGenerator.init(), so this layer never needs torch.
beat_web_image = modal.Image.debian_slim(python_version="3.12").uv_pip_install(
    "fastapi[standard]", "pydantic"
)


@app.function(image=beat_web_image, cpu=1.0, memory=2048, timeout=1800)
def run_beat(job_id: str, prompt: str, duration: float, seed: int):
    """CPU wrapper: drives the GPU class and records progress in the Dict."""
    import traceback

    jobs[job_id] = {"status": "running"}
    try:
        res = BeatGenerator().beat.remote(prompt, duration=duration, seed=seed)
        jobs[job_id] = {"status": "done", "url": res.get("url", ""), "result": res}
    except Exception as e:
        traceback.print_exc()
        jobs[job_id] = {"status": "failed", "error": str(e)[:300]}


@app.function(image=beat_web_image, timeout=150, scaledown_window=300,
              secrets=[BEAT_SECRET])
@modal.asgi_app()
def api():
    import os
    import uuid

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    web = FastAPI()
    key = os.environ.get("FX_INTERNAL_SECRET", "")

    @web.get("/health")
    async def health():
        return {"ok": True}

    @web.get("/")
    async def poll(request: Request):
        jid = request.query_params.get("id")
        if not jid:
            return {"ok": True}
        return (await jobs.get.aio(jid)) or {"status": "none"}

    @web.post("/")
    async def start(request: Request):
        if not key or request.headers.get("authorization") != "Bearer " + key:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "bad json"}, status_code=400)

        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            return JSONResponse({"error": "prompt required"}, status_code=400)

        duration = float(body.get("duration") or 45.0)
        if not (5.0 <= duration <= 240.0):
            return JSONResponse({"error": "duration must be 5-240s"}, status_code=400)

        seed = int(body.get("seed") or 1)

        jid = uuid.uuid4().hex
        await jobs.put.aio(jid, {"status": "queued"})
        await run_beat.spawn.aio(jid, prompt, duration, seed)
        return {"job": jid}

    return web
