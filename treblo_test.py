#!/usr/bin/env python3
import os, sys, time, json, pathlib, requests

BASE = "https://api.treblo.com/v1"
KEY  = os.environ.get("TREBLO_API_KEY", "").strip()
REF  = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "ref.wav")
OUT  = pathlib.Path("beats")
OUT.mkdir(exist_ok=True)

PROMPT = ("Club-ready South African amapiano instrumental. Log-drum bounce, "
          "rolling bass, syncopated shakers, airy pads, spacious reverb, "
          "hypnotic dancefloor groove.")
TAGS   = ["amapiano", "afrobeats", "afro house", "dance", "club",
          "percussion", "drums", "shakers", "energetic"]
SCALES = [1.0, 2.5, 5.0]
POLL, TIMEOUT = 5, 420


def die(msg, r=None):
    print("FAIL:", msg)
    if r is not None:
        print("  HTTP", r.status_code)
        print("  ", r.text[:900].replace("\n", " "))
    sys.exit(1)


if not KEY:
    die("TREBLO_API_KEY not set -> export TREBLO_API_KEY=sonauto_...")
if not REF.exists():
    die(str(REF) + " not found")

H = {"Authorization": "Bearer " + KEY}

print("[1/2] uploading", REF, REF.stat().st_size, "bytes")
with REF.open("rb") as f:
    r = requests.post(BASE + "/uploads", headers=H,
                      files={"file": (REF.name, f)}, timeout=180)
if r.status_code != 200:
    die("upload rejected", r)

uid = r.json().get("audio_upload_id")
if not uid:
    die("no audio_upload_id in response", r)
print("      audio_upload_id =", uid)

for scale in SCALES:
    body = {
        "prompt": PROMPT,
        "tags": TAGS,
        "instrumental": True,
        "audio_upload_id": uid,
        "reference_scale": scale,
        "output_format": "wav",
        "length_range": [60, 90],
    }
    print("[2/2] reference_scale =", scale)
    r = requests.post(BASE + "/generations/v3/reference",
                      headers={"Authorization": "Bearer " + KEY,
                               "Content-Type": "application/json"},
                      json=body, timeout=120)
    if r.status_code != 200:
        die("submit failed for scale " + str(scale), r)

    tid = r.json().get("task_id")
    if not tid:
        die("no task_id returned", r)
    print("      task_id =", tid)

    t0 = time.time()
    while True:
        s = requests.get(BASE + "/generations/status/" + tid,
                         headers=H, timeout=60)
        if s.status_code != 200:
            die("status check failed", s)
        st = s.json()
        if isinstance(st, dict):
            st = st.get("status", "")
        if st == "SUCCESS":
            break
        if st in ("FAILURE", "FAILED", "ERROR"):
            die("generation failed: " + str(st), s)
        if time.time() - t0 > TIMEOUT:
            die("timed out after " + str(TIMEOUT) + "s")
        print("      ", st, round(time.time() - t0), "s")
        time.sleep(POLL)

    res = requests.get(BASE + "/generations/" + tid, headers=H, timeout=120)
    if res.status_code != 200:
        die("fetch failed", res)
    data = res.json()
    (OUT / ("treblo_s" + str(scale) + ".json")).write_text(json.dumps(data, indent=2))

    paths = data.get("song_paths") or []
    if not paths:
        print(json.dumps(data, indent=2)[:1200])
        die("no song_paths in result")
    audio = requests.get(paths[0], timeout=300).content
    out = OUT / ("amapiano_ref" + str(scale) + ".wav")
    out.write_bytes(audio)
    print("      saved", out.name, len(audio), "bytes")

print("DONE ->", OUT.resolve())
