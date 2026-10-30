"""Serve the exported web app and the API from a single local origin."""
import mimetypes
import os
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .app import Handler as APIHandler

ROOT = Path(__file__).resolve().parents[1] / 'dist'


class Handler(APIHandler):
    def do_GET(self):
        self.handle_request()

    def do_HEAD(self):
        self.handle_request(head=True)

    def handle_request(self, head=False):
        path = unquote(urlsplit(self.path).path)
        if path == '/api' or path.startswith('/api/'):
            if head:
                self.send_error(405)
            else:
                super().do_GET()
            return
        candidate = (ROOT / path.lstrip('/')).resolve()
        if not candidate.is_relative_to(ROOT.resolve()):
            self.send_error(404)
            return
        if not candidate.is_file():
            # Only navigation requests get the SPA shell, never missing assets.
            if '.' in path.rsplit('/', 1)[-1] or path.startswith(('/assets/', '/_expo/')):
                self.send_error(404)
                return
            candidate = ROOT / 'index.html'
        try:
            body = candidate.read_bytes()
        except OSError:
            self.send_error(404)
            return
        mime = mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream'
        if candidate.suffix == '.webmanifest':
            mime = 'application/manifest+json'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if not head:
            self.wfile.write(body)


if __name__ == '__main__':
    if not (ROOT / 'index.html').is_file():
        raise SystemExit('Versione web assente: esegui prima npm run build:web.')
    host = os.getenv('WEB_HOST', '127.0.0.1')
    port = int(os.getenv('WEB_PORT', '8000'))
    print(f'Roma Autobus web: http://{host}:{port}', flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
