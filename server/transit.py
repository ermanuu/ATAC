"""Roma Mobilità GTFS adapter. No mock data or third-party routing service."""
import csv
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import urllib.request
import zipfile
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DB = DATA / "transit.sqlite"
BASE = "https://romamobilita.it/sites/default/files/"
STATIC_URL = BASE + "rome_static_gtfs.zip"
VEHICLES_URL = BASE + "rome_rtgtfs_vehicle_positions_feed.pb"
UPDATES_URL = BASE + "rome_rtgtfs_trip_updates_feed.pb"
ROME = ZoneInfo("Europe/Rome")


class Unavailable(Exception):
    pass


def download(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": "ATAC-development/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def seconds(value):
    h, m, s = map(int, value.split(":"))
    return h * 3600 + m * 60 + s


@contextmanager
def connect():
    if not DB.exists():
        raise Unavailable("Orari non ancora importati. Eseguire python -m server.import_gtfs.")
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def import_gtfs(payload):
    """Build a new database atomically; retain the last valid dataset on failure."""
    DATA.mkdir(parents=True, exist_ok=True)
    temporary = DATA / "import.sqlite"
    temporary.unlink(missing_ok=True)
    try:
        # SQLite's transaction context manager does not close the connection.
        # Windows requires it closed before replacing or deleting the file.
        with zipfile.ZipFile(io.BytesIO(payload)) as archive, closing(sqlite3.connect(temporary)) as db:
            db.executescript("""
                CREATE TABLE routes(route_id TEXT PRIMARY KEY, name TEXT, description TEXT, type INTEGER);
                CREATE TABLE stops(stop_id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL);
                CREATE TABLE trips(trip_id TEXT PRIMARY KEY, route_id TEXT, service_id TEXT, headsign TEXT, direction TEXT);
                CREATE TABLE times(trip_id TEXT, stop_id TEXT, sequence INTEGER, arrival INTEGER, departure INTEGER, pickup INTEGER, dropoff INTEGER);
                CREATE TABLE calendar(service_id TEXT, start TEXT, end TEXT, days TEXT);
                CREATE TABLE exceptions(service_id TEXT, date TEXT, type INTEGER);
                CREATE TABLE metadata(imported_at INTEGER);
            """)

            def rows(name):
                if name not in archive.namelist():
                    return
                with archive.open(name) as raw:
                    yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))

            if next(rows("frequencies.txt"), None) is not None:
                raise ValueError("Feed con frequencies.txt non ancora supportato: importazione interrotta per evitare orari inesatti")

            db.executemany("INSERT INTO routes VALUES (?,?,?,?)", (
                (r["route_id"], r.get("route_short_name") or r.get("route_long_name"), r.get("route_long_name", ""), int(r["route_type"]))
                for r in rows("routes.txt")))
            db.executemany("INSERT INTO stops VALUES (?,?,?,?)", (
                (r["stop_id"], r["stop_name"], float(r["stop_lat"]), float(r["stop_lon"])) for r in rows("stops.txt")))
            db.executemany("INSERT INTO trips VALUES (?,?,?,?,?)", (
                (r["trip_id"], r["route_id"], r["service_id"], r.get("trip_headsign", ""), r.get("direction_id", "")) for r in rows("trips.txt")))
            db.executemany("INSERT INTO times VALUES (?,?,?,?,?,?,?)", (
                (r["trip_id"], r["stop_id"], int(r["stop_sequence"]), seconds(r["arrival_time"]), seconds(r["departure_time"]), int(r.get("pickup_type") or 0), int(r.get("drop_off_type") or 0))
                for r in rows("stop_times.txt") if r.get("arrival_time") and r.get("departure_time")))
            weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
            db.executemany("INSERT INTO calendar VALUES (?,?,?,?)", (
                (r["service_id"], r["start_date"], r["end_date"], "".join(r[d] for d in weekdays)) for r in rows("calendar.txt")))
            db.executemany("INSERT INTO exceptions VALUES (?,?,?)", (
                (r["service_id"], r["date"], int(r["exception_type"])) for r in rows("calendar_dates.txt")))
            db.executescript("""
                CREATE UNIQUE INDEX times_trip_sequence ON times(trip_id, sequence);
                CREATE INDEX times_stop ON times(stop_id, departure);
                CREATE INDEX trips_route ON trips(route_id);
                CREATE TABLE connections AS
                    SELECT a.stop_id AS origin, b.stop_id AS destination, a.departure, b.arrival,
                           a.pickup, b.dropoff, t.trip_id, t.route_id, t.service_id
                    FROM times a JOIN times b ON b.trip_id=a.trip_id AND b.sequence=(
                        SELECT min(c.sequence) FROM times c WHERE c.trip_id=a.trip_id AND c.sequence>a.sequence)
                    JOIN trips t ON t.trip_id=a.trip_id JOIN routes r ON r.route_id=t.route_id
                    WHERE r.type=3;
                CREATE INDEX connections_departure ON connections(departure);
            """)
            for table in ("routes", "stops", "trips", "times", "connections"):
                if db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0:
                    raise ValueError(f"GTFS incompleto: {table} vuota")
            db.execute("INSERT INTO metadata VALUES (?)", (int(time.time()),))
            db.commit()
        os.replace(temporary, DB)
    finally:
        temporary.unlink(missing_ok=True)


