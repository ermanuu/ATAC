"""Serve the exported web app and the API from a single local origin."""
import gzip
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .app import Handler as APIHandler
from .app import application as api_application
from .cache import SharedCache
from .http import respond, serve

ROOT = Path(__file__).resolve().parents[1] / 'dist'
_assets = SharedCache(max_entries=128, max_weight=16 * 1024 * 1024,
                      weight=lambda value: len(value[0]) + len(value[1] or b''))


def application(environ, start_response):
    path = environ.get('PATH_INFO', '/')
    if path == '/api' or path.startswith('/api/'):
        return api_application(environ, start_response)
    if environ.get('REQUEST_METHOD') not in ('GET', 'HEAD'):
        return respond(environ, start_response, 405, b'Method not allowed', [('Allow', 'GET, HEAD')])
    candidate = (ROOT / path.lstrip('/')).resolve()
    if not candidate.is_relative_to(ROOT.resolve()):
        return respond(environ, start_response, 404, b'Not found')
    if not candidate.is_file():
        if '.' in path.rsplit('/', 1)[-1] or path.startswith(('/assets/', '/_expo/')):
            return respond(environ, start_response, 404, b'Not found')
        candidate = ROOT / 'index.html'
    try:
        stat = candidate.stat()
        key = (str(candidate), stat.st_ino, stat.st_mtime_ns, stat.st_size)
        mime = 'application/manifest+json' if candidate.suffix == '.webmanifest' else (
            mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream')
        text = mime.startswith('text/') or mime in ('application/javascript', 'application/json', 'application/manifest+json')

        def read():
            body = candidate.read_bytes()
            return body, gzip.compress(body, mtime=0) if text and len(body) >= 512 else None

        body, compressed = _assets.get(key, read, ttl=3600)
    except OSError:
        return respond(environ, start_response, 404, b'Not found')
    fingerprinted = bool(re.search(r'[.-][a-f0-9]{32}\.', candidate.name))
    etag = f'W/"{stat.st_ino:x}-{stat.st_mtime_ns:x}-{stat.st_size:x}"'
    headers = [('Content-Type', mime), ('ETag', etag),
               ('Cache-Control', 'public, max-age=31536000, immutable' if fingerprinted else 'no-cache')]
    tags = [value.strip().removeprefix('W/') for value in environ.get('HTTP_IF_NONE_MATCH', '').split(',')]
    if etag.removeprefix('W/') in tags or '*' in tags:
        if compressed is not None:
            headers.append(('Vary', 'Accept-Encoding'))
        return respond(environ, start_response, 304, b'', headers)
    return respond(environ, start_response, 200, body, headers, compressed=compressed)


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
        def start_response(status, headers):
            self.send_response(int(status.split()[0]))
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()

        environ = {'REQUEST_METHOD': 'HEAD' if head else 'GET', 'PATH_INFO': unquote(urlsplit(self.path).path),
                   'HTTP_ACCEPT_ENCODING': self.headers.get('Accept-Encoding', ''),
                   'HTTP_IF_NONE_MATCH': self.headers.get('If-None-Match', '')}
        for body in application(environ, start_response):
            self.wfile.write(body)


if __name__ == '__main__':
    if not (ROOT / 'index.html').is_file():
        raise SystemExit('Versione web assente: esegui prima npm run build:web.')
    host = os.getenv('WEB_HOST', '127.0.0.1')
    port = int(os.getenv('WEB_PORT', '8000'))
    print(f'Roma Autobus web: http://{host}:{port}', flush=True)
    serve(application, host, port)
