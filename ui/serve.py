"""
Mission-control UI server. Standalone: doesn't change Michael's code.

Serves this folder on :8100 and forwards /api/* to the bench server
(default http://127.0.0.1:8000/resistor), so the page never hits CORS.

  python ui/serve.py                         # live: proxy to the resistor demo
  python ui/serve.py --upstream http://127.0.0.1:8000/sim
  open http://127.0.0.1:8100                 # live
  open http://127.0.0.1:8100/?mock=1         # replay a recorded Gemma run, no server needed
"""
import argparse
import http.server
import socketserver
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def make_handler(upstream):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(HERE), **k)

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _proxy(self, method):
            body = None
            if method == "POST":
                body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
            req = urllib.request.Request(upstream + self.path, data=body, method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    data, status, ctype = r.read(), r.status, r.headers.get("Content-Type", "application/json")
            except urllib.error.HTTPError as e:
                data, status, ctype = e.read(), e.code, e.headers.get("Content-Type", "application/json")
            except Exception as e:
                data, status, ctype = ('{"detail":"bench server unreachable: %s"}' % e).encode(), 502, "application/json"
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self._proxy("GET")
            return super().do_GET()

        def do_POST(self):
            if self.path.startswith("/api/"):
                return self._proxy("POST")
            self.send_error(404)

    return Handler


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--upstream", default="http://127.0.0.1:8000/resistor")
    a = ap.parse_args()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", a.port), make_handler(a.upstream.rstrip("/"))) as s:
        print(f"Mission control: http://127.0.0.1:{a.port}   (mock: /?mock=1)   upstream: {a.upstream}")
        s.serve_forever()
