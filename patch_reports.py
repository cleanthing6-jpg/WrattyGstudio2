import pathlib, sys

src = pathlib.Path("modal_mix.py")
text = src.read_text()

OLD = '''            print("MIXREPORT " + _j.dumps(_safe, default=str)[:6000], flush=True)
        except Exception:
            pass'''

NEW = '''            _rpt = _j.dumps(_safe, default=str)
            print("MIXREPORT " + _rpt[:6000], flush=True)
            try:
                _rp = os.path.join("/mixes", "reports", "%s.json" % job_id)
                os.makedirs(os.path.dirname(_rp), exist_ok=True)
                with open(_rp, "w") as _f:
                    _f.write(_rpt)
                print("REPORT_SAVED " + _rp, flush=True)
                try:
                    mixvol.commit()
                except Exception as _ce:
                    print("report commit failed: %s" % _ce, flush=True)
            except Exception as _re:
                print("REPORT_SAVE_ERR " + str(_re)[:200], flush=True)
        except Exception:
            pass'''

n = text.count(OLD)
if n == 0:
    print("ABORT: target block not found — file already patched or modified")
    sys.exit(1)
if n > 1:
    print("ABORT: target block appears %d times" % n)
    sys.exit(1)

bak = src.with_suffix(src.suffix + ".bak")
bak.write_text(text)
print("backup:", bak)

src.write_text(text.replace(OLD, NEW))
print("OK: patched modal_mix.py")