def active_services(db, day):
    date = day.strftime("%Y%m%d")
    active = {r["service_id"] for r in db.execute(
        "SELECT * FROM calendar WHERE start<=? AND end>=?", (date, date)) if r["days"][day.weekday()] == "1"}
    for r in db.execute("SELECT * FROM exceptions WHERE date=?", (date,)):
        if r["type"] == 1:
            active.add(r["service_id"])
        else:
            active.discard(r["service_id"])
    return active


def service_windows(db, now, horizon=14400):
    local = datetime.fromtimestamp(now, ROME)
    # Include the previous service day for GTFS times after 24:00.
    for offset in (-1, 0, 1):
        day = (local + timedelta(days=offset)).date()
        midnight = datetime.combine(day, datetime.min.time(), ROME).timestamp()
        # GTFS time is measured from local noon minus 12 hours (also on DST days).
        epoch = datetime.combine(day, datetime.min.time().replace(hour=12), ROME).timestamp() - 43200
        if midnight > now + horizon:
            continue
        yield epoch, active_services(db, day)


class Realtime:
    def __init__(self):
        self.lock = threading.Lock()
        self.cache = {}

    def read(self, kind):
        with self.lock:
            cached = self.cache.get(kind)
            now = time.time()
            if cached and now - cached[0] < 30:
                return cached[1]
            try:
                feed = gtfs_realtime_pb2.FeedMessage()
                feed.ParseFromString(download(VEHICLES_URL if kind == "vehicles" else UPDATES_URL, timeout=10))
                timestamp = int(feed.header.timestamp)
                if feed.header.incrementality == gtfs_realtime_pb2.FeedHeader.DIFFERENTIAL:
                    raise ValueError("Feed differenziale non supportato")
                if not timestamp or timestamp > now + 60 or now - timestamp > 180:
                    raise ValueError("Feed assente, scaduto o con timestamp non valido")
                result = {"available": True, "timestamp": timestamp, "feed": feed}
            except Exception as exc:
                result = {"available": False, "timestamp": None, "error": str(exc), "feed": None}
            self.cache[kind] = (now, result)
            return result


realtime = Realtime()


def status():
    result = {"provider": "Roma Servizi per la Mobilità", "staticAvailable": False,
              "staticImportedAt": None, "vehiclesUrl": VEHICLES_URL, "updatesUrl": UPDATES_URL}
    if DB.exists():
        with connect() as db:
            result["staticImportedAt"] = db.execute("SELECT imported_at FROM metadata").fetchone()[0]
            result["staticAvailable"] = True
            result["serviceToday"] = bool(active_services(db, datetime.now(ROME).date()))
    for kind in ("vehicles", "updates"):
        live = realtime.read(kind)
        result[kind] = {k: v for k, v in live.items() if k != "feed"}
    return result


