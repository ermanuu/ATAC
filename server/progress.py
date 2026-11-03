"""Conservative next-arrival progress, distinct from a geographic GPS position."""
from datetime import datetime
from dataclasses import dataclass
from google.transit import gtfs_realtime_pb2 as pb
from . import transit as t
from .realtime_utils import stop_event_index, stop_predictions


@dataclass(frozen=True)
class ArrivalProgress:
    index: int | None
    timestamp: int
    upcoming: int | None


def next_arrival(vehicle, trip, stops, start, now, live, windows):
    if start is None or not trip or not live or not live.get('available'):
        return None
    candidates = []
    bounds = []
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
        if not 0 <= now - stamp <= 180:
            continue
        date = update.trip.start_date or vehicle.trip.start_date
        epochs = [epoch for epoch, active in windows if trip['service_id'] in active and
                  (datetime.fromtimestamp(epoch + 43200, t.ROME).strftime('%Y%m%d') == date if date else
                   epoch + stops[0]['departure'] <= now + 3600 and epoch + stops[-1]['arrival'] >= now - 3600)]
        if len(epochs) != 1:
            continue
        if stamp > latest:
            latest, candidates, bounds = stamp, [], []
        elif stamp < latest:
            continue
        # A newer NO_DATA / dwell / cancellation also supersedes an older
        # forecast that would otherwise move the icon.
        candidates.append(None)
        bounds.append(None)
        if update.trip.schedule_relationship == pb.TripDescriptor.CANCELED:
            continue
        epoch = epochs[0]
        events = {}
        for event in update.stop_time_update:
            index = stop_event_index(event, stops)
            if index is not None:
                events[index] = event
        predictions = stop_predictions(update, stops, epoch)

        def event_times(index):
            return predictions.get(index, {})

        # A fresh ETA that is still in the future is an upper bound, including
        # when GPS projection or an earlier forecast placed this bus too far on.
        for index, prediction in predictions.items():
            arrival = prediction.get('arrival', prediction.get('departure'))
            departure = prediction.get('departure', arrival)
            if arrival is not None and (now <= arrival <= now + 600 or
                                        arrival < now <= departure <= now + 600):
                bounds[-1] = index
                break

        begin = start
        if events and min(events) > start:
            # The provider omits the passed prefix, but the first remaining
            # ETA can cross "now" before the next feed arrives. Requiring it
            # to stay in the future pins the marker behind the stop board.
            # Keep two consecutive, ordered events as the identity anchor.
            first = min(events)
            if predictions.get(first, {}).get('source') != 'direct' or predictions.get(first + 1, {}).get('source') != 'direct':
                continue
            first_times, following_times = event_times(first), event_times(first + 1)
            first_time = first_times.get('arrival', first_times.get('departure'))
            following_time = following_times.get('arrival', following_times.get('departure'))
            if first_time is None or following_time is None or not now - 180 <= first_time <= now + 600 or following_time < first_time:
                continue
            begin = first
        for index in range(begin, len(stops)):
            prediction = predictions.get(index)
            if not prediction or prediction.get('noData'):
                break
            if prediction.get('skipped'):
                continue
            times = event_times(index)
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
                if index > start:
                    candidates[-1] = index
                break
            # A passed event is enough to leave that stop, even when the
            # next ETA is omitted / NO_DATA. It proves only the next segment:
            # missing intermediate events must never authorize a bigger jump.
            if index + 1 < len(stops):
                candidates[-1] = index + 1
    if not candidates:
        return None
    indices = set(candidates)
    index = indices.pop() if len(indices) == 1 and None not in indices else None
    limits = set(bounds)
    upcoming = limits.pop() if len(limits) == 1 and None not in limits else None
    return ArrivalProgress(index, latest, upcoming) if index is not None or upcoming is not None else None
