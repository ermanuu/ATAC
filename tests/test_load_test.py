import asyncio
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aiohttp import web
from server import load_test


def options(**values):
    args = dict(users=1, duration=.15, interval=10, connections=2, timeout=1, burst=True)
    return SimpleNamespace(**(args | values))


class LoadArgumentsTests(unittest.TestCase):
    def test_ten_thousand_users_do_not_require_ten_thousand_connections(self):
        args = load_test.parse_args(['--users', '10000'])
        self.assertEqual(args.users, 10000)
        self.assertEqual(args.connections, 256)

    def test_invalid_and_nonfinite_limits_are_rejected(self):
        for argv in (['--users', '10001'], ['--connections', '0'], ['--duration', 'nan'],
                     ['--interval', 'inf'], ['--timeout', '-1']):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                load_test.parse_args(argv)


class LoadSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_visitors_share_a_bounded_pool_and_bursts_measure_the_full_window(self):
        active = peak = 0

        async def request(path):
            nonlocal active, peak
            active += 1
            peak = max(active, peak)
            try:
                await asyncio.sleep(.003)
            finally:
                active -= 1

        report = await load_test.run_load(options(users=20, connections=3), ['/api/test'], request)
        self.assertEqual(report['requests'], 20)
        self.assertEqual(report['errors'], 0)
        self.assertLessEqual(peak, 3)
        self.assertTrue(report['load_target_met'])
        self.assertGreaterEqual(report['duration_seconds'], .15)

    async def test_refresh_only_on_first_poll_and_query_separator_is_preserved(self):
        paths = []

        async def request(path):
            paths.append(path)

        report = await load_test.run_load(options(duration=.14, interval=.06), ['/api/routes/706?variant=x'], request)
        self.assertEqual(paths, ['/api/routes/706?variant=x&fresh=1', '/api/routes/706?variant=x', '/api/routes/706?variant=x'])
        self.assertEqual(report['expected_requests'], 3)

    async def test_missed_load_is_reported_even_without_http_errors(self):
        async def slow(path):
            await asyncio.sleep(.06)

        report = await load_test.run_load(options(duration=.08, interval=.02), ['/api/test'], slow)
        self.assertEqual(report['errors'], 0)
        self.assertEqual(report['expected_requests'], 4)
        self.assertGreater(report['missed_requests'], 0)
        self.assertFalse(report['load_target_met'])

    async def test_queue_timeouts_are_distinguished_and_cancel_waiters(self):
        active = 0

        async def slow(path):
            nonlocal active
            active += 1
            try:
                await asyncio.sleep(1)
            finally:
                active -= 1

        report = await load_test.run_load(options(users=10, connections=1, timeout=.03), ['/api/test'], slow)
        self.assertGreater(report['generator_queue_timeouts'], 0)
        self.assertGreater(report['errors'], 0)
        self.assertLess(report['requests'], report['expected_requests'])
        self.assertFalse(report['load_target_met'])
        self.assertEqual(active, 0)


class LoadHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_http_reuses_connections_decodes_gzip_and_records_server_errors(self):
        peers = set()

        async def handle(request):
            peers.add(request.transport.get_extra_info('peername'))
            if request.path.endswith('fail'):
                return web.Response(status=503, text='busy')
            response = web.json_response({'result': 'large response' * 100})
            response.enable_compression()
            return response

        app = web.Application()
        app.router.add_get('/api/{name}', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        try:
            port = site._server.sockets[0].getsockname()[1]
            with tempfile.TemporaryDirectory() as folder:
                paths = Path(folder) / 'paths.json'
                paths.write_text(json.dumps(['/api/ok', '/api/fail']))
                output = Path(folder) / 'report.json'
                args = load_test.parse_args(['--base-url', f'http://127.0.0.1:{port}', '--paths-file', str(paths),
                                             '--users', '6', '--connections', '2', '--duration', '.5',
                                             '--burst', '--output', str(output)])
                with redirect_stdout(io.StringIO()), patch.object(load_test, 'get_env_proxy_for_url', wraps=load_test.get_env_proxy_for_url) as resolve:
                    result = await load_test.run(args)
                self.assertEqual(resolve.call_count, 1)
                report = json.loads(output.read_text())
            self.assertEqual(result, 1)
            self.assertEqual(report['requests'], 6)
            self.assertEqual(report['errors'], 3)
            self.assertEqual(report['generator_queue_timeouts'], 0)
            self.assertTrue(report['load_target_met'])
            self.assertLessEqual(len(peers), 2)
        finally:
            await runner.cleanup()
