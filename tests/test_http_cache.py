import gzip
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from server import app, transit as t, web


class HttpCacheTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for context in (patch.object(t, 'DB', self.root / 'transit.sqlite'),
                        patch.object(t, 'realtime', t.Realtime()),
                        patch.object(t.time, 'time', return_value=1000)):
            value = context.start()
            self.addCleanup(context.stop)
            if hasattr(value, 'return_value'):
                self.clock = value

    def test_api_burst_reuses_serialized_response_and_normalizes_query_order(self):
        barrier = threading.Barrier(10)

        def request(index):
            barrier.wait(timeout=3)
            return app.api_response('/api/routes/706?' + ('variant=a&fresh=1' if index % 2 else 'fresh=1&variant=a'))

        with patch.object(t, 'route_detail', return_value={'stops': []}) as calculate, ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(pool.map(request, range(10)))
        self.assertTrue(all(value is responses[0] for value in responses))
        calculate.assert_called_once_with('706', 'a', refresh=True)

    def test_live_response_rechecks_eta_every_second_and_after_a_new_feed(self):
        with patch.object(t, 'arrivals', return_value={'arrivals': ['before']}) as calculate:
            first = app.api_response('/api/stops/74351/arrivals')
            calculate.return_value = {'arrivals': ['after']}
            self.assertIs(app.api_response('/api/stops/74351/arrivals'), first)
            self.clock.return_value = 1001
            self.assertEqual(app.api_response('/api/stops/74351/arrivals').result['arrivals'], ['after'])
            t.realtime.revision += 1
            calculate.return_value = {'arrivals': ['new feed']}
            self.assertEqual(app.api_response('/api/stops/74351/arrivals').result['arrivals'], ['new feed'])
            self.assertEqual(calculate.call_count, 3)

    def test_replacing_the_dataset_invalidates_cached_searches(self):
        t.DB.write_bytes(b'first')
        with patch.object(t, 'routes', return_value=['old']) as calculate:
            app.api_response('/api/routes?q=706')
            replacement = self.root / 'import.sqlite'
            replacement.write_bytes(b'new dataset')
            os.replace(replacement, t.DB)
            calculate.return_value = ['new']
            self.assertEqual(app.api_response('/api/routes?q=706').result, ['new'])
            self.assertEqual(calculate.call_count, 2)

    def test_failed_responses_are_retried_in_the_same_second(self):
        with patch.object(t, 'arrivals', side_effect=t.Unavailable('retry')) as calculate:
            self.assertEqual(app.api_response('/api/stops/74351/arrivals').code, 503)
            calculate.side_effect = None
            calculate.return_value = {'arrivals': []}
            self.assertEqual(app.api_response('/api/stops/74351/arrivals').code, 200)

    def test_wsgi_static_cache_gzip_etag_and_head(self):
        (self.root / 'index.html').write_bytes(b'<html>shell</html>')
        name = 'bundle-' + 'a' * 32 + '.js'
        body = b'/* a large fingerprinted asset */' * 100
        (self.root / name).write_bytes(body)

        def request(path, method='GET', **headers):
            captured = []
            result = web.application({'PATH_INFO': path, 'REQUEST_METHOD': method, **headers},
                                     lambda status, values: captured.extend((status, dict(values))))
            return captured[0], captured[1], b''.join(result)

        with patch.object(web, 'ROOT', self.root):
            status, headers, compressed = request('/' + name, HTTP_ACCEPT_ENCODING='gzip')
            self.assertEqual(status, '200 OK')
            self.assertEqual(gzip.decompress(compressed), body)
            self.assertIn('immutable', headers['Cache-Control'])
            self.assertEqual(headers['Vary'], 'Accept-Encoding')
            self.assertEqual(request('/' + name, HTTP_IF_NONE_MATCH=headers['ETag'])[0], '304 Not Modified')
            status, headers, result = request('/' + name, 'HEAD')
            self.assertEqual(result, b'')
            self.assertEqual(int(headers['Content-Length']), len(body))
            self.assertEqual(request('/' + name, HTTP_ACCEPT_ENCODING='gzip;q=0')[2], body)
            self.assertEqual(request('/line/706/a')[1]['Cache-Control'], 'no-cache')
            self.assertEqual(request('/%2e%2e/private.txt')[0], '404 Not Found')

    def test_wsgi_api_uses_the_shared_response_and_does_not_cache_in_browser(self):
        with patch.object(t, 'routes', return_value=['large value' * 100]):
            captured = []
            result = web.application({'PATH_INFO': '/api/routes', 'QUERY_STRING': 'q=706',
                                      'REQUEST_METHOD': 'GET', 'HTTP_ACCEPT_ENCODING': 'gzip'},
                                     lambda status, values: captured.extend((status, dict(values))))
            self.assertEqual(captured[0], '200 OK')
            self.assertEqual(captured[1]['Cache-Control'], 'no-store')
            self.assertIn(b'large value', gzip.decompress(b''.join(result)))

    def test_status_does_not_expose_internal_protobuf_indexes(self):
        from google.transit import gtfs_realtime_pb2 as pb
        feed = pb.FeedMessage(); feed.header.gtfs_realtime_version = '2.0'; feed.header.timestamp = 1000
        entity = feed.entity.add(); entity.id = 'v'; entity.vehicle.trip.trip_id = 't1'
        with patch.object(t, 'download', return_value=feed.SerializeToString()):
            t.realtime.read('vehicles')
            result = t.status()
        self.assertNotIn('byTrip', result['vehicles'])
        self.assertNotIn('feed', result['vehicles'])
        json.dumps(result)

    def test_wsgi_keeps_literal_fragment_and_percent_characters_in_route_ids(self):
        with patch.object(t, 'route_detail', return_value={'stops': []}) as calculate:
            list(app.application({'PATH_INFO': '/api/routes/route#%?', 'QUERY_STRING': 'variant=x',
                                  'REQUEST_METHOD': 'GET'}, lambda *args: None))
            calculate.assert_called_once_with('route#%?', 'x')

    def test_slow_planner_leaves_workers_free_for_live_pages(self):
        entered, release = threading.Event(), threading.Event()

        def plan(*args):
            entered.set()
            self.assertTrue(release.wait(3))
            return {'legs': []}

        with patch.object(t, 'plan', side_effect=plan) as calculate, patch.object(t, 'routes', return_value=[]), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(app.api_response, '/api/plan?from=a&to=b')
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(app.api_response('/api/plan?from=a&to=b').code, 503)
                self.assertEqual(app.api_response('/api/plan?from=c&to=d').code, 503)
                self.assertEqual(pool.submit(app.api_response, '/api/routes?q=706').result(timeout=1).code, 200)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3).code, 200)
            self.assertEqual(app.api_response('/api/plan?from=a&to=b').code, 200)
            self.assertEqual(calculate.call_count, 1)