def routes(query=""):
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM routes WHERE type=3 AND (name LIKE ? OR description LIKE ?) ORDER BY length(name),name LIMIT 100", (f"%{query}%", f"%{query}%"))]


def stops(query):
    with connect() as db:
        return [dict(r) for r in db.execute("SELECT * FROM stops WHERE name LIKE ? OR stop_id=? ORDER BY name LIMIT 30", (f"%{query}%", query))]


def route_detail(route_id):
    with connect() as db:
        variants = []
        # Select one stop pattern per direction/headsign; only currently active service.
        active = active_services(db, datetime.now(ROME).date())
        seen = set()
        for trip in db.execute("SELECT * FROM trips WHERE route_id=? ORDER BY direction,headsign,trip_id", (route_id,)):
            key = (trip["direction"], trip["headsign"])
            if trip["service_id"] not in active or key in seen:
                continue
            seen.add(key)
            sequence = [dict(r) for r in db.execute("SELECT s.*,t.sequence FROM times t JOIN stops s ON s.stop_id=t.stop_id WHERE trip_id=? ORDER BY sequence", (trip["trip_id"],))]
            variants.append({"headsign": trip["headsign"], "direction": trip["direction"], "stops": sequence})
    live = realtime.read("vehicles")
    vehicles = []
    if live["available"]:
        with connect() as db:
            trip_routes = dict(db.execute("SELECT trip_id,route_id FROM trips"))
        for entity in live["feed"].entity:
            if entity.is_deleted or not entity.HasField("vehicle"):
                continue
            v = entity.vehicle
            timestamp = int(v.timestamp or live["timestamp"])
            actual_route = v.trip.route_id or trip_routes.get(v.trip.trip_id)
            if actual_route == route_id and v.HasField("position") and 0 <= time.time() - timestamp <= 180:
                vehicles.append({"id": v.vehicle.id or entity.id, "lat": v.position.latitude, "lon": v.position.longitude,
                                 "timestamp": timestamp, "stopId": v.stop_id, "status": gtfs_realtime_pb2.VehiclePosition.VehicleStopStatus.Name(v.current_status)})
    return {"variants": variants, "vehicles": vehicles, "liveAvailable": live["available"], "timestamp": live["timestamp"]}


def arrivals(stop_id):
    now = int(time.time())
    scheduled = []
    with connect() as db:
        for epoch, active in service_windows(db, now, 7200):
            for r in db.execute("SELECT t.*,tr.service_id,tr.headsign,r.name FROM times t JOIN trips tr ON tr.trip_id=t.trip_id JOIN routes r ON r.route_id=tr.route_id WHERE t.stop_id=? AND t.departure BETWEEN ? AND ? AND r.type=3 AND t.pickup!=1 ORDER BY t.departure", (stop_id, now-1800-epoch, now+7200-epoch)):
                if r["service_id"] in active:
                    scheduled.append({"tripId": r["trip_id"], "stopSequence": r["sequence"], "line": r["name"], "headsign": r["headsign"], "time": int(epoch+r["departure"]), "kind": "scheduled", "serviceDate": datetime.fromtimestamp(epoch+43200, ROME).strftime("%Y%m%d")})
    live = realtime.read("updates")
    if live["available"]:
        by_trip = {}
        for e in live["feed"].entity:
            if not e.is_deleted and e.HasField("trip_update"):
                by_trip[(e.trip_update.trip.trip_id, e.trip_update.trip.start_date)] = e.trip_update
        keep = []
        for item in scheduled:
            update = by_trip.get((item["tripId"], item["serviceDate"]))
            if update is None:
                update = by_trip.get((item["tripId"], ""))
            if update is not None:
                if update.timestamp and not 0 <= now - update.timestamp <= 180:
                    keep.append(item)
                    continue
                if update.trip.schedule_relationship == gtfs_realtime_pb2.TripDescriptor.CANCELED:
                    continue
                skipped = False
                for event in update.stop_time_update:
                    if event.stop_id != stop_id and not (not event.stop_id and event.HasField("stop_sequence") and event.stop_sequence == item["stopSequence"]):
                        continue
                    if event.schedule_relationship == gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED:
                        skipped = True
                        break
                    if event.schedule_relationship == gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.NO_DATA:
                        break
                    for field in ("departure", "arrival"):
                        if event.HasField(field):
                            prediction = getattr(event, field)
                            if prediction.HasField("time"):
                                item.update(time=int(prediction.time), kind="live")
                                break
                            if prediction.HasField("delay"):
                                item.update(time=item["time"] + prediction.delay, kind="live")
                                break
                    break
                if skipped:
                    continue
            keep.append(item)
        scheduled = keep
    return {"arrivals": sorted((i for i in scheduled if now <= i["time"] <= now+7200), key=lambda i: i["time"])[:20],
            "liveAvailable": live["available"], "timestamp": live["timestamp"]}


