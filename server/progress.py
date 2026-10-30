"""Conservative next-arrival progress, distinct from a geographic GPS position."""
from datetime import datetime
from google.transit import gtfs_realtime_pb2 as pb
from . import transit as t


def next_arrival(vehicle, trip, stops, start, measurement_time, now, live, windows):
    if start is None or not trip or not live or not live.get('available'):
        return None
    candidates = []
    latest = 0
    for entity in live['feed'].entity:
        if entity.is_deleted or not entity.HasField('trip_update'):
            continue
        update = entity.trip_update
        if update.trip.trip_id != vehicle.trip.trip_id:
            continue
        descriptor = update.vehicle
        # A shared route/headsign or an ETA alone cannot identify this vehicle.
        if descriptor.id and vehicle.vehicle.id and descriptor.id != vehicle.vehicle.id:
            continue
        if descriptor.label and vehicle.vehicle.label and descriptor.label != vehicle.vehicle.label:
            continue
        identity = (descriptor.id and descriptor.id == vehicle.vehicle.id) or (descriptor.label and descriptor.label == vehicle.vehicle.label)
        if not identity:
            continue
        if any(getattr(update.trip, field) and getattr(vehicle.trip, field) and
               getattr(update.trip, field) != getattr(vehicle.trip, field)
               for field in ('start_date', 'start_time', 'route_id')):
            continue
        stamp = int(update.timestamp or live['timestamp'] or 0)
        if stamp < measurement_time or not 0 <= now - stamp <= 90:
            continue
        date = update.trip.start_date or vehicle.trip.start_date
        epochs = [epoch for epoch, active in windows if trip['service_id'] in active and
                  (datetime.fromtimestamp(epoch + 43200, t.ROME).strftime('%Y%m%d') == date if date else
                   epoch + stops[0]['departure'] <= now + 3600 and epoch + stops[-1]['arrival'] >= now - 3600)]
        if len(epochs) != 1:
            continue
        if stamp > latest:
            latest, candidates = stamp, []
        elif stamp < latest:
            continue
        # A newer NO_DATA / dwell / cancellation also supersedes an older
        # forecast that would otherwise move the icon.
        candidates.append(None)
        if update.trip.schedule_relationship == pb.TripDescriptor.CANCELED:
            continue
        epoch = epochs[0]
        events = {}
        for event in update.stop_time_update:
            if event.HasField('stop_sequence'):
                indices = [i for i, stop in enumerate(stops) if stop['sequence'] == event.stop_sequence and
                           (not event.stop_id or event.stop_id == stop['stop_id'])]
            else:
                indices = [i for i, stop in enumerate(stops) if stop['stop_id'] == event.stop_id]
            if len(indices) == 1:
                events[indices[0]] = event
        for index in range(start, len(stops)):
            event = events.get(index)
            if event is None or event.schedule_relationship == pb.TripUpdate.StopTimeUpdate.NO_DATA:
                break
            if event.schedule_relationship == pb.TripUpdate.StopTimeUpdate.SKIPPED:
                continue
            times = {}
            for field in ('arrival', 'departure'):
                if event.HasField(field):
                    prediction = getattr(event, field)
                    if prediction.HasField('time'):
                        times[field] = int(prediction.time)
                    elif prediction.HasField('delay'):
                        times[field] = int(epoch + stops[index][field] + prediction.delay)
            arrival = times.get('arrival', times.get('departure'))
            passed = times.get('departure', times.get('arrival'))
            if arrival is None:
                break
            if arrival >= now:
                if index > start and arrival <= now + 600:
                    candidates[-1] = index
                break
            # This is next-arrival forecast progress, not a GPS measurement.
            # Every crossed stop needs an explicit past event; missing updates
            # must never be interpreted as stops the bus has already passed.
            if passed is None or passed > now:
                break
    if not candidates:
        return None
    indices = set(candidates)
    return (indices.pop(), latest) if len(indices) == 1 and None not in indices else None
