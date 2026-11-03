"""Shared HTTP response handling and the single-process production server."""
from http import HTTPStatus
import os


def accepts_gzip(value):
    encodings = {}
    for item in value.lower().split(','):
        name, *options = item.strip().split(';')
        try:
            encodings[name] = next((float(option.strip()[2:]) for option in options
                                    if option.strip().startswith('q=')), 1)
        except ValueError:
            encodings[name] = 0
    return encodings.get('gzip', encodings.get('*', 0)) > 0


def respond(environ, start_response, code, body, headers=(), compressed=None):
    headers = list(headers)
    if compressed is not None:
        headers.append(('Vary', 'Accept-Encoding'))
        if accepts_gzip(environ.get('HTTP_ACCEPT_ENCODING', '')):
            body = compressed
            headers.append(('Content-Encoding', 'gzip'))
    if code != 304:
        headers.append(('Content-Length', str(len(body))))
    headers.append(('X-Content-Type-Options', 'nosniff'))
    start_response(f'{code} {HTTPStatus(code).phrase}', headers)
    return [] if environ.get('REQUEST_METHOD') == 'HEAD' or code == 304 else [body]


def serve(application, host, port):
    from waitress import serve as run
    from .transit import realtime
    realtime.start()
    try:
        run(application, host=host, port=port,
            threads=int(os.getenv('WEB_THREADS', '8')),
            connection_limit=256, channel_timeout=30,
            ident='Roma Autobus', log_socket_errors=False)
    finally:
        realtime.stop()
