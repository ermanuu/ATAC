"""Resolve a realtime stop reference consistently in boards and arrivals."""
def stop_event_time(event, field, scheduled_time):
    """Use the same absolute time / delay precedence in arrivals and markers."""
    if event.HasField(field):
        prediction = getattr(event, field)
        if prediction.HasField('time'):
            return int(prediction.time)
        if prediction.HasField('delay'):
            return int(scheduled_time + prediction.delay)
    return None


def stop_event_index(event, stops):
    matches = [i for i, stop in enumerate(stops) if event.stop_id and stop['stop_id'] == event.stop_id]
    if len(matches) == 1:
        return matches[0]
    if event.HasField('stop_sequence'):
        indices = [i for i, stop in enumerate(stops) if stop['sequence'] == event.stop_sequence and
                   (not event.stop_id or i in matches)]
        if len(indices) == 1:
            return indices[0]
    return None


def stop_predictions(update, stops, epoch):
    """Resolve direct events and GTFS-RT forward delay propagation.

    Omitted stops inherit the last live delay until the next explicit update.
    NO_DATA clears that delay; SKIPPED omits the stop without clearing it.
    """
    from google.transit import gtfs_realtime_pb2 as pb
    events = {}
    for event in update.stop_time_update:
        index = stop_event_index(event, stops)
        if index is not None:
            events[index] = event
    result = {}
    delay = None
    for index, stop in enumerate(stops):
        event = events.get(index)
        if event is not None and event.schedule_relationship == pb.TripUpdate.StopTimeUpdate.NO_DATA:
            result[index] = {'noData': True}
            delay = None
            continue
        if event is not None and event.schedule_relationship == pb.TripUpdate.StopTimeUpdate.SKIPPED:
            result[index] = {'skipped': True}
            continue
        times = {}
        if event is not None:
            for field in ('arrival', 'departure'):
                value = stop_event_time(event, field, epoch + stop[field])
                if value is not None:
                    times[field] = value
        if times:
            field = 'departure' if 'departure' in times else 'arrival'
            delay = times[field] - int(epoch + stop[field])
            result[index] = times | {'source': 'direct'}
        elif delay is not None:
            result[index] = {field: int(epoch + stop[field] + delay) for field in ('arrival', 'departure')} | {'source': 'propagated'}
    return result
