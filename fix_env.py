import json, os, urllib.request
from urllib.error import HTTPError

RK = os.environ.get("RK") or "rnd_0Ks3p1TDkHjqoj4ZbuCDGCVmAFmX"
B = "https://api.render.com/v1"
MIX = "srv-dak2m9oae00c73ermmeg"

def local(k):
    # root file FIRST - fx-api/.env.local holds a junk FX_INTERNAL_SECRET
    for f in (".env.local", "fx-api/.env.local"):
        if os.path.exists(f):
            for l in open(f):
                if l.startswith(k + "="):
                    v = l.split("=", 1)[1].strip().strip('"').strip("'")
                    if v:
                        return v
    return ""

def call(u, method="GET", data=None):
    r = urllib.request.Request(u, method=method)
    r.add_header("Authorization", "Bearer " + RK)
    r.add_header("Accept", "application/json")
    r.add_header("Content-Type", "application/json")
    body = json.dumps(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(r, body, timeout=120) as x:
            return x.status, x.read()[:200].decode()
    except HTTPError as e:
        return e.code, e.read().decode()[:200]

sec = local("FX_INTERNAL_SECRET")
blob = local("BLOB_READ_WRITE_TOKEN")
print("secret chars:", len(sec), "| blob chars:", len(blob))
if not sec or not blob:
    raise SystemExit("missing local value - paste this output")

for k, v in (("FX_INTERNAL_SECRET", sec), ("BLOB_READ_WRITE_TOKEN", blob)):
    st, o = call(B + "/services/" + MIX + "/env-vars/" + k, "PUT", {"value": v})
    print(k, "->", st, o)

print("deploy:", call(B + "/services/" + MIX + "/deploys", "POST", {})[0])

# make both local files agree so the junk can never be picked again
for f in (".env.local", "fx-api/.env.local"):
    if not os.path.exists(f):
        continue
    lines = [l for l in open(f).read().splitlines() if not l.startswith("FX_INTERNAL_SECRET=")]
    lines.append("FX_INTERNAL_SECRET=" + sec)
    open(f, "w").write("\n".join(lines) + "\n")
    print("rewrote FX_INTERNAL_SECRET in", f)
print("DONE - wait for deploy, then run mix_call.py")
