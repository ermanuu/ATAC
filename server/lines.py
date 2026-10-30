"""Direction-specific line boards, using the existing GTFS database."""
from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
import time

from google.transit import gtfs_realtime_pb2 as pb
from . import transit as t


def patterns(db, route_id, now):
    windows = list(t.service_windows(db, now, 3600))
    services = set().union(*(active for _, active in windows))
    trips = {r['trip_id']: dict(r) for r in db.execute(
        'SELECT * FROM trips WHERE route_id=? ORDER BY trip_id', (route_id,)) if r['service_id'] in services}
    sequences = defaultdict(list)
    for row in db.execute('''SELECT ti.trip_id,ti.sequence,ti.departure,ti.pickup,s.* FROM times ti
                            JOIN trips tr ON tr.trip_id=ti.trip_id JOIN stops s ON s.stop_id=ti.stop_id
                            WHERE tr.route_id=? ORDER BY ti.trip_id,ti.sequence''', (route_id,)):
        if row['trip_id'] in trips:
            sequences[row['trip_id']].append(dict(row))
    groups = {}
    for trip_id, trip in trips.items():
        stops = sequences[trip_id]
        if not stops:
            continue
        key = (trip['direction'], trip['headsign'], tuple(s['stop_id'] for s in stops))
        if key not in groups:
            identifier = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:16]
            groups[key] = {'id': identifier, 'direction': trip['direction'], 'headsign': trip['headsign'] or stops[-1]['name'],
                           'fromName': stops[0]['name'], 'toName': stops[-1]['name'], 'stopCount': len(stops),
                           'stops': stops, 'trips': {}}
        groups[key]['trips'][trip_id] = trip
    return sorted(groups.values(), key=lambda g: (g['direction'], g['headsign'], g['fromName'], g['id'])), sequences, windows


def summary(group):
    return {k: v for k, v in group.items() if k not in ('stops', 'trips')}


def terminal_departures(group, sequences, windows, now, live):
    updates = {}
    if live['available']:
        for entity in live['feed'].entity:
            if not entity.is_deleted and entity.HasField('trip_update'):
                update = entity.trip_update
                if not update.timestamp or 0 <= now - update.timestamp <= 180:
                    updates[(update.trip.trip_id, update.trip.start_date)] = update
    result = []
    for epoch, active in windows:
        service_date = datetime.fromtimestamp(epoch + 43200, t.ROME).strftime('%Y%m%d')
        for trip_id, trip in group['trips'].items():
            first = sequences[trip_id][0]
            if trip['service_id'] not in active or first['pickup'] == 1:
                continue
            scheduled = int(epoch + first['departure'])
            item = {'tripId': trip_id, 'serviceDate': service_date, 'scheduledTime': scheduled,
                    'time': scheduled, 'kind': 'scheduled'}
            update = updates.get((trip_id, service_date))
            if update is None:
                update = updates.get((trip_id, ''))
            skipped = False
            if update is not None:
                if update.trip.schedule_relationship in (pb.TripDescriptor.CANCELED,):
                    continue
                for event in update.stop_time_update:
                    # Match the first occurrence, including loop routes with a repeated terminus.
                    if event.HasField('stop_sequence'):
                        matches = event.stop_sequence == first['sequence']
                    else:
                        matches = event.stop_id == first['stop_id']
                    if not matches:
                        continue
                    if event.schedule_relationship == pb.TripUpdate.StopTimeUpdate.SKIPPED:
                        skipped = True
                    elif event.schedule_relationship != pb.TripUpdate.StopTimeUpdate.NO_DATA and event.HasField('departure'):
                        prediction = event.departure
                        if prediction.HasField('time'):
                            item.update(time=int(prediction.time), kind='live')
                        elif prediction.HasField('delay'):
                            item.update(time=scheduled + prediction.delay, kind='live')
                    break
            if not skipped and now - 600 <= item['time'] <= now + 3600:
                result.append(item)
    return sorted(result, key=lambda i: (i['time'], i['tripId']))


def stop_distance(lat, lon, stop):
    # Local equirectangular distance is sufficient for the 500 m fallback threshold.
    return math.hypot((lat - stop['lat']) * 111320,
                      (lon - stop['lon']) * 111320 * math.cos(math.radians(lat)))


