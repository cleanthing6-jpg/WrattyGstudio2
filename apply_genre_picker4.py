from pathlib import Path
import ast, re, sys

AUTO, COMP = Path("fx-api/api/auto.py"), Path("src/components/AiMixer.tsx")
auto, tsx = AUTO.read_text(encoding="utf-8"), COMP.read_text(encoding="utf-8")

tree = ast.parse(auto); node = None
for n in tree.body:
    if isinstance(n, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == "PRESETS" for t in n.targets):
        node = n.value
if not isinstance(node, ast.Dict):
    sys.exit("ABORT: PRESETS not a dict")
slugs = {k.value for k in node.keys
         if isinstance(k, ast.Constant) and isinstance(k.value, str)}
print("ENGINE PRESETS:", ", ".join(sorted(slugs)))

MAP = {
    "afrobeat": "afrobeats", "afrobeats": "afrobeats",
    "hiphopgrime": "rap", "hiphop": "rap", "rap": "rap",
    "reggaedub": "afrobeats", "reggae": "afrobeats", "dancehall": "afrobeats",
    "pop": "pop", "electronic": "pop", "amapiano": "pop",
    "acoustic": "rnb", "rockindie": "rnb", "rock": "rnb", "rnb": "rnb",
    "other": "neutral", "neutral": "neutral", "auto": "neutral",
}
def slug_of(t):
    return MAP.get(re.sub(r"[^a-z0-9]", "", str(t).lower()))

m = re.search(r"(const\s+STYLES\s*(?::[^=]*)?=\s*\[)([\s\S]*?)(\n\s*\];)", tsx)
if not m:
    sys.exit("ABORT: const STYLES [...] not found")
body = m.group(2)
entries = list(re.finditer(r"\{[^{}]*\}", body, re.S))
if not entries:
    sys.exit("ABORT: no entries in STYLES")

newbody, rows, bad = body, [], []
for e in entries:
    t = e.group(0)
    vl = re.search(r'value:\s*"([^"]*)"', t)
    ll = re.search(r'label:\s*"([^"]*)"', t)
    if not vl or not ll:
        sys.exit("ABORT: entry missing value/label -> " + t[:90])
    old, label = vl.group(1), ll.group(1)
    new = slug_of(old)
    if not new or new not in slugs:
        bad.append("%s (%s)" % (label, old))
        continue
    rows.append((label, old, new))
    newbody = newbody.replace('value: "%s"' % old, 'value: "%s"' % new, 1)

if bad:
    sys.exit("ABORT: unmapped -> " + ", ".join(bad))

tsx = tsx[:m.start(2)] + newbody + tsx[m.end(2):]

first_old, first_new = rows[0][1], rows[0][2]
if 'useState("%s")' % first_old not in tsx:
    sys.exit('ABORT: useState("%s") default not found' % first_old)
tsx = tsx.replace('useState("%s")' % first_old, 'useState("%s")' % first_new, 1)

OLD = "body: JSON.stringify({ stems: prepared, loudness: roexLoudness }),"
NEW = "body: JSON.stringify({ stems: prepared, loudness: roexLoudness, preset: style }),"
if tsx.count(OLD) != 1:
    sys.exit("ABORT: /api/mix body matched %d times" % tsx.count(OLD))
tsx = tsx.replace(OLD, NEW, 1)

COMP.write_text(tsx, encoding="utf-8")
for label, old, new in rows:
    print("  %-34s %-14s -> %s" % (label[:34], old, new))
print("PATCHED - revert: git checkout -- src/components/AiMixer.tsx")