def plan(origin, destination, now=None):
    """Connection scan, bus-only, four-hour horizon, two-minute transfer margin."""
    now = int(time.time()) if now is None else now
    if origin == destination:
        raise ValueError("Scegli due fermate diverse")
    with connect() as db:
        for stop in (origin, destination):
            if not db.execute("SELECT 1 FROM stops WHERE stop_id=?", (stop,)).fetchone():
                raise ValueError("Fermata non valida")
        connections = []
        for epoch, active in service_windows(db, now):
            for row in db.execute("SELECT * FROM connections WHERE departure BETWEEN ? AND ?", (now-epoch, now+14400-epoch)):
                if row["service_id"] in active:
                    c = dict(row)
                    c.update(departure=int(epoch+c["departure"]), arrival=int(epoch+c["arrival"]), key=(epoch,c["trip_id"]))
                    connections.append(c)
        connections.sort(key=lambda c: c["departure"])
        labels = {origin: (now, [])}
        onboard = {}
        for c in connections:
            previous = onboard.get(c["key"])
            label = labels.get(c["origin"])
            if previous is None and label and c["pickup"] != 1 and label[0] + (0 if c["origin"] == origin else 120) <= c["departure"]:
                previous = label[1]
            if previous is None:
                continue
            path = previous + [c]
            onboard[c["key"]] = path
            if c["dropoff"] != 1 and c["arrival"] < labels.get(c["destination"], (float("inf"), []))[0]:
                labels[c["destination"]] = (c["arrival"], path)
        if destination not in labels:
            return {"legs": [], "kind": "scheduled", "message": "Nessun percorso solo autobus nelle prossime 4 ore. Prova altre fermate."}
        legs = []
        for c in labels[destination][1]:
            if legs and legs[-1]["key"] == c["key"]:
                legs[-1].update(to=c["destination"], arrival=c["arrival"], stops=legs[-1]["stops"]+1)
            else:
                line = db.execute("SELECT name FROM routes WHERE route_id=?", (c["route_id"],)).fetchone()[0]
                legs.append({"key": c["key"], "line": line, "from": c["origin"], "to": c["destination"], "departure": c["departure"], "arrival": c["arrival"], "stops": 1})
        for leg in legs:
            del leg["key"]
            for field in ("from", "to"):
                leg[field+"Name"] = db.execute("SELECT name FROM stops WHERE stop_id=?", (leg[field],)).fetchone()[0]
        return {"legs": legs, "kind": "scheduled", "message": "Orari programmati · solo autobus · cambi alla stessa fermata · margine cambio 2 min · nessun tratto a piedi"}
