"""Byte storage on a Modal Volume - replaces Vercel Blob for mix outputs.

Writes land in the mounted volume; the separate app in modal_files.py
("wratty-files") serves them over HTTPS with Range support. Any failure here
is caught by put() in mix.py, which falls back to Vercel Blob.
"""
import os
import pathlib

MOUNT = pathlib.Path(os.environ.get("MIX_MOUNT", "/mixes"))
BASE = os.environ.get("FILES_BASE_URL",
                      "https://wrattyg--wratty-files-web.modal.run").rstrip("/")
VOLUME = os.environ.get("MIX_VOLUME", "wratty-mixes")


def enabled():
    """True only when the volume is actually mounted into this container."""
    return MOUNT.is_dir()


def put(blob, name):
    """blob: bytes | file-like | path.  name: key, e.g. 'fx/<uuid>-mix-high.mp3'."""
    if not enabled():
        raise RuntimeError("volume not mounted at %s" % MOUNT)
    if isinstance(blob, (bytes, bytearray)):
        data = bytes(blob)
    else:
        data = blob.read() if hasattr(blob, "read") else pathlib.Path(blob).read_bytes()
    dst = MOUNT / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, dst)      # atomic - wratty-files can never serve half a file
    commit()
    return "%s/f/%s" % (BASE, name)


def commit():
    """Publish the write so the wratty-files app sees it. Best effort."""
    try:
        import modal
        modal.Volume.from_name(VOLUME).commit()
    except Exception as e:
        print("blobstore commit failed: %s" % e, flush=True)
