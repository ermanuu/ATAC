import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from yarl import URL
from server import app, transit as t, web
from server.cache import SharedCache
from server.http import create_app


class AsyncCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_reader_does_not_cancel_a_shared_calculation(self):
        cache = SharedCache()
        entered, release = threading.Event(), threading.Event()
        calls = []

        def build():
            calls.append(True)
            entered.set()
            release.wait(3)
            return 'ready'

        with ThreadPoolExecutor(max_workers=1) as pool:
            first = asyncio.create_task(cache.get_async('x', build, 10, pool))
            second = asyncio.create_task(cache.get_async('x', build, 10, pool))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                first.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await first
                self.assertFalse(second.done())
            finally:
                release.set()
            self.assertEqual(await asyncio.wait_for(second, 2), 'ready')
            self.assertEqual(cache.get('x', lambda: 'wrong', 10), 'ready')
            self.assertEqual(len(calls), 1)

    async def test_errors_release_the_key_and_cached_hits_do_not_use_the_executor(self):
        cache = SharedCache()
        with ThreadPoolExecutor(max_workers=1) as pool:
            def fail():
                raise ValueError('retry')

            with self.assertRaisesRegex(ValueError, 'retry'):
                await cache.get_async('x', fail, 10, pool)
            self.assertFalse(cache.pending)
            self.assertEqual(await cache.get_async('x', lambda: 'ok', 10, pool), 'ok')
        # A closed executor proves a hit is served without submitting work.
        self.assertEqual(await cache.get_async('x', fail, 10, pool), 'ok')

    async def test_shutdown_cancels_queued_owners_without_leaving_pending_keys(self):
        cache = SharedCache()
        entered, release = threading.Event(), threading.Event()
        pool = ThreadPoolExecutor(max_workers=1)

        def busy():
            entered.set()
            release.wait(3)

        pool.submit(busy)
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        task = asyncio.create_task(cache.get_async('x', lambda: 'unused', 10, pool))
        await asyncio.sleep(0)
        try:
            pool.shutdown(wait=False, cancel_futures=True)
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            self.assertFalse(cache.pending)
        finally:
            release.set()
            await asyncio.to_thread(pool.shutdown, wait=True)


class AsyncHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / 'index.html').write_text('<html>app</html>')
        for context in (patch.object(t, 'DB', self.root / 'transit.sqlite'),
                        patch.object(t, 'realtime', t.Realtime()),
                        patch.object(web, 'ROOT', self.root),
                        patch.object(t.time, 'time', return_value=1000)):
            value = context.start()
            self.addCleanup(context.stop)
            if hasattr(value, 'return_value'):
                self.clock = value
        self.client = TestClient(TestServer(create_app(web.application, start_readers=False, workers=2)))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def test_cached_api_stays_responsive_when_all_compute_threads_are_busy(self):
        release = threading.Event()
        entered = [threading.Event(), threading.Event()]

        def arrivals(stop):
            entered[int(stop)].set()
            release.wait(3)
            return {'arrivals': []}

        with patch.object(t, 'routes', return_value=[]), patch.object(t, 'arrivals', side_effect=arrivals):
            response = await self.client.get('/api/routes?q=706')
            await response.read()
            requests = [asyncio.create_task(self.client.get(f'/api/stops/{i}/arrivals')) for i in range(2)]
            try:
                self.assertTrue(all(await asyncio.gather(*(asyncio.to_thread(event.wait, 2) for event in entered))))
                hit = await asyncio.wait_for(self.client.get('/api/routes?q=706'), 1)
                self.assertEqual(hit.status, 200)
                self.assertEqual(await hit.json(), [])
                self.assertFalse(any(request.done() for request in requests))
            finally:
                release.set()
            responses = await asyncio.gather(*requests)
            self.assertTrue(all(response.status == 200 for response in responses))
            await asyncio.gather(*(response.read() for response in responses))

    async def test_async_and_sync_clients_share_one_response_and_recheck_live_clock(self):
        with patch.object(t, 'arrivals', return_value={'arrivals': ['before']}) as calculate:
            original = app.api_response('/api/stops/74351/arrivals')
            response = await self.client.get('/api/stops/74351/arrivals')
            self.assertEqual(await response.read(), original.body)
            self.assertEqual(calculate.call_count, 1)
            calculate.return_value = {'arrivals': ['after']}
            self.clock.return_value = 1001
            response = await self.client.get('/api/stops/74351/arrivals')
            self.assertEqual((await response.json())['arrivals'], ['after'])
            t.realtime.revision += 1
            await (await self.client.get('/api/stops/74351/arrivals')).read()
            self.assertEqual(calculate.call_count, 3)

    async def test_atomic_dataset_replacement_invalidates_native_cached_responses(self):
        t.DB.write_bytes(b'old dataset')
        with patch.object(t, 'routes', return_value=['old']) as calculate:
            response = await self.client.get('/api/routes?q=706')
            self.assertEqual(await response.json(), ['old'])
            replacement = self.root / 'import.sqlite'
            replacement.write_bytes(b'new dataset')
            os.replace(replacement, t.DB)
            calculate.return_value = ['new']
            response = await self.client.get('/api/routes?q=706')
            self.assertEqual(await response.json(), ['new'])
            self.assertEqual(calculate.call_count, 2)

    async def test_many_cold_requests_share_one_calculation(self):
        entered, release = threading.Event(), threading.Event()

        def arrivals(stop):
            entered.set()
            release.wait(3)
            return {'arrivals': []}

        with patch.object(t, 'arrivals', side_effect=arrivals) as calculate:
            requests = [asyncio.create_task(self.client.get('/api/stops/74351/arrivals')) for _ in range(10)]
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            finally:
                release.set()
            responses = await asyncio.gather(*requests)
            results = await asyncio.gather(*(response.json() for response in responses))
            self.assertEqual(results, [{'arrivals': []}] * 10)
            self.assertEqual(calculate.call_count, 1)

    async def test_runtime_starts_one_shared_reader_and_stops_it_on_cleanup(self):
        with patch.object(t.realtime, 'start') as start, patch.object(t.realtime, 'stop') as stop, patch.object(t, 'routes', return_value=[]):
            async with TestClient(TestServer(create_app(web.application, workers=1))) as client:
                for _ in range(2):
                    response = await client.get('/api/routes?q=706')
                    self.assertEqual(response.status, 200)
                    await response.read()
                start.assert_called_once_with()
                stop.assert_not_called()
            stop.assert_called_once_with()

    async def test_native_http_preserves_gzip_methods_and_encoded_identifiers(self):
        with patch.object(t, 'route_detail', return_value={'stops': ['large' * 300]}) as calculate:
            response = await self.client.get(URL('/api/routes/route%23%25%3F?variant=x', encoded=True))
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers['Content-Encoding'], 'gzip')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual((await response.json())['stops'], ['large' * 300])
            calculate.assert_called_once_with('route#%?', 'x')
        response = await self.client.post('/api/status')
        self.assertEqual(response.status, 405)
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        await response.read()

    async def test_static_head_etag_unicode_spa_and_traversal(self):
        file = self.root / ('bundle-' + 'a' * 32 + '.js')
        file.write_bytes(b'/* asset */' * 100)
        (self.root / 'città.txt').write_text('Roma')
        response = await self.client.get('/' + file.name)
        etag = response.headers['ETag']
        self.assertIn('immutable', response.headers['Cache-Control'])
        self.assertEqual(await response.read(), file.read_bytes())
        response = await self.client.head('/' + file.name, headers={'Accept-Encoding': 'identity'})
        self.assertEqual(int(response.headers['Content-Length']), file.stat().st_size)
        self.assertEqual(await response.read(), b'')
        response = await self.client.get('/' + file.name, headers={'If-None-Match': etag})
        self.assertEqual(response.status, 304)
        await response.read()
        response = await self.client.get('/città.txt')
        self.assertEqual(await response.text(), 'Roma')
        response = await self.client.get('/line/706/x')
        self.assertEqual(response.headers['Cache-Control'], 'no-cache')
        await response.read()
        response = await self.client.get(URL('/%2e%2e/private.txt', encoded=True))
        self.assertEqual(response.status, 404)
        await response.read()

    async def test_diagnostics_is_not_cached_and_failures_can_be_retried(self):
        with patch('server.diagnostics.vehicle_diagnostics', return_value={'vehicles': []}) as diagnose:
            for _ in range(2):
                response = await self.client.get('/api/vehicles/2620/diagnostics?fresh=1')
                self.assertEqual(response.status, 200)
                await response.read()
            self.assertEqual(diagnose.call_count, 2)
        with patch.object(t, 'arrivals', side_effect=t.Unavailable('retry')) as calculate:
            response = await self.client.get('/api/stops/74351/arrivals')
            self.assertEqual(response.status, 503)
            await response.read()
            calculate.side_effect = None
            calculate.return_value = {'arrivals': []}
            response = await self.client.get('/api/stops/74351/arrivals')
            self.assertEqual(response.status, 200)
            await response.read()
