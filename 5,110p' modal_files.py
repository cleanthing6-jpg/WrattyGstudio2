[33mcommit fc4b82d0125030afee2e0df2dd0d64e36f1ddfcd[m[33m ([m[1;36mHEAD[m[33m -> [m[1;32mmain[m[33m, [m[1;31morigin/main[m[33m, [m[1;31morigin/HEAD[m[33m)[m
Author: cleanthing6-jpg <cleanthing6@gmail.com>
Date:   Sat Oct 3 16:45:20 2026 +0100

    delete: remove Modal audio files on permanent delete

[1mdiff --git a/modal_cleanup.py b/modal_cleanup.py[m
[1mnew file mode 100644[m
[1mindex 0000000..0282557[m
[1m--- /dev/null[m
[1m+++ b/modal_cleanup.py[m
[36m@@ -0,0 +1,47 @@[m
[32m+[m[32mimport os[m
[32m+[m[32mimport hmac[m
[32m+[m[32mimport modal[m
[32m+[m
[32m+[m[32mapp = modal.App("wratty-cleanup")[m
[32m+[m[32mSECRET = modal.Secret.from_name("wratty-mix")[m
[32m+[m[32mmixvol = modal.Volume.from_name("wratty-mixes", create_if_missing=True)[m
[32m+[m
[32m+[m
[32m+[m[32m@app.function([m
[32m+[m[32m    image=modal.Image.debian_slim().pip_install("fastapi[standard]"),[m
[32m+[m[32m    secrets=[SECRET],[m
[32m+[m[32m    volumes={"/mixes": mixvol},[m
[32m+[m[32m)[m
[32m+[m[32m@modal.asgi_app()[m
[32m+[m[32mdef api():[m
[32m+[m[32m    from fastapi import FastAPI, Request[m
[32m+[m[32m    from fastapi.responses import JSONResponse[m
[32m+[m
[32m+[m[32m    web = FastAPI()[m
[32m+[m
[32m+[m[32m    @web.post("/delete")[m
[32m+[m[32m    async def delete(request: Request):[m
[32m+[m[32m        key = os.environ.get("FX_INTERNAL_SECRET", "")[m
[32m+[m[32m        auth = request.headers.get("authorization", "")[m
[32m+[m[32m        if not key or not hmac.compare_digest(auth, "Bearer " + key):[m
[32m+[m[32m            return JSONResponse({"error": "unauthorized"}, status_code=401)[m
[32m+[m[32m        body = await request.json()[m
[32m+[m[32m        keys = body.get("keys") or [][m
[32m+[m[32m        deleted, missing, bad = [], [], [][m
[32m+[m[32m        for k in keys:[m
[32m+[m[32m            k = str(k)[m
[32m+[m[32m            if not (k.startswith("fx/") and (k.endswith(".mp3") or k.endswith(".flac"))):[m
[32m+[m[32m                bad.append(k)[m
[32m+[m[32m                continue[m
[32m+[m[32m            try:[m
[32m+[m[32m                os.remove(os.path.join("/mixes", k))[m
[32m+[m[32m                deleted.append(k)[m
[32m+[m[32m            except FileNotFoundError:[m
[32m+[m[32m                missing.append(k)[m
[32m+[m[32m            except Exception:[m
[32m+[m[32m                bad.append(k)[m
[32m+[m[32m        if deleted:[m
[32m+[m[32m            mixvol.commit()[m
[32m+[m[32m        return JSONResponse({"ok": True, "deleted": deleted, "missing": missing, "bad": bad})[m
[32m+[m
[32m+[m[32m    return web[m
