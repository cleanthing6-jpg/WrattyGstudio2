from pathlib import Path
import ast, sys

P = Path("fx-api/api/auto.py")
s = P.read_text(encoding="utf-8")

A1 = "# ---------- polish additions ----------"
if s.count(A1) != 1:
    sys.exit("ABORT: polish-additions anchor matched %d" % s.count(A1))

MASTER = '''# ---------- full-mix master bus ----------

WIDEN_MASTER = 1.10


def _master(x, sr, rep, loud="MEDIUM"):
    """Master a finished stereo mix. No vocal EQ, no role chain, no low-cut
    below 20 Hz. Rumble guard -> tone polish -> modest width. mix.py adds the
    glue, the LUFS normalise and the true-peak limiter on top."""
    a = np.asarray(x, dtype=np.float32)
    if a.ndim == 1:
        a = a[None, :]
    moves = []
    try:
        a = Pedalboard([HighpassFilter(cutoff_frequency_hz=20.0)])(a, sr).astype(np.float32)
        moves.append(["hpf", 20.0])
    except Exception:
        pass
    try:
        a2, pst = polish.dynamic_eq(a, sr, get_stats=True)
        a = np.asarray(a2, dtype=np.float32)
        rep["polish"] = pst
        moves.append(["polish_eq", "on"])
    except Exception as e:
        rep["polish_error"] = str(e)[:160]
    try:
        a = _widen(a, sr, WIDEN_MASTER)
        moves.append(["width", WIDEN_MASTER])
    except Exception:
        pass
    rep["master_chain"] = moves
    return _headroom(a, -1.0), rep


'''
s = s.replace(A1, MASTER + A1, 1)

A2 = '    _oth = groups.get("other") or []\n    if _oth:'
if s.count(A2) != 1:
    sys.exit("ABORT: other-fold anchor matched %d" % s.count(A2))
NEW2 = ('    _oth = groups.get("other") or []\n'
        '    if (beat is None and _oth\n'
        '            and not any(groups.get(r) for r in ROLE_VOCALS)):\n'
        '        rep["mode"] = "master"\n'
        '        rep["note"] = "single full-mix stem - master bus, no vocal chain"\n'
        '        return _master(_sum(_oth), sr, rep, loud)\n'
        '    if _oth:')
s = s.replace(A2, NEW2, 1)

P.write_text(s, encoding="utf-8")
ast.parse(s)
print("PATCHED: _master() added; master dispatch runs before the backing fold")
print("revert: git checkout -- fx-api/api/auto.py")
