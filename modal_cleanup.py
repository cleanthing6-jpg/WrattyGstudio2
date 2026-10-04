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


# Runs daily at 03:00 UTC. Starts in DRY-RUN: it only logs what it WOULD
# delete, so the policy can be reviewed before anything is removed.
# Flip `{"live": True}` to enable real deletion.
@app.function(
    image=modal.Image.debian_slim(),
    secrets=[SECRET],
    schedule=modal.Cron("0 3 * * *"),
    timeout=600,
)
def retention_sweep():
    import json
    import os
    import urllib.request

    app_url = (os.environ.get("APP_URL") or "").rstrip("/")
    key = os.environ.get("FX_INTERNAL_SECRET", "")
    if not app_url or not key:
        print("retention: APP_URL or FX_INTERNAL_SECRET missing", flush=True)
        return

    body = json.dumps({"live": True}).encode()    # LIVE
    req = urllib.request.Request(
        app_url + "/api/retention/sweep",
        data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        # 180s: the Render service may be cold-starting after 15 min idle.
        with urllib.request.urlopen(req, timeout=180) as r:
            print("retention:", r.status, r.read()[:600].decode(), flush=True)
    except Exception as e:
        print("retention failed:", e, flush=True)
