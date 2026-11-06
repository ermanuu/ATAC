"""Static arrival reuse must never freeze realtime or widen arrival windows."""
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from google.transit import gtfs_realtime_pb2 as pb
from server import transit as t
from server.cache import SharedCache
from test_transit import fixture


class StopScheduleTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.now = int(datetime(2026, 10, 30, 10, 0, tzinfo=t.ROME).timestamp())
        self.live = {'available': False, 'timestamp': None}
        for context in (patch.object(t, 'DATA', Path(folder.name)),
                        patch.object(t, 'DB', Path(folder.name) / 'transit.sqlite'),
                        patch.object(t, '_stop_schedules', SharedCache()),
                        patch.object(t.time, 'time', return_value=self.now),
                        patch.object(t, 'read_live', side_effect=lambda *args: self.live)):
            value = context.start()
            self.addCleanup(context.stop)
            if context.attribute == 'time':
                self.clock = value
        t.import_gtfs(fixture())

    def item(self):
        return next(row for row in t.arrivals('b')['arrivals'] if row['tripId'] == 't1')

    def test_reuses_static_queries_across_seconds_but_not_minutes_or_stops(self):
        with patch.object(t, 'service_windows', wraps=t.service_windows) as windows:
            self.item()
            self.clock.return_value = self.now + 1
            self.item()
            self.assertEqual(windows.call_count, 1)
            t.arrivals('c')
            self.assertEqual(windows.call_count, 2)
            self.clock.return_value = self.now + 60
            self.item()
            self.assertEqual(windows.call_count, 3)

    def test_live_changes_expiry_and_returned_mutations_do_not_pollute_static_cache(self):
        self.assertEqual(self.item()['kind'], 'scheduled')
        feed = pb.FeedMessage(); feed.header.gtfs_realtime_version = '2.0'
        feed.header.timestamp = self.now
        entity = feed.entity.add(); entity.id = 'trip'
        update = entity.trip_update; update.trip.trip_id = 't1'
        update.timestamp = self.now - 180
        event = update.stop_time_update.add(); event.stop_id = 'b'
        event.arrival.time = self.now + 900
        self.live = {'available': True, 'timestamp': self.now, 'feed': feed}
        self.assertEqual(self.item()['time'], self.now + 900)
        self.clock.return_value = self.now + 1
        row = self.item()
        self.assertEqual(row['kind'], 'scheduled')
        self.assertEqual(row['time'], self.now + 600)
        update.timestamp = self.now + 1
        event.arrival.time = self.now + 800
        self.assertEqual(self.item()['time'], self.now + 800)
        update.trip.schedule_relationship = pb.TripDescriptor.CANCELED
        self.assertFalse(any(row['tripId'] == 't1' for row in t.arrivals('b')['arrivals']))
        self.live = {'available': False, 'timestamp': None}
        row = self.item(); row['time'] = -1
        self.assertEqual(self.item()['time'], self.now + 600)
        self.assertNotIn('predictionTimestamp', self.item())

    def test_exact_rolling_upper_bound_inside_cached_minute(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE times SET arrival=39601,departure=39601 WHERE trip_id='t1' AND stop_id='b'")
        self.assertFalse(any(row['tripId'] == 't1' for row in t.arrivals('b')['arrivals']))
        self.clock.return_value = self.now + 1
        self.assertEqual(self.item()['time'], self.now + 3601)

    def test_candidate_expires_from_lookback_even_if_live_prediction_is_future(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE times SET arrival=34200,departure=34200 WHERE trip_id='t1' AND stop_id='b'")
        feed = pb.FeedMessage(); feed.header.gtfs_realtime_version = '2.0'
        entity = feed.entity.add(); entity.id = 'trip'
        update = entity.trip_update; update.trip.trip_id = 't1'
        event = update.stop_time_update.add(); event.stop_id = 'b'
        event.arrival.time = self.now + 10
        self.live = {'available': True, 'timestamp': self.now, 'feed': feed}
        self.assertEqual(self.item()['kind'], 'live')
        self.clock.return_value = self.now + 1
        self.assertFalse(any(row['tripId'] == 't1' for row in t.arrivals('b')['arrivals']))

    def test_atomic_import_invalidates_static_candidates_and_patterns(self):
        self.assertEqual(self.item()['line'], '64')
        import io
        import zipfile
        source = zipfile.ZipFile(io.BytesIO(fixture()))
        payload = io.BytesIO()
        with source, zipfile.ZipFile(payload, 'w') as target:
            for name in source.namelist():
                data = source.read(name)
                if name == 'routes.txt':
                    data = data.replace(b'r1,64,', b'r1,99,')
                target.writestr(name, data)
        t.import_gtfs(payload.getvalue())
        self.assertEqual(self.item()['line'], '99')

    def test_previous_service_day_and_calendar_exception_after_midnight(self):
        self.clock.return_value = int(datetime(2026, 10, 31, 0, 59, tzinfo=t.ROME).timestamp())
        rows = t.arrivals('a')['arrivals']
        self.assertEqual([(r['tripId'], r['serviceDate']) for r in rows], [('night', '20261030')])
        self.clock.return_value += 1
        self.assertEqual(t.arrivals('a')['arrivals'], rows)
        self.clock.return_value = int(datetime(2026, 11, 1, 0, 59, tzinfo=t.ROME).timestamp())
        self.assertEqual(t.arrivals('a')['arrivals'], [])
