from pathlib import Path
import sys

def load(p):
    f = Path(p)
    if not f.exists(): sys.exit("ABORT: %s missing" % p)
    return f.read_text(encoding="utf-8")

def rep(s, old, new, path, label):
    n = s.count(old)
    if n != 1: sys.exit("ABORT %s: '%s' matched %d (need 1)" % (path, label, n))
    print("  ok  %-16s %s" % (path.split('/')[-1], label))
    return s.replace(old, new, 1)

P1 = "src/app/api/mix/route.ts"
m = load(P1)
m = rep(m, "async function mixer(path: string, init: RequestInit, tries: number, retryCodes: number[]) {",
        "async function mixer(path: string, init: RequestInit, tries: number, retryCodes: number[], ms = 45000) {", P1, "default 45s")
m = rep(m, "signal: AbortSignal.timeout(120000),", "signal: AbortSignal.timeout(ms),", P1, "120s -> ms")
m = rep(m, 'const r = await mixer("/?id=" + encodeURIComponent(row.runner_job || ""), { method: "GET" }, 4, [502, 503, 504]);',
        'const r = await mixer("/?id=" + encodeURIComponent(row.runner_job || ""), { method: "GET" }, 1, [502, 503, 504], 20000);', P1, "GET 1 try 20s")

P2 = "src/app/api/roex-master/route.ts"
r = load(P2)
r = rep(r, 'return NextResponse.json({ status: "done", previewUrl: d.url });',
        'return NextResponse.json({ status: "done", url: d.url, previewUrl: d.url });', P2, "done response carries url")
r = rep(r, "preview: false", "preview: true", P2, "ask for 30s preview")

P3 = "src/components/AiMixer.tsx"
a = load(P3)
a = rep(a, 'if (st.masterUrl || st.url) { setMasterUrl(st.masterUrl || st.url); setMsg("Master ready"); return; }',
        'const got = st.masterUrl || st.url || st.previewUrl;\n        if (got) { setMasterUrl(got); setMsg("Master ready"); return; }', P3, "accept previewUrl")

Path(P1).write_text(m, encoding="utf-8")
Path(P2).write_text(r, encoding="utf-8")
Path(P3).write_text(a, encoding="utf-8")
print("PATCHED - revert: git checkout -- src/app/api/mix/route.ts src/app/api/roex-master/route.ts src/components/AiMixer.tsx")
