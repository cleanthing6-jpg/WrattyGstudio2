#!/usr/bin/env python3
import json, os, sys, time, pathlib, requests

API  = "https://api.elevenlabs.io/v1"
KEY  = os.environ.get("ELEVENLABS_API_KEY", "").strip()
REF  = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "ref.wav")
TAG  = REF.stem
OUT  = pathlib.Path("beats")
OUT.mkdir(exist_ok=True)

MODEL, DUR_MS, RUNS = "music_v2_5", 20000, 3

STYLE = (
    "Create a high-energy, club-ready South African amapiano instrumental. "
    "Use the uploaded vocal only as a guide for tempo, groove, phrasing and energy. "
    "Do not reproduce or double its melody; no vocals. Build an original log-drum groove "
    "with rolling low bass, syncopated shakers and percussion, airy pads, spacious reverb, "
    "and a hypnotic dancefloor pulse."
)
TAGS = ["amapiano", "South African", "club", "log drums",
        "syncopated percussion", "airy pads"]


def die(msg, r=None):
    print("FAIL:", msg)
    if r is not None:
        print("  HTTP", r.status_code)
        print("  ", r.text[:900].replace("\n", " "))
    sys.exit(1)


if not KEY:
    die("ELEVENLABS_API_KEY not set -> export ELEVENLABS_API_KEY=sk_...")
if not REF.exists():
    die(str(REF) + " not found - run the ffmpeg prep step first")

H = {"xi-api-key": KEY}

print("[1/2] uploading", REF, REF.stat().st_size, "bytes")
with REF.open("rb") as f:
    r = requests.post(API + "/music/upload", headers=H,
                      files={"file": (REF.name, f, "audio/wav")}, timeout=180)
if r.status_code != 200:
    die("upload rejected", r)

song_id = r.json().get("song_id")
if not song_id:
    die("no song_id in response -> field names may differ", r)
print("      song_id =", song_id)

payload = {
    "model_id": MODEL,
    "composition_plan": {"chunks": [{
        "text": STYLE,
        "duration_ms": DUR_MS,
        "positive_styles": TAGS,
        "conditioning_ref": {"song_id": song_id,
                             "range": {"start_ms": 0, "end_ms": DUR_MS - 1000}},
        "condition_strength": "high",
    }]},
}
(OUT / (TAG + "_plan.json")).write_text(json.dumps(payload, indent=2))

print("[2/2] generating", RUNS, "x")
for i in range(1, RUNS + 1):
    t = time.time()
    r = requests.post(API + "/music",
                      headers={"xi-api-key": KEY, "Content-Type": "application/json"},
                      json=payload, timeout=600)
    if r.status_code != 200:
        die("generation " + str(i) + " failed", r)
    out = OUT / ("amapiano_" + TAG + "_" + str(i) + ".mp3")
    out.write_bytes(r.content)
    print("      [" + str(i) + "/" + str(RUNS) + "]", out.name,
          len(r.content), "bytes", round(time.time() - t), "s")

print("DONE ->", OUT.resolve())
