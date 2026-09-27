"""Serves - and now accepts - files on the wratty-mixes volume."""
import hashlib
import hmac
import os
import pathlib
import time
from urllib.parse import quote

import modal

VOL = "wratty-mixes"
MOUNT = "/mixes"
FILES_BASE = "https://wrattyg--wratty-files-web.modal.run"
MAX_UPLOAD = 512 * 1024 * 1024      # per-file cap
SECRET_NAME = "wratty-mix"          # reuses FX_INTERNAL_SECRET

app = modal.App("wratty-files")
vol = modal.Volume.from_name(VOL, create_if_missing=True)

image = modal.Image.debian_slim().pip_install("fastapi[standard]")

MEDIA = {".mp3": "audio/mpeg", ".flac": "audio/flac",
         ".wav": "audio/wav", ".m4a": "audio/mp4"}
HDRS = {"cache-control": "public, max-age=31536000, immutable",
        "access-control-allow-origin": "*"}


@app.function(image=image, volumes={MOUNT: vol},
              secrets=[modal.Secret.from_name(SECRET_NAME)],
              max_containers=4, timeout=300)
@modal.asgi_app()
def web():
    import threading
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse

    api = FastAPI()
    api.add_middleware(CORSMiddleware, allow_origins=["*"],
                       allow_methods=["GET", "PUT", "OPTIONS"],
                       allow_headers=["*"], max_age=86400)

    ROOT = pathlib.Path(MOUNT).resolve()
    LOCK = threading.Lock()
    KEY = os.environ.get("FX_INTERNAL_SECRET", "")

    def resolve(key):
        p = (ROOT / key).resolve()
        if not str(p).startswith(str(ROOT)):
            return None
        return p

    def ticket_ok(req):
        """Verifies the short-lived ticket minted by the Next.js app.
        The signing secret itself never leaves the two servers."""
        if not KEY:
            return False
        tok = req.headers.get("x-fx-ticket", "")
        try:
            exp_s, sig = tok.split(".", 1)
            exp = int(exp_s)
        except Exception:
            return False
        if abs(time.time() - exp) > 900:      # +-15 min, tolerant of clock skew
            return False
        want = hmac.new(KEY.encode(), ("stem-upload|%d" % exp).encode(),
                        hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, sig)

    def listing(prefix=""):
        out = []
        if ROOT.is_dir():
            for p in ROOT.rglob("*"):
                if p.is_file() and not p.name.endswith(".part"):
                    k = str(p.relative_to(ROOT))
                    if k.startswith(prefix):
                        out.append(k)
        return sorted(out)

    @api.get("/")
    def index():
        return {"ok": True, "service": "wratty-files",
                "mounted": ROOT.is_dir(), "base": "/f/<key>"}

    @api.get("/health")
    def health():
        return {"ok": True, "mounted": ROOT.is_dir(), "mount": MOUNT}

    @api.get("/ls")
    def ls(prefix: str = ""):
        if not ROOT.is_dir():
            return {"count": 0, "files": [], "note": "volume not mounted"}
        ks = listing(prefix)
        return {"count": len(ks), "files": ks[:200]}

    @api.put("/u/{key:path}")
    async def upload(key: str, request: Request):
        if not ticket_ok(request):
            raise HTTPException(status_code=401, detail="bad or expired ticket")
        p = resolve(key)
        if p is None or key.startswith("/") or ".." in key:
            raise HTTPException(status_code=400, detail="bad key")
        if p.exists():
            raise HTTPException(status_code=409, detail="already exists: " + key)

        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        n = 0
        with open(tmp, "wb") as fh:
            async for chunk in request.stream():
                n += len(chunk)
                if n > MAX_UPLOAD:
                    fh.close()
                    tmp.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="too large")
                fh.write(chunk)
        if n == 0:
            tmp.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="empty body")
        os.replace(tmp, p)                   # atomic - never a half file
        try:
            vol.commit()                     # publish before we say OK
        except Exception as e:
            print("upload commit failed: %s" % e, flush=True)
        return {"key": key, "bytes": n,
                "url": "%s/f/%s" % (FILES_BASE, quote(key))}

    @api.get("/f/{key:path}")
    def get_file(key: str):
        p = resolve(key)
        if p is None:
            raise HTTPException(status_code=400, detail="bad key")
        if not p.is_file():
            # Miss: another container may have just committed. reload() only
            # here - it errors "volume busy" while files are open, and shows
            # the volume empty for a moment, so never on the hot path.
            with LOCK:
                if not p.is_file():
                    try:
                        vol.reload()
                    except Exception as e:
                        print("reload failed: %s" % e, flush=True)
                        time.sleep(0.5)
            p = resolve(key)
        if p is None or not p.is_file():
            raise HTTPException(status_code=404, detail="not found: " + key,
                                headers={"cache-control": "no-store"})
        return FileResponse(
            p,
            media_type=MEDIA.get(p.suffix.lower(), "application/octet-stream"),
            headers=HDRS,
        )

    return api
