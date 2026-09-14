import json, sys, importlib.util
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        out = {"python": sys.version.split()[0], "path": sys.path}
        for mod in ("numpy", "requests", "pedalboard"):
            try:
                out["spec_" + mod] = str(importlib.util.find_spec(mod))
            except Exception as e:
                out["spec_" + mod] = "FAIL " + repr(e)
            try:
                m = __import__(mod)
                out[mod] = "OK " + str(getattr(m, "__version__", "?"))
            except Exception as e:
                out[mod] = "FAIL " + repr(e)
        try:
            from pedalboard import Reverb, Compressor
            out["effects"] = "OK"
        except Exception as e:
            out["effects"] = "FAIL " + repr(e)
        body = json.dumps(out, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
