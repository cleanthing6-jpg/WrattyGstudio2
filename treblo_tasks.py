#!/usr/bin/env python3
"""Fetch finished Treblo generations by task id. Costs nothing.
Usage: python treblo_tasks.py [task_id ...]   (no args = all beats/*.taskid)"""
import os, sys, pathlib, requests

BASE = "https://api.treblo.com/v1"
KEY  = os.environ.get("TREBLO_API_KEY", "").strip()
OUT  = pathlib.Path("beats"); OUT.mkdir(exist_ok=True)
if not KEY:
    sys.exit("FAIL: TREBLO_API_KEY not set")
A = {"Authorization": "Bearer " + KEY}

ids = sys.argv[1:] or [f.read_text().strip() for f in sorted(OUT.glob("*.taskid"))]
if not ids:
    sys.exit("no ids - usage: python treblo_tasks.py <task_id>")

for tid in ids:
    s = requests.get(BASE + "/generations/status/" + tid, headers=A, timeout=60)
    print(tid, "->", s.text[:120])
    g = requests.get(BASE + "/generations/" + tid, headers=A, timeout=60)
    (OUT / (tid + ".json")).write_text(g.text)
    try:
        paths = g.json().get("song_paths") or []
    except Exception:
        paths = []
    for i, u in enumerate(paths):
        u = str(u)
        link = u if u.startswith("http") else BASE + "/" + u.lstrip("/")
        a = requests.get(link, timeout=300)
        f = OUT / (tid[:8] + ("" if i == 0 else "-" + str(i)) + ".wav")
        f.write_bytes(a.content)
        print("   saved", f.name, len(a.content), "bytes")
