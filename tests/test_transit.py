"""Isolated synthetic GTFS fixtures are test inputs, never app fallback data."""
import io
from pathlib import Path
import tempfile
import sqlite3
import time
import unittest
from unittest.mock import patch
import zipfile
from datetime import datetime

from server import transit as t
from google.transit import gtfs_realtime_pb2 as pb


def fixture():
    files = {
        "routes.txt": "route_id,route_short_name,route_long_name,route_type\nr1,64,Test linea,3\nr2,40,Test cambio,3\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\na,Origine,41.90,12.49\nb,Cambio,41.91,12.50\nc,Destinazione,41.92,12.51\nd,Isolata,41.93,12.52\n",
        "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id\nr1,daily,t1,Cambio,0\nr2,daily,t2,Destinazione,0\nr1,daily,night,Notturno,1\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nt1,10:00:00,10:00:00,a,10\nt1,10:10:00,10:10:00,b,20\nt2,10:13:00,10:13:00,b,1\nt2,10:30:00,10:30:00,c,2\nnight,25:00:00,25:00:00,a,1\nnight,25:15:00,25:15:00,c,2\n",
        "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\ndaily,1,1,1,1,1,1,1,20260101,20261231\n",
        "calendar_dates.txt": "service_id,date,exception_type\ndaily,20261031,2\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buffer.getvalue()


class TransitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(t, "DATA", Path(self.temp.name)), patch.object(t, "DB", Path(self.temp.name)/"transit.sqlite"), patch.object(t.realtime, "read", return_value={"available": False, "timestamp": None})]
        for p in self.patches:
            p.start()
        t.import_gtfs(fixture())
        self.now = int(datetime(2026, 10, 30, 9, 59, tzinfo=t.ROME).timestamp())

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_import_and_search(self):
        self.assertEqual(t.routes("64")[0]["route_id"], "r1")
        self.assertEqual(t.stops("Origine")[0]["stop_id"], "a")
        self.assertEqual(len(t.route_detail("r1")["variants"]), 2)

    def test_route_with_transfer_and_nonconsecutive_sequences(self):
        result = t.plan("a", "c", self.now)
        self.assertEqual([r["line"] for r in result["legs"]], ["64", "40"])
        self.assertEqual(result["legs"][-1]["toName"], "Destinazione")
        self.assertEqual(result["legs"][0]["stops"], 1)

    def test_transfer_margin_prevents_impossible_connection(self):
        import sqlite3
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE connections SET departure=36630 WHERE trip_id='t2'")
        self.assertEqual(t.plan("a", "c", self.now)["legs"], [])

    def test_no_route(self):
        self.assertEqual(t.plan("a", "d", self.now)["legs"], [])

    def test_invalid_stops(self):
        for pair in (("a", "a"), ("missing", "a")):
            with self.assertRaises(ValueError):
                t.plan(*pair, self.now)

    def test_previous_day_over_24_hours(self):
        now = int(datetime(2026, 10, 31, 0, 59, tzinfo=t.ROME).timestamp())
        result = t.plan("a", "c", now)
        self.assertEqual(len(result["legs"]), 1)
        self.assertEqual(result["legs"][0]["stops"], 1)

    def test_calendar_exception(self):
        with t.connect() as db:
            self.assertEqual(t.active_services(db, datetime(2026, 10, 31).date()), set())

    def test_failed_import_preserves_database(self):
        before = t.DB.read_bytes()
        with self.assertRaises(zipfile.BadZipFile):
            t.import_gtfs(b"invalid feed")
        self.assertEqual(t.DB.read_bytes(), before)

    def tracked_connections(self):
        connections = []
        original = sqlite3.connect

        class TrackedConnection(sqlite3.Connection):
            closed = False

            def close(self):
                super().close()
                self.closed = True

        def create(*args, **kwargs):
            connection = original(*args, **kwargs, factory=TrackedConnection)
            connections.append(connection)
            return connection

        return connections, create

    def test_database_closed_before_replace_on_windows(self):
        connections, create = self.tracked_connections()
        replace = t.os.replace

        def windows_replace(source, destination):
            self.assertTrue(connections)
            self.assertTrue(all(c.closed for c in connections), "Windows locks an open SQLite database")
            return replace(source, destination)

        with patch.object(t.sqlite3, "connect", side_effect=create), patch.object(t.os, "replace", side_effect=windows_replace):
            t.import_gtfs(fixture())
        self.assertEqual(t.routes("64")[0]["route_id"], "r1")

    def test_database_closed_before_failed_import_cleanup_on_windows(self):
        connections, create = self.tracked_connections()
        unlink = Path.unlink
        before = t.DB.read_bytes()

        def windows_unlink(path, *args, **kwargs):
            if path.name == "import.sqlite" and path.exists():
                self.assertTrue(all(c.closed for c in connections), "Windows cannot delete an open SQLite database")
            return unlink(path, *args, **kwargs)

        with patch.object(t.sqlite3, "connect", side_effect=create), patch.object(Path, "unlink", windows_unlink), patch.object(t, "seconds", side_effect=ValueError("invalid GTFS time")):
            with self.assertRaisesRegex(ValueError, "invalid GTFS time"):
                t.import_gtfs(fixture())
        self.assertTrue(connections)
        self.assertTrue(all(c.closed for c in connections))
        self.assertFalse((t.DATA / "import.sqlite").exists())
        self.assertEqual(t.DB.read_bytes(), before)

    def test_realtime_rejects_stale_and_caches_failures(self):
        feed = pb.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = int(time.time()) - 400
        with patch.object(t, "download", return_value=feed.SerializeToString()) as fetch:
            client = t.Realtime()
            self.assertFalse(client.read("updates")["available"])
            client.read("updates")
            self.assertEqual(fetch.call_count, 1)

    def test_vehicle_cache_refreshes_before_next_fifteen_second_poll(self):
        f=pb.FeedMessage(); f.header.gtfs_realtime_version='2.0'; f.header.timestamp=self.now
        client=t.Realtime()
        with patch.object(t.time,'time',return_value=self.now) as now, patch.object(t,'download',return_value=f.SerializeToString()) as fetch:
            self.assertTrue(client.read('vehicles')['available'])
            now.return_value=self.now+5
            client.read('vehicles')
            self.assertEqual(fetch.call_count,1)
            now.return_value=self.now+15
            f.header.timestamp=self.now+15; fetch.return_value=f.SerializeToString()
            self.assertEqual(client.read('vehicles')['timestamp'],self.now+15)
            self.assertEqual(fetch.call_count,2)

    def test_cached_feed_cannot_remain_available_after_expiry(self):
        f=pb.FeedMessage(); f.header.gtfs_realtime_version='2.0'; f.header.timestamp=self.now-175
        client=t.Realtime()
        with patch.object(t.time,'time',return_value=self.now) as now, patch.object(t,'download',return_value=f.SerializeToString()):
            self.assertTrue(client.read('vehicles')['available'])
            now.return_value=self.now+7
            self.assertFalse(client.read('vehicles')['available'])

    def test_trip_update_and_cancellation(self):
        feed = pb.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = self.now
        update = feed.entity.add()
        update.id = "prediction"
        update.trip_update.trip.trip_id = "t1"
        update.trip_update.trip.start_date = "20261030"
        stop = update.trip_update.stop_time_update.add()
        stop.stop_id = "a"
        stop.departure.delay = 120
        with patch.object(t.time, "time", return_value=self.now), patch.object(t.realtime, "read", return_value={"available": True, "timestamp": self.now, "feed": feed}):
            result = t.arrivals("a")["arrivals"]
            self.assertEqual(result[0]["kind"], "live")
            self.assertEqual(result[0]["time"], self.now+180)
            update.trip_update.trip.schedule_relationship = pb.TripDescriptor.CANCELED
            self.assertEqual(t.arrivals("a")["arrivals"], [])

    def test_missing_live_falls_back_to_scheduled(self):
        with patch.object(t.time, "time", return_value=self.now), patch.object(t.realtime, "read", return_value={"available": False, "timestamp": None}):
            result = t.arrivals("a")
            self.assertFalse(result["liveAvailable"])
            self.assertEqual(result["arrivals"][0]["kind"], "scheduled")


if __name__ == "__main__":
    unittest.main()
