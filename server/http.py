"""HTTP helpers and asynchronous serving with shared live data."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
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


def response_parts(accept_encoding, code, body, headers=(), compressed=None):
    headers = list(headers)
    if compressed is not None:
        headers.append(('Vary', 'Accept-Encoding'))
        if accepts_gzip(accept_encoding):
            body = compressed
            headers.append(('Content-Encoding', 'gzip'))
    if code != 304:
        headers.append(('Content-Length', str(len(body))))
    headers.append(('X-Content-Type-Options', 'nosniff'))
    return body, headers


def respond(environ, start_response, code, body, headers=(), compressed=None):
    body, headers = response_parts(environ.get('HTTP_ACCEPT_ENCODING', ''), code, body, headers, compressed)
    start_response(f'{code} {HTTPStatus(code).phrase}', headers)
    return [] if environ.get('REQUEST_METHOD') == 'HEAD' or code == 304 else [body]


def create_app(application, *, start_readers=True, workers=None):
    from aiohttp import web
    from .app import api_response_async
    from .transit import realtime

    executor = ThreadPoolExecutor(max_workers=workers if workers is not None else int(os.getenv('WEB_THREADS', '8')),
                                  thread_name_prefix='romabus-compute')
    app = web.Application(client_max_size=1024 * 1024)

    async def handle(request):
        if request.path == '/api' or request.path.startswith('/api/'):
            if request.method != 'GET':
                return web.Response(status=405, body=b'Method not allowed',
                                    headers={'Allow': 'GET', 'X-Content-Type-Options': 'nosniff'})
            value = await api_response_async(request.raw_path, executor)
            body, headers = response_parts(request.headers.get('Accept-Encoding', ''), value.code, value.body,
                                           [('Content-Type', 'application/json; charset=utf-8'), ('Cache-Control', 'no-store')],
                                           value.compressed)
            return web.Response(status=value.code, body=body, headers=headers)

        environ = {'REQUEST_METHOD': request.method, 'PATH_INFO': request.path.encode('utf-8').decode('latin1'),
                   'QUERY_STRING': request.raw_path.partition('?')[2],
                   'HTTP_ACCEPT_ENCODING': request.headers.get('Accept-Encoding', ''),
                   'HTTP_IF_NONE_MATCH': request.headers.get('If-None-Match', '')}

        def static_response():
            captured = []
            result = application(environ, lambda status, headers: captured.extend((status, headers)))
            try:
                body = b''.join(result)
            finally:
                if hasattr(result, 'close'):
                    result.close()
            return int(captured[0].split()[0]), captured[1], body

        status, headers, body = await asyncio.get_running_loop().run_in_executor(executor, static_response)
        return web.Response(status=status, headers=headers, body=body)

    async def startup(app):
        if start_readers:
            realtime.start()

    async def cleanup(app):
        if start_readers:
            await asyncio.to_thread(realtime.stop)
        await asyncio.to_thread(executor.shutdown, wait=True, cancel_futures=True)

    app.router.add_route('*', '/{path:.*}', handle)
    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


def serve(application, host, port, *, asynchronous=False):
    if asynchronous and os.getenv('WEB_SERVER', 'aiohttp') != 'waitress':
        from aiohttp import web
        web.run_app(create_app(application), host=host, port=port, print=None,
                    access_log=None, backlog=1024, keepalive_timeout=15,
                    shutdown_timeout=20, handler_cancellation=True)
        return
    from waitress import serve as run
    from .transit import realtime
    realtime.start()
    try:
        run(application, host=host, port=port,
            threads=int(os.getenv('WEB_THREADS', '8')),
            connection_limit=256, channel_timeout=30,
            ident='ROMABUS', log_socket_errors=False)
    finally:
        realtime.stop()
