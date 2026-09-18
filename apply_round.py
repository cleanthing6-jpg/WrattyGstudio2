from pathlib import Path
import ast

P = Path("fx-api/api/auto.py")
s = P.read_text(encoding="utf-8")
log = []

def swap(old, new, label):
    global s
    if new in s and old not in s:
        log.append("skip  %s (already applied)" % label); return
    n = s.count(old)
    if n != 1:
        log.append("MISS  %s (anchor matched %d - skipped)" % (label, n)); return
    s = s.replace(old, new, 1)
    log.append("ok    %s" % label)

swap('target = {"adlib": lead - 8.0, "backing": lead - 10.0}',
     'target = {"adlib": lead - 8.0, "backing": lead - 8.0}',
     "backing target lead-10 -> lead-8")

swap('gain = float(np.clip(min(tgt - cur, head), -6.0, 18.0))',
     'gain = float(np.clip(min(tgt - cur, head), -6.0, 22.0))',
     "backing lift cap 18 -> 22")

swap('SEND_PLATE = 10.0 ** (-14.0 / 20.0)   # plate send',
     'SEND_PLATE = 10.0 ** (-12.0 / 20.0)   # plate send',
     "plate send -14 -> -12 dB")

swap('SEND_SLAP  = 10.0 ** (-14.0 / 20.0)   # slap send',
     'SEND_SLAP  = 10.0 ** (-11.0 / 20.0)   # slap send',
     "delay send -14 -> -11 dB")

swap('Delay(delay_seconds=d / float(sr), feedback=0.18, mix=1.0)',
     'Delay(delay_seconds=d / float(sr), feedback=0.22, mix=1.0)',
     "delay feedback 0.18 -> 0.22")

swap('''    beat_s = 60.0 / max(bpm, 40.0)
    d = max(int(sr * 0.04), min(int(sr * beat_s * 0.5), int(sr * 0.35)))''',
     '''    try:
        bpm = float(bpm)
    except (TypeError, ValueError):
        bpm = 100.0
    if not np.isfinite(bpm) or bpm <= 0:
        bpm = 100.0
    bpm = float(min(max(bpm, 40.0), 240.0))
    beat_s = 60.0 / bpm
    d = max(int(sr * 0.04), min(int(sr * beat_s * 0.5), int(sr * 0.60)))''',
     "tempo guard + delay cap 350 -> 600 ms")

swap('"sat": 0.6, "width": 1.2},',  '"sat": 0.6, "width": 1.35},', "backing width 1.2 -> 1.35")
swap('"sat": 1.2, "width": 1.30},', '"sat": 1.2, "width": 1.45},', "adlib width 1.30 -> 1.45")

P.write_text(s, encoding="utf-8")
ast.parse(s)
for line in log:
    print("  " + line)

t = P.read_text(encoding="utf-8")
print("--- STATE ---")
for label, tok in [("backing lead-8", '"backing": lead - 8.0'),
                   ("lift cap 22", "-6.0, 22.0"),
                   ("tempo guard", "isfinite(bpm)"),
                   ("ambience raised", "-11.0 / 20.0"),
                   ("widths widened", '"width": 1.35')]:
    print("  %-16s %s" % (label, "YES" if tok in t else "no"))
print("SYNTAX OK")
