from pathlib import Path
import re, sys

def load(p):
    f = Path(p)
    if not f.exists(): sys.exit("ABORT: %s missing" % p)
    return f.read_text(encoding="utf-8")

def rep(s, old, new, path, label):
    n = s.count(old)
    if n != 1: sys.exit("ABORT %s: '%s' matched %d (need 1)" % (path, label, n))
    print("  ok  %-18s %s" % (path.split('/')[-1], label))
    return s.replace(old, new, 1)

def resub(s, pat, new, path, label):
    s2, n = re.subn(pat, new, s, flags=re.S)
    if n != 1: sys.exit("ABORT %s: '%s' matched %d (need 1)" % (path, label, n))
    print("  ok  %-18s %s" % (path.split('/')[-1], label))
    return s2

P1 = "src/app/api/mix/route.ts"
m = load(P1)
m = rep(m, "async function mixer(path: string, init: RequestInit, tries: number, retryCodes: number[]) {",
        "async function mixer(path: string, init: RequestInit, tries: number, retryCodes: number[], ms = 20000) {",
        P1, "mixer takes ms")
m = rep(m, "signal: AbortSignal.timeout(120000),", "signal: AbortSignal.timeout(ms),", P1, "120s -> ms")
m = resub(m, r"\}, \d+, \[502, 503\]\)", "}, 1, [502, 503], 45000)", P1, "POST 1 try 45s")
m = resub(m, r"\}, \d+, \[502, 503, 504\]\)", "}, 2, [502, 503, 504], 20000)", P1, "GET 2 tries 20s")

P2 = "src/app/api/roex-master/route.ts"
r = rep(load(P2), "preview: false", "preview: true", P2, "ask for 30s preview")

P3 = "src/components/AiMixer.tsx"
a = rep(load(P3),
  "for (let i = 0; i < 30; i++) {\n        await new Promise((res) => setTimeout(res, 5000));",
  'for (let i = 0; i < 120; i++) {\n        await new Promise((res) => setTimeout(res, 5000));\n        setMsg("Mastering… " + (i + 1) + " of 120");',
  P3, "poll 150s -> 10min")

Path(P1).write_text(m, encoding="utf-8")
Path(P2).write_text(r, encoding="utf-8")
Path(P3).write_text(a, encoding="utf-8")
print("PATCHED - revert: git checkout -- src/app/api/mix/route.ts src/app/api/roex-master/route.ts src/components/AiMixer.tsx")
