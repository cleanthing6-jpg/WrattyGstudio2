#!/usr/bin/env python3
"""Probe Treblo API shapes using the key in TREBLO_API_KEY.
Only reads what exists - no generation calls, no credit cost."""
import os, sys, pathlib, requests, json

BASE = "https://api.treblo.com/v1"
KEY  = os.environ.get("TREBLO_API_KEY", "").strip() or sys.argv[1]
if not KEY.startswith("sonauto_"):
    sys.exit("expects key starting with 'sonauto_' (or paste as arg)")
H = {"Authorization": "Bearer " + KEY}
J = {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}

def show(r):
    b = r.text[:400].replace("\n", " ")
    print("  HTTP", r.status_code, "->", b)

print("=== /v1 (root) ===")
show(requests.get(BASE, headers=H, timeout=30))

print("\n=== GET  /v1/uploads (is it GET? → expect 405) ===")
show(requests.get(BASE + "/uploads", headers=H, timeout=30))

print("\n=== OPTIONS /v1/uploads ===")
show(requests.options(BASE + "/uploads", headers=H, timeout=30))

print("\n=== POST /v1/generations/v3/reference  ->  OPTIONS  ===")
show(requests.options(BASE + "/generations/v3/reference", headers=J, timeout=30))
