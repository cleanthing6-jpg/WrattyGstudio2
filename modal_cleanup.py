import os
import hmac
import modal

app = modal.App("wratty-cleanup")
SECRET = modal.Secret.from_name("wratty-mix")
mixvol = modal.Volume.from_name("wratty-mixes", create_if_missing=True)


@app.function(
    image=modal.Image.debian_slim().pip_install("fastapi[standard]"),
    secrets=[SECRET],
    volumes={"/mixes": mixvol},
)
@modal.asgi_app()
def api():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    web = FastAPI()

    @web.post("/delete")
    async def delete(request: Request):
        key = os.environ.get("FX_INTERNAL_SECRET", "")
        auth = request.headers.get("authorization", "")
        if not key or not hmac.compare_digest(auth, "Bearer " + key):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        keys = body.get("keys") or []
        deleted, missing, bad = [], [], []
        for k in keys:
            k = str(k)
            if not (k.startswith("fx/") and (k.endswith(".mp3") or k.endswith(".flac"))):
                bad.append(k)
                continue
            try:
                os.remove(os.path.join("/mixes", k))
                deleted.append(k)
            except FileNotFoundError:
                missing.append(k)
            except Exception:
                bad.append(k)
        if deleted:
            mixvol.commit()
        return JSONResponse({"ok": True, "deleted": deleted, "missing": missing, "bad": bad})

    return web
