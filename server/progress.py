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


def same_vehicle(left, right):
    if any(getattr(left, field) and getattr(right, field) and
           getattr(left, field) != getattr(right, field) for field in ('id', 'label')):
        return False
    return any(getattr(left, field) and getattr(left, field) == getattr(right, field)
               for field in ('id', 'label'))


def same_journey(left, right):
    return left.trip_id == right.trip_id and not any(
        getattr(left, field) and getattr(right, field) and
        getattr(left, field) != getattr(right, field)
        for field in ('start_date', 'start_time', 'route_id'))


def has_newer_assignment(vehicle, position_timestamp, now, live):
    """Do not draw a previous run after this bus has a newer live assignment."""
    if not live or not live.get('available'):
        return False
    assignments = set()
    for entity in live['feed'].entity:
        if entity.is_deleted or not entity.HasField('trip_update'):
            continue
        update = entity.trip_update
        if not update.trip.trip_id or not same_vehicle(update.vehicle, vehicle.vehicle):
            continue
        stamp = int(update.timestamp or live['timestamp'] or 0)
        if not 0 <= now - stamp <= 180:
            continue
        # Providers can publish the next run while the current one is still
        # active. A concurrent update for this journey keeps its marker valid.
        if same_journey(update.trip, vehicle.trip):
            return False
        if stamp > position_timestamp and update.trip.schedule_relationship != pb.TripDescriptor.CANCELED:
            assignments.add((update.trip.trip_id, update.trip.start_date, update.trip.start_time))
    return len(assignments) == 1


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
        # A shared route/headsign or an ETA alone cannot identify this vehicle.
        if not same_journey(update.trip, vehicle.trip) or not same_vehicle(update.vehicle, vehicle.vehicle):
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
        # Match the stop board: timetable-based propagation must not hold the
        # marker upstream of a later, explicitly reported live passage.
        predictions = stop_predictions(update, stops, epoch, propagate=False)

        def event_times(index):
            return predictions.get(index, {})

        def advance(index):
            if index > start:
                candidates[-1] = max(candidates[-1] or 0, index)

        # A recent direct passage is useful even if the provider has omitted
        # earlier events or marks the terminal NO_DATA. It proves only the
        # segment immediately after that stop, without inventing another ETA.
        for index, prediction in predictions.items():
            arrival = prediction.get('arrival', prediction.get('departure'))
            departure = prediction.get('departure', arrival)
            if index >= start and arrival is not None and now - 180 <= arrival < now:
                advance(index if departure > now else min(index + 1, len(stops) - 1))

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
            # Without a recent passage, omitting a prefix is not enough to
            # prove progress. Require two consecutive, ordered direct events
            # before anchoring to the first remaining future arrival.
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
                    advance(index)
                break
            # This is next-arrival forecast progress, not a GPS measurement.
            # Missing updates alone never prove that the bus has passed.
            if passed is None or passed > now:
                if index > start:
                    advance(index)
                break
            # A passed event is enough to leave that stop, even when the
            # next ETA is omitted / NO_DATA. It proves only the next segment:
            # missing intermediate events must never authorize a bigger jump.
            if index + 1 < len(stops):
                advance(index + 1)
    if not candidates:
        return None
    indices = set(candidates)
    index = indices.pop() if len(indices) == 1 and None not in indices else None
    limits = set(bounds)
    upcoming = limits.pop() if len(limits) == 1 and None not in limits else None
    return ArrivalProgress(index, latest, upcoming) if index is not None or upcoming is not None else None
