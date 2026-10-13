import json, glob
files = sorted(glob.glob("bench/*.json"))
if not files:
    print("no reports in bench/"); raise SystemExit
print(f"{'file':22s} {'preset':9s} {'mode':10s} {'lufs':>7s} {'tp':>6s} {'clarity':>7s} {'corr':>6s} {'pass':>5s}")
for f in files:
    r = json.load(open(f))
    d = r.get("report") or {}
    chk = d.get("check") or {}
    print(f"{f.split('/')[-1]:22s} "
          f"{(r.get('preset') or '?'):9s} "
          f"{(r.get('mode') or '?'):10s} "
          f"{str(d.get('final_lufs','?')):>7s} "
          f"{str(d.get('final_true_peak_dbfs','?')):>6s} "
          f"{str(chk.get('clarity','?')):>7s} "
          f"{str(chk.get('corr','?')):>6s} "
          f"{str(chk.get('pass','?')):>5s}")
