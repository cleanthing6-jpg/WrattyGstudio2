from pathlib import Path
import sys

P = Path("src/components/AiMixer.tsx")
s = P.read_text(encoding="utf-8")
notes = []

def swap(old, new, label):
    global s
    if new in s and old not in s:
        notes.append("skip %s (already applied)" % label)
        return
    n = s.count(old)
    if n != 1:
        sys.exit("ABORT [%s]: matched %d times (need 1) - NOTHING written" % (label, n))
    s = s.replace(old, new, 1)
    notes.append("ok  " + label)

swap(
'''  async function masterTrack(mixUrl: string) {
    if (!mixUrl || busy) return;
    setBusy(true); setErr(""); setMasterUrl("");
    setMsg("Creating mastering preview...");''',
'''  async function masterTrack(mixUrl: string, full = false) {
    if (!mixUrl || busy) return;
    setBusy(true); setErr(""); setMasterUrl("");
    setMsg(full ? "Creating your full master - this can take a few minutes..." : "Creating mastering preview...");''',
"masterTrack takes a full flag")

swap(
'        body: JSON.stringify({ url: mixUrl, style, loudness: roexLoudness }),',
'        body: JSON.stringify({ url: mixUrl, style, loudness: roexLoudness, preview: !full }),',
"request sends preview:!full")

swap(
'''      for (let i = 0; i < 30; i++) {
        await new Promise((res) => setTimeout(res, 5000));
        const s2 = await fetch("/api/roex-master?taskId=" + encodeURIComponent(data.taskId));''',
'''      for (let i = 0; i < (full ? 120 : 30); i++) {
        await new Promise((res) => setTimeout(res, 5000));
        const s2 = await fetch("/api/roex-master?taskId=" + encodeURIComponent(data.taskId));''',
"poll 30 -> 120 tries for a full master")

swap(
'      throw new Error("Mastering preview timed out");',
'      throw new Error(full ? "Full master timed out - try again" : "Mastering preview timed out");',
"timeout message reflects the mode")

# call site: OWNER gets the full render, everyone else keeps the 30s preview
for old, label in (('            onClick={() => masterTrack(finalUrl, true)}', "call site: true -> isOwner"),
                   ('            onClick={() => masterTrack(finalUrl)}', "call site -> isOwner")):
    if s.count(old) == 1:
        s = s.replace(old, '            onClick={() => masterTrack(finalUrl, isOwner)}', 1)
        notes.append("ok  " + label)
        break
else:
    if 'masterTrack(finalUrl, isOwner)' in s:
        notes.append("skip call site (already owner-gated)")
    else:
        sys.exit("ABORT: masterTrack(finalUrl...) call site not found")

P.write_text(s, encoding="utf-8")
for n in notes:
    print("  " + n)
print("PATCHED - revert: git checkout -- src/components/AiMixer.tsx")
