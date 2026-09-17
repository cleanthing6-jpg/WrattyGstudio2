from pathlib import Path
import sys

P = Path("src/components/AiMixer.tsx")
s = P.read_text(encoding="utf-8")
notes = []

def rep1(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        sys.exit("ABORT [%s]: matched %d times (need 1) - NOTHING written" % (label, n))
    s = s.replace(old, new, 1)
    notes.append("ok  " + label)

rep1(
'''  async function masterTrack(mixUrl: string) {
    if (!mixUrl || busy) return;
    setBusy(true); setErr(""); setMasterUrl("");
    setMsg("Creating mastering preview...");''',
'''  async function masterTrack(mixUrl: string, full = false) {
    if (!mixUrl || busy) return;
    setBusy(true); setErr(""); setMasterUrl("");
    setMsg(full ? "Creating your full master - this can take a few minutes..." : "Creating mastering preview...");''',
"masterTrack takes a full flag")

rep1(
'        body: JSON.stringify({ url: mixUrl, style, loudness: roexLoudness }),',
'        body: JSON.stringify({ url: mixUrl, style, loudness: roexLoudness, preview: !full }),',
"request sends preview:!full")

rep1(
'''      for (let i = 0; i < 30; i++) {
        await new Promise((res) => setTimeout(res, 5000));
        const s2 = await fetch("/api/roex-master?taskId=" + encodeURIComponent(data.taskId));''',
'''      for (let i = 0; i < (full ? 120 : 30); i++) {
        await new Promise((res) => setTimeout(res, 5000));
        const s2 = await fetch("/api/roex-master?taskId=" + encodeURIComponent(data.taskId));''',
"poll 30 -> 120 tries for a full master")

rep1(
'      throw new Error("Mastering preview timed out");',
'      throw new Error(full ? "Full master timed out - try again" : "Mastering preview timed out");',
"timeout message reflects the mode")

rep1(
'            onClick={() => masterTrack(finalUrl)}',
'            onClick={() => masterTrack(finalUrl, true)}',
"button now requests the full master")

P.write_text(s, encoding="utf-8")
for n in notes:
    print("  " + n)
print("PATCHED - revert: git checkout -- src/components/AiMixer.tsx")
