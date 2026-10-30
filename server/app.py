"""Small read-only development API. Bind locally unless explicitly configured."""
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import transit


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        params = parse_qs(url.query)
        query = lambda name: params.get(name, [""])[0]
        parts = [unquote(p) for p in url.path.strip("/").split("/")]
        try:
            if parts == ["api", "status"]:
                result = transit.status()
            elif parts == ["api", "routes"]:
                result = transit.routes(query("q"))
            elif len(parts) == 3 and parts[:2] == ["api", "routes"]:
                result = transit.route_detail(parts[2])
            elif parts == ["api", "stops"]:
                result = transit.stops(query("q")) if len(query("q")) >= 2 else []
            elif len(parts) == 4 and parts[:2] == ["api", "stops"] and parts[3] == "arrivals":
                result = transit.arrivals(parts[2])
            elif parts == ["api", "plan"]:
                result = transit.plan(query("from"), query("to"))
            else:
                return self.respond(404, {"error": "Endpoint non trovato"})
            self.respond(200, result)
        except transit.Unavailable as exc:
            self.respond(503, {"error": str(exc)})
        except ValueError as exc:
            self.respond(400, {"error": str(exc)})
        except Exception:
            logging.exception("API failure")
            self.respond(500, {"error": "Errore del servizio. Riprova tra poco."})

    def respond(self, code, result):
        body = json.dumps(result, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    print(f"Roma bus API on {host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
