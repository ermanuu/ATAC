"""Incomplete snapshots must not flicker or keep vehicles indefinitely."""
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from server import transit as t
from google.transit import gtfs_realtime_pb2 as pb
from server.positions import PositionHistory


def feed(now, trip='t1', include=True, timestamp=True):
    f = pb.FeedMessage()
    f.header.gtfs_realtime_version = '2.0'
    f.header.timestamp = now
    if include:
        e = f.entity.add(); e.id = 'position'
        e.vehicle.vehicle.id = '1001'
        e.vehicle.trip.trip_id = trip
        if timestamp:
            e.vehicle.timestamp = now
    return f


class PositionsTests(unittest.TestCase):
    def test_missing_once_then_reappearing_keeps_original_timestamp(self):
        h = PositionHistory()
        h.merge(feed(1000, timestamp=False), 1000)
        merged, retained, sources = h.merge(feed(1015, include=False), 1015)
        self.assertEqual(merged.entity[0].vehicle.timestamp, 1000)
        self.assertEqual(retained, ['position'])
        self.assertEqual(sources, ['position'])
        merged, retained, _ = h.merge(feed(1030), 1030)
        self.assertEqual(len(merged.entity), 1)
        self.assertEqual(merged.entity[0].vehicle.timestamp, 1030)
        self.assertEqual(retained, [])

    def test_missing_grace_and_failed_download_are_bounded(self):
        h = PositionHistory(); h.merge(feed(1000), 1000)
        self.assertEqual(len(h.merge(None, 1045)[0].entity), 1)
        self.assertEqual(len(h.merge(None, 1046)[0].entity), 0)

    def test_repeated_old_measurement_expires(self):
        h = PositionHistory(); h.merge(feed(1000), 1000)
        old = feed(1180); old.entity[0].vehicle.timestamp = 1000
        self.assertEqual(len(h.merge(old, 1180)[0].entity), 1)
        self.assertEqual(len(h.merge(old, 1181)[0].entity), 0)

    def test_reassignment_replaces_old_trip(self):
        h = PositionHistory(); h.merge(feed(1000), 1000)
        merged, retained, _ = h.merge(feed(1015, trip='t2'), 1015)
        self.assertEqual([e.vehicle.trip.trip_id for e in merged.entity], ['t2'])
        self.assertEqual(retained, [])

    def test_explicit_deletion_is_immediate(self):
        h = PositionHistory(); h.merge(feed(1000), 1000)
        f = feed(1015, include=False)
        e = f.entity.add(); e.id = 'position'; e.is_deleted = True
        self.assertEqual(len(h.merge(f, 1015)[0].entity), 0)

    def test_header_change_does_not_refresh_identical_measurement(self):
        h=PositionHistory(); h.merge(feed(1000, timestamp=False),1000)
        merged, _, _=h.merge(feed(1030, timestamp=False),1030)
        self.assertEqual(merged.entity[0].vehicle.timestamp,1000)
        changed=feed(1060,timestamp=False); changed.entity[0].vehicle.current_stop_sequence=2
        merged, _, _=h.merge(changed,1060)
        self.assertEqual(merged.entity[0].vehicle.timestamp,1060)

    def test_header_only_measurement_does_not_revive_after_history_expiry(self):
        h=PositionHistory(); h.merge(feed(1000,timestamp=False),1000)
        self.assertEqual(len(h.merge(feed(1181,timestamp=False),1181)[0].entity),0)
        self.assertEqual(len(h.merge(feed(1210,timestamp=False),1210)[0].entity),0)
        h.merge(feed(1256,include=False),1256)
        self.assertEqual(len(h.merge(feed(1280,timestamp=False),1280)[0].entity),0)
        changed=feed(1300,timestamp=False); changed.entity[0].vehicle.current_stop_sequence=3
        merged, _, _=h.merge(changed,1300)
        self.assertEqual(merged.entity[0].vehicle.timestamp,1300)

    def test_older_response_cannot_revert_current_position(self):
        h=PositionHistory()
        newer=feed(1030); newer.entity[0].vehicle.current_stop_sequence=3
        h.merge(newer,1030)
        older=feed(1000); older.entity[0].vehicle.current_stop_sequence=1
        merged, _, _=h.merge(older,1040)
        self.assertEqual(merged.entity[0].vehicle.current_stop_sequence,3)
        self.assertEqual(merged.entity[0].vehicle.timestamp,1030)

    def test_force_refresh_bypasses_ttl_but_coalesces_a_two_second_burst(self):
        reader=t.Realtime()
        with patch.object(t.time,'time',return_value=1000) as clock, patch.object(t,'download',return_value=feed(1000).SerializeToString()) as fetch:
            reader.read('vehicles'); reader.read('vehicles')
            self.assertEqual(fetch.call_count,1)
            reader.read('vehicles',force=True)
            self.assertEqual(fetch.call_count,1)
            clock.return_value = 1002
            reader.read('vehicles',force=True)
            self.assertEqual(fetch.call_count,2)

    def test_concurrent_first_requests_share_one_download(self):
        reader = t.Realtime()
        entered, release = threading.Event(), threading.Event()
        barrier = threading.Barrier(10)

        def download(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return feed(1000).SerializeToString()

        def request():
            barrier.wait(timeout=3)
            return reader.read('vehicles', force=True)

        with patch.object(t.time, 'time', return_value=1000), patch.object(t, 'download', side_effect=download) as fetch, ThreadPoolExecutor(max_workers=10) as pool:
            requests = [pool.submit(request) for _ in range(10)]
            try:
                self.assertTrue(entered.wait(3))
            finally:
                release.set()
            self.assertTrue(all(request.result(timeout=3)['available'] for request in requests))
            self.assertEqual(fetch.call_count, 1)

    def test_slow_forced_download_does_not_block_cached_readers_or_the_other_feed(self):
        reader = t.Realtime()
        entered, release = threading.Event(), threading.Event()
        with patch.object(t.time, 'time', return_value=1000) as clock, patch.object(t, 'download', return_value=feed(1000).SerializeToString()) as fetch, ThreadPoolExecutor(max_workers=3) as pool:
            original = reader.read('vehicles')
            clock.return_value = 1003

            def download(url, **kwargs):
                if url == t.VEHICLES_URL:
                    entered.set()
                    self.assertTrue(release.wait(3))
                return feed(1003).SerializeToString()

            fetch.side_effect = download
            refresh = pool.submit(reader.read, 'vehicles', True)
            try:
                self.assertTrue(entered.wait(3))
                self.assertIs(pool.submit(reader.read, 'vehicles').result(timeout=1), original)
                self.assertTrue(pool.submit(reader.read, 'updates').result(timeout=1)['available'])
            finally:
                release.set()
            self.assertEqual(refresh.result(timeout=3)['timestamp'], 1003)

    def test_background_polling_preserves_header_expiry_and_can_stop(self):
        reader = t.Realtime()
        seen = set()
        ready = threading.Event()

        def download(url, **kwargs):
            seen.add(url)
            if len(seen) == 2:
                ready.set()
            return feed(1000).SerializeToString()

        with patch.object(t.time, 'time', return_value=1000) as clock, patch.object(t, 'download', side_effect=download):
            reader.start()
            workers = list(reader.workers)
            try:
                self.assertTrue(ready.wait(3))
                reader.read('vehicles', force=True)
                clock.return_value = 1181
                self.assertFalse(reader.read('vehicles')['available'])
            finally:
                reader.stop()
            self.assertTrue(all(not worker.is_alive() for worker in workers))

    def test_download_failure_preserves_bounded_last_known_feed(self):
        reader = t.Realtime()
        with patch.object(t.time, 'time', return_value=1000) as clock, patch.object(t, 'download', return_value=feed(1000).SerializeToString()) as download:
            self.assertTrue(reader.read('vehicles')['available'])
            clock.return_value = 1015
            download.side_effect = OSError('temporary network failure')
            result = reader.read('vehicles')
            self.assertFalse(result['available'])
            self.assertEqual(result['retained'], ['position'])
            self.assertEqual(result['feed'].entity[0].vehicle.timestamp, 1000)
            clock.return_value = 1046
            self.assertEqual(len(reader.read('vehicles')['feed'].entity), 0)
