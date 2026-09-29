import datetime, py_compile, shutil, sys, pathlib

MIX = pathlib.Path("fx-api/api/mix.py")
MM = pathlib.Path("modal_mix.py")

OLD_PUT = '''def put(p, name, ctype="audio/wav"):
    t = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not t:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN missing")
    with open(p, "rb") as fh:
        r = requests.put(BLOB + "/" + name, data=fh, timeout=600,
                         headers={"authorization": "Bearer " + t,
                                  "x-api-version": "7", "x-content-type": ctype,
                                  "x-add-random-suffix": "1", "Content-Type": ctype})
    if r.status_code >= 300:
        raise RuntimeError("blob " + r.text[:150])
    return r.json().get("url", "")
'''

NEW_PUT = '''def put(p, name, ctype="audio/wav"):
    # Prefer the Modal volume: no Vercel Blob data-transfer meter. Any failure
    # falls through to Blob so a bad deploy can never break a mix.
    try:
        import blobstore
        if blobstore.enabled():
            url = blobstore.put(p, name)
            print("PUT modal %s" % url, flush=True)
            return url
    except Exception as e:
        print("PUT modal failed (%s) - using blob" % str(e)[:200], flush=True)
    t = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not t:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN missing")
    with open(p, "rb") as fh:
        r = requests.put(BLOB + "/" + name, data=fh, timeout=600,
                         headers={"authorization": "Bearer " + t,
                                  "x-api-version": "7", "x-content-type": ctype,
                                  "x-add-random-suffix": "1", "Content-Type": ctype})
    if r.status_code >= 300:
        raise RuntimeError("blob " + r.text[:150])
    return r.json().get("url", "")
'''

OLD_MM = '''SECRET = modal.Secret.from_name("wratty-mix")
jobs = modal.Dict.from_name("wratty-mix-jobs", create_if_missing=True)


@app.function(image=image, cpu=2.0, memory=8192, timeout=3600, secrets=[SECRET])
def run_mix(job_id: str, stems: list, loudness: str, preset: str = "neutral", max_seconds: float = 0):
    import sys
    import traceback

    sys.path.insert(0, "/root/api")
    import mix

    jobs[job_id] = {"status": "running"}
    try:
        res = mix.do_mix(stems, loudness, job_id, max_seconds, preset)
'''

NEW_MM = '''SECRET = modal.Secret.from_name("wratty-mix")
jobs = modal.Dict.from_name("wratty-mix-jobs", create_if_missing=True)

# Mix renders are written here and served by the separate wratty-files app.
mixvol = modal.Volume.from_name("wratty-mixes", create_if_missing=True)


@app.function(image=image, cpu=2.0, memory=8192, timeout=3600, secrets=[SECRET],
              volumes={"/mixes": mixvol})
def run_mix(job_id: str, stems: list, loudness: str, preset: str = "neutral", max_seconds: float = 0):
    import sys
    import traceback

    sys.path.insert(0, "/root/api")
    import mix

    jobs[job_id] = {"status": "running"}
    try:
        res = mix.do_mix(stems, loudness, job_id, max_seconds, preset)
        try:
            mixvol.commit()      # publish the render to wratty-files
        except Exception as _e:
            print("volume commit failed: %s" % _e, flush=True)
'''


def edit(path, old, new, label):
    s = path.read_text()
    n = s.count(old)
    if n != 1:
        print("ABORT %s: found %d matches (expected 1) - nothing written" % (label, n))
        return False
    bak = str(path) + ".bak." + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, bak)
    path.write_text(s.replace(old, new))
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as e:
        shutil.copy2(bak, path)
        print("ABORT %s: compile failed, restored: %s" % (label, e))
        return False
    print("PATCHED %-18s backup %s" % (label, bak))
    return True


ok = edit(MIX, OLD_PUT, NEW_PUT, "mix.py put()")
ok = edit(MM, OLD_MM, NEW_MM, "modal_mix.py vol") and ok
print("PATCH OK" if ok else "PATCH FAILED")
sys.exit(0 if ok else 1)
