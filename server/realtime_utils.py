"""Resolve a realtime stop reference consistently in boards and arrivals."""
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
