"""Read-only API with short, shared response caching."""
from dataclasses import dataclass
import gzip
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, quote_from_bytes, unquote, urlparse

from . import transit
from .cache import CacheBusy, SharedCache
from .http import respond as http_respond, serve


@dataclass(frozen=True)
class Response:
    code: int
    result: object
    body: bytes
    compressed: bytes | None


def response(code, result):
    body = json.dumps(result, ensure_ascii=False).encode()
    return Response(code, result, body, gzip.compress(body, mtime=0) if len(body) >= 512 else None)


_responses = SharedCache(max_entries=256, max_weight=8 * 1024 * 1024,
                         weight=lambda value: len(value.body) + len(value.compressed or b''))
_planning = threading.BoundedSemaphore(1)


def calculate_plan(origin, destination):
    if not _planning.acquire(blocking=False):
        raise transit.Unavailable('È già in corso un calcolo del percorso. Riprova tra pochi secondi.')
    try:
        return transit.plan(origin, destination)
    finally:
        _planning.release()


def api_response(path):
    url = urlparse(path)
    params = parse_qs(url.query)
    query = lambda name: params.get(name, [''])[0]
    refresh = query('fresh') == '1'
    options = {'refresh': True} if refresh else {}
    parts = [unquote(p) for p in url.path.strip('/').split('/')]
    live = True
    ttl = 1
    try:
        if parts == ['api', 'status']:
            key = ('status',)
            build = lambda: transit.status(**options)
        elif parts == ['api', 'routes']:
            key, live, ttl = ('routes', query('q')), False, 60
            build = lambda: transit.routes(query('q'))
        elif len(parts) == 3 and parts[:2] == ['api', 'routes']:
            key = ('route', parts[2], query('variant'))
            build = lambda: transit.route_detail(parts[2], query('variant') or None, **options)
        elif parts == ['api', 'stops']:
            key, live, ttl = ('stops', query('q')), False, 60
            build = lambda: transit.stops(query('q')) if len(query('q')) >= 2 else []
        elif len(parts) == 4 and parts[:2] == ['api', 'stops'] and parts[3] == 'arrivals':
            key = ('arrivals', parts[2])
            build = lambda: transit.arrivals(parts[2], **options)
        elif len(parts) == 4 and parts[:2] == ['api', 'vehicles'] and parts[3] == 'diagnostics':
            from .diagnostics import vehicle_diagnostics
            # Diagnostics always describes the current source, not a cached API row.
            return response(200, vehicle_diagnostics(parts[2], **options))
        elif parts == ['api', 'plan']:
            key, live, ttl = ('plan', query('from'), query('to')), False, 5
            build = lambda: calculate_plan(query('from'), query('to'))
        else:
            return response(404, {'error': 'Endpoint non trovato'})
        # Bucket live responses by the second, so ETA crossings and position
        # expiry are re-evaluated even if no new source packet has arrived.
        clock = int(time.time()) if ttl == 1 else int(time.time() // ttl)
        source = (transit.realtime, transit.realtime.revision, refresh) if live else None
        cache_key = (transit.database_version(), key, source, clock)
        return _responses.get(cache_key, lambda: response(200, build()), ttl=ttl, wait=key[0] != 'plan')
    except CacheBusy:
        return response(503, {'error': 'È già in corso un calcolo del percorso. Riprova tra pochi secondi.'})
    except transit.Unavailable as exc:
        return response(503, {'error': str(exc)})
    except ValueError as exc:
        return response(400, {'error': str(exc)})
    except Exception:
        logging.exception('API failure')
        return response(500, {'error': 'Errore del servizio. Riprova tra poco.'})


def application(environ, start_response):
    if environ.get('REQUEST_METHOD') != 'GET':
        return http_respond(environ, start_response, 405, b'Method not allowed', [('Allow', 'GET')])
    # WSGI has already decoded PATH_INFO (as Latin-1 bytes); restore URL
    # escaping before parsing so literal #, ?, % and UTF-8 IDs stay intact.
    path = quote_from_bytes(environ.get('PATH_INFO', '').encode('latin1'), safe='/') + '?' + environ.get('QUERY_STRING', '')
    value = api_response(path)
    return http_respond(environ, start_response, value.code, value.body,
                        [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store')],
                        compressed=value.compressed)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        value = api_response(self.path)
        self.respond(value.code, value.result)

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
    serve(application, host, port)
