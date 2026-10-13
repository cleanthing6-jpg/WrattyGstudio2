"""Byte storage for mix outputs. R2 primary, Modal volume fallback."""
import os
import pathlib

MOUNT = pathlib.Path(os.environ.get("MIX_MOUNT", "/mixes"))
BASE = os.environ.get("FILES_BASE_URL",
                      "https://wrattyg--wratty-files-web.modal.run").rstrip("/")
VOLUME = os.environ.get("MIX_VOLUME", "wratty-mixes")

R2_ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
R2_KEY = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
R2_SECRET = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET_NAME", "")
R2_HOST = "r2.wratty.internal"

_r2_client = None


def _r2():
    global _r2_client
    if _r2_client is None:
        import boto3
        from botocore.config import Config
        _r2_client = boto3.client(
            "s3",
            endpoint_url="https://%s.r2.cloudflarestorage.com" % R2_ACCOUNT,
            aws_access_key_id=R2_KEY,
            aws_secret_access_key=R2_SECRET,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
    return _r2_client


def r2_enabled():
    return bool(R2_ACCOUNT and R2_KEY and R2_SECRET and R2_BUCKET)


def volume_enabled():
    return MOUNT.is_dir()


def _content_type(name):
    n = name.lower()
    if n.endswith(".mp3"): return "audio/mpeg"
    if n.endswith(".flac"): return "audio/flac"
    if n.endswith(".wav"): return "audio/wav"
    return "application/octet-stream"


def put(blob, name):
    if isinstance(blob, (bytes, bytearray)):
        data = bytes(blob)
    elif hasattr(blob, "read"):
        data = blob.read()
    else:
        data = pathlib.Path(blob).read_bytes()

    if r2_enabled():
        try:
            key = "mixes/%s" % name
            _r2().put_object(Bucket=R2_BUCKET, Key=key, Body=data,
                             ContentType=_content_type(name))
            return "https://%s/%s" % (R2_HOST, key)
        except Exception as _e:
            print("R2 put failed, falling back to volume: %s" % str(_e)[:200], flush=True)

    if not volume_enabled():
        raise RuntimeError("no R2 creds and volume not mounted at %s" % MOUNT)
    dst = MOUNT / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, dst)
    _commit_volume()
    return "%s/f/%s" % (BASE, name)


def _commit_volume():
    try:
        import modal
        modal.Volume.from_name(VOLUME).commit()
    except Exception as e:
        print("blobstore commit failed: %s" % e, flush=True)


def commit():
    if not r2_enabled():
        _commit_volume()
