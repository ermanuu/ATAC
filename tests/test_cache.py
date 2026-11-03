import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from server.cache import SharedCache


class CacheTests(unittest.TestCase):
    def test_concurrent_misses_share_one_calculation(self):
        cache = SharedCache()
        barrier = threading.Barrier(10)
        entered, release = threading.Event(), threading.Event()
        calls = []

        def build():
            calls.append(True)
            entered.set()
            self.assertTrue(release.wait(3))
            return b'one shared response'

        def request():
            barrier.wait(timeout=3)
            return cache.get('line', build, ttl=10)

        with ThreadPoolExecutor(max_workers=10) as pool:
            requests = [pool.submit(request) for _ in range(10)]
            try:
                self.assertTrue(entered.wait(3))
            finally:
                release.set()
            self.assertEqual([request.result(timeout=3) for request in requests], [b'one shared response'] * 10)
        self.assertEqual(len(calls), 1)

    def test_expiry_does_not_renew_a_cached_value(self):
        cache = SharedCache()
        with patch('server.cache.time.monotonic', return_value=100) as clock:
            self.assertEqual(cache.get('x', lambda: 'old', ttl=2), 'old')
            clock.return_value = 101
            self.assertEqual(cache.get('x', lambda: 'unexpected', ttl=2), 'old')
            clock.return_value = 102
            self.assertEqual(cache.get('x', lambda: 'new', ttl=2), 'new')

    def test_lru_eviction_respects_the_total_weight(self):
        cache = SharedCache(max_entries=3, max_weight=6, weight=len)
        for key in ('a', 'b', 'c'):
            cache.get(key, lambda: b'xx', ttl=10)
        cache.get('a', lambda: b'wrong', ttl=10)
        cache.get('d', lambda: b'xxx', ttl=10)
        self.assertEqual(list(cache.entries), ['a', 'd'])
        self.assertEqual(cache.total_weight, 5)
        cache.get('huge', lambda: b'x' * 7, ttl=10)
        self.assertNotIn('huge', cache.entries)

    def test_errors_are_not_cached_or_left_pending(self):
        cache = SharedCache()
        with self.assertRaisesRegex(ValueError, 'retry'):
            cache.get('x', lambda: (_ for _ in ()).throw(ValueError('retry')), ttl=10)
        self.assertFalse(cache.pending)
        self.assertEqual(cache.get('x', lambda: 'recovered', ttl=10), 'recovered')
