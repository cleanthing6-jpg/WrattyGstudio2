#!/usr/bin/env python3
# Usage: python treblo_genre.py ref.wav 1.0   (2nd arg = your best-sounding scale)
import os, sys, time, json, pathlib, requests

BASE  = "https://api.treblo.com/v1"
KEY   = os.environ.get("TREBLO_API_KEY", "").strip()
REF   = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "ref.wav")
SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
OUT   = pathlib.Path("beats"); OUT.mkdir(exist_ok=True)
POLL, TIMEOUT = 5, 1800

P_PLAIN = ("Club-ready South African amapiano instrumental. Log-drum bounce, rolling "
           "bass, syncopated shakers, airy pads, spacious reverb, hypnotic dancefloor groove.")

P_FULL = ("Pure South African amapiano instrumental, 112 BPM. Signature log drum bass with "
          "pitch-sliding hits, sparse syncopated kick, jazzy amapiano piano chords and "
          "plucked stabs, soft shakers and rim clicks, airy pad swells, deep sub-bass, "
          "spacious reverb, hypnotic dancefloor groove. Not afrobeats, not afro house, "
          "not EDM, no vocals.")

P_FULL += (" Hard instrumental only: no singing, no vocal chops, no vocal samples, "
           "do not reproduce the reference melody, lyrics or ad-libs.")

_ALL = {
    "A_one_tag":     (["amapiano"], P_PLAIN, True),
    "B_full_prompt": (["amapiano"], P_FULL,  True),
    "C_no_ref":      (["amapiano"], P_FULL,  False),
}
_pick = os.environ.get("RUN", "B_full_prompt")
assert _pick in _ALL, "RUN must be one of: " + ", ".join(_ALL)
VARIANTS = [(_pick,) + _ALL[_pick]]

AUTH = {"Authorization": "Bearer " + KEY}
JSON = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

def show(tag, r):
    print("   ", tag, "HTTP", r.status_code, r.text[:400].replace("\n", " "))

if not KEY:
    sys.exit("FAIL: TREBLO_API_KEY not set")
if not REF.exists():
    sys.exit("FAIL: " + str(REF) + " not found")

print("[1/2] uploading", REF.name, REF.stat().st_size, "bytes")
with REF.open("rb") as f:
    r = requests.post(BASE + "/uploads", headers=AUTH,
                      files={"file": (REF.name, f)}, timeout=180)
if r.status_code != 200:
    show("upload", r); sys.exit(1)
UID = r.json().get("audio_upload_id")
print("      audio_upload_id =", UID)

for name, tags, prompt, use_ref in VARIANTS:
    body = {"prompt": prompt, "tags": tags, "instrumental": True,
            "output_format": "wav", "length_range": [60, 90]}
    if use_ref:
        body["audio_upload_id"] = UID
        body["reference_scale"] = SCALE

    url = BASE + ("/generations/v3/reference" if use_ref else "/generations/v3")
    print("[2/2]", name, "(with reference)" if use_ref else "(text only)")
    r = requests.post(url, headers=JSON, json=body, timeout=120)
    if r.status_code != 200:
        show(name, r); continue

    tid = r.json().get("task_id")
    if not tid:
        show(name, r); continue
    (OUT / (name + ".taskid")).write_text(str(tid) + "\n")

    t0 = time.time(); status = "?"
    while time.time() - t0 < TIMEOUT:
        try:
            s = requests.get(BASE + "/generations/status/" + tid, headers=AUTH, timeout=60)
        except requests.exceptions.RequestException as e:
            print("      net error, retrying:", str(e)[:70])
            time.sleep(POLL); continue
        j = s.json() if s.status_code == 200 else "HTTP " + str(s.status_code)
        status = j.get("status", "?") if isinstance(j, dict) else str(j).strip('"').upper()
        if status.upper() in ("SUCCESS", "COMPLETED", "COMPLETE", "FAILED", "FAILURE", "ERROR"):
            break
        print("      ", status, int(time.time() - t0), "s", end="\r")
        time.sleep(POLL)
    print("      status:", status, str(int(time.time() - t0)) + "s")

    g = requests.get(BASE + "/generations/" + tid, headers=AUTH, timeout=60)
    (OUT / (name + ".json")).write_text(g.text)
    try:
        paths = g.json().get("song_paths") or []
    except Exception:
        paths = []
    print("      song_paths:", paths)

    for i, u in enumerate(paths):
        u = str(u)
        link = u if u.startswith("http") else BASE + "/" + u.lstrip("/")
        a = requests.get(link, timeout=300)
        if a.status_code == 200:
            f = OUT / (name + ("" if i == 0 else "-" + str(i)) + ".wav")
            f.write_bytes(a.content)
            print("      saved", f.name, len(a.content), "bytes")
        else:
            print("      download failed", a.status_code, link)

print("DONE ->", OUT.resolve())