def place_vehicles(group, groups, sequences, now, live):
    stops = [{k: v for k, v in s.items() if k not in ('trip_id', 'departure', 'pickup')} |
             {'vehiclesAt': [], 'vehiclesBefore': []} for s in group['stops']]
    if not live['available']:
        return stops, 0
    unplaced = 0
    selected_ids = tuple(s['stop_id'] for s in stops)
    for entity in live['feed'].entity:
        if entity.is_deleted or not entity.HasField('vehicle'):
            continue
        vehicle = entity.vehicle
        timestamp = int(vehicle.timestamp or live['timestamp'])
        if not 0 <= now - timestamp <= 180:
            continue
        if vehicle.trip.HasField('direction_id') and group['direction'] and str(vehicle.trip.direction_id) != group['direction']:
            continue
        trip_id = vehicle.trip.trip_id
        if trip_id not in group['trips']:
            if vehicle.trip.route_id != next(iter(group['trips'].values()))['route_id']:
                continue
            # With a known trip, never mix another direction or variant into this board.
            if trip_id in sequences:
                continue
            if not vehicle.trip.HasField('direction_id') or str(vehicle.trip.direction_id) != group['direction']:
                continue
            # Resolve an unknown trip only when direction + stop identify one pattern.
            candidates = [g for g in groups if g['direction'] == group['direction'] and
                          any(s['stop_id'] == vehicle.stop_id for s in g['stops'])]
            if len(candidates) != 1 or candidates[0]['id'] != group['id']:
                continue
        actual_route = vehicle.trip.route_id
        if actual_route and actual_route != group['trips'][next(iter(group['trips']))]['route_id']:
            continue
        if vehicle.trip.schedule_relationship in (pb.TripDescriptor.CANCELED,):
            continue
        index = None
        estimated = False
        actual_stops = sequences.get(trip_id)
        if actual_stops and vehicle.HasField('current_stop_sequence'):
            index = next((i for i, s in enumerate(actual_stops) if s['sequence'] == vehicle.current_stop_sequence), None)
        if index is None and vehicle.stop_id:
            matches = [i for i, stop_id in enumerate(selected_ids) if stop_id == vehicle.stop_id]
            if len(matches) == 1:
                index = matches[0]
        if index is None and vehicle.HasField('position'):
            lat, lon = vehicle.position.latitude, vehicle.position.longitude
            distances = [stop_distance(lat, lon, s) for s in stops]
            nearest = min(range(len(stops)), key=lambda i: distances[i])
            if distances[nearest] <= 500 and selected_ids.count(selected_ids[nearest]) == 1:
                index = nearest
                estimated = True
        if index is None:
            unplaced += 1
            continue
        stopped = vehicle.current_status == pb.VehiclePosition.STOPPED_AT
        placement = 'at' if stopped or estimated else 'before'
        item = {'id': vehicle.vehicle.id or entity.id, 'timestamp': timestamp,
                'status': pb.VehiclePosition.VehicleStopStatus.Name(vehicle.current_status),
                'estimated': estimated, 'placement': placement,
                'lat': vehicle.position.latitude if vehicle.HasField('position') else None,
                'lon': vehicle.position.longitude if vehicle.HasField('position') else None}
        stops[index]['vehiclesAt' if placement == 'at' else 'vehiclesBefore'].append(item)
    return stops, unplaced


def line_detail(route_id, variant=None, now=None):
    now = int(time.time()) if now is None else now
    with t.connect() as db:
        route = db.execute('SELECT * FROM routes WHERE route_id=? AND type=3', (route_id,)).fetchone()
        if not route:
            raise ValueError('Linea autobus non trovata')
        groups, sequences, windows = patterns(db, route_id, now)
        result = {'route': dict(route), 'variants': [summary(g) for g in groups]}
    if not variant:
        # The direction picker needs no realtime requests, vehicle list or stop list.
        return result
    selected = next((g for g in groups if g['id'] == variant), None)
    if selected is None:
        raise ValueError('Direzione non disponibile: torna alla scelta della direzione')
    vehicles = t.realtime.read('vehicles')
    updates = t.realtime.read('updates')
    positioned_stops, unplaced = place_vehicles(selected, groups, sequences, now, vehicles)
    result.update(selectedVariant=summary(selected), stops=positioned_stops,
                  departures=terminal_departures(selected, sequences, windows, now, updates),
                  window={'from': now - 600, 'to': now + 3600},
                  liveAvailable=vehicles['available'], timestamp=vehicles['timestamp'],
                  departureLiveAvailable=updates['available'], departureTimestamp=updates['timestamp'],
                  unplacedVehicleCount=unplaced)
    return result
