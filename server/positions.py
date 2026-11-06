"""Bounded last-known positions across incomplete realtime snapshots."""
import threading
from google.transit import gtfs_realtime_pb2 as pb


class PositionHistory:
    def __init__(self):
        self.entries = {}
        self.measurements = {}

    def merge(self, feed, now):
        seen = set()
        if feed is not None:
            for entity in feed.entity:
                if entity.is_deleted:
                    for key, (old, _, _) in list(self.entries.items()):
                        if old.id == entity.id:
                            del self.entries[key]
                    continue
                if not entity.HasField('vehicle'):
                    continue
                key = entity.vehicle.vehicle.id or entity.id
                seen.add(key)
                clone = pb.FeedEntity()
                clone.CopyFrom(entity)
                # Preserve the original measurement time when later feeds omit it.
                clone.vehicle.timestamp = entity.vehicle.timestamp or feed.header.timestamp
                previous = self.entries.get(key)
                own_timestamp = bool(entity.vehicle.timestamp)
                if previous and clone.vehicle.timestamp < previous[0].vehicle.timestamp:
                    # A delayed response must not move the bus backwards.
                    continue
                value = pb.VehiclePosition()
                value.CopyFrom(clone.vehicle)
                value.ClearField('timestamp')
                value.ClearField('vehicle')
                fingerprint = value.SerializeToString(deterministic=True)
                measurement = self.measurements.get(key)
                if not own_timestamp and measurement and measurement[0] == fingerprint:
                    # Keep this even after the visible history entry expires: a
                    # changing feed header cannot revive an unchanged old bus.
                    clone.vehicle.timestamp = measurement[1]
                self.measurements[key] = (fingerprint, clone.vehicle.timestamp, now)
                self.entries[key] = (clone, now, own_timestamp)
        self.measurements = {key: value for key, value in self.measurements.items() if now - value[2] <= 21600}
        result = pb.FeedMessage()
        result.header.gtfs_realtime_version = '2.0'
        result.header.timestamp = int(now)
        retained = []
        feed_timestamps = []
        for key, (entity, last_seen, own_timestamp) in list(self.entries.items()):
            age = now - entity.vehicle.timestamp
            if age > 180 or age < -60 or (key not in seen and now - last_seen > 45):
                del self.entries[key]
                continue
            result.entity.add().CopyFrom(entity)
            if not own_timestamp:
                feed_timestamps.append(entity.id)
            if key not in seen:
                retained.append(entity.id)
        return result, retained, feed_timestamps


class MarkerHistory:
    """Keep a trip's displayed progress without refreshing old location evidence."""
    def __init__(self):
        self.entries = {}
        self.lock = threading.Lock()
        self.last_cleanup = 0

    def resolve(self, board, journey, index, item, now):
        # Without a trip ID there is no reliable boundary between two runs.
        if not journey[0]:
            return (index, item) if index is not None else None
        key = (*board, item['id'])
        reference = item.get('referenceStopIndex')
        observed_progress = (reference, item['status'] == 'STOPPED_AT') if reference is not None else (-1, False)
        with self.lock:
            if now - self.last_cleanup >= 60:
                self.entries = {k: v for k, v in self.entries.items() if now - v[3] <= 21600}
                self.last_cleanup = now
            previous = self.entries.get(key)
            same_journey = (previous and previous[0][0] == journey[0] and all(
                not before or not after or before == after for before, after in zip(previous[0][1:], journey[1:])))
            if same_journey:
                # An omitted service date/start time does not identify a new run.
                journey = tuple(after or before for before, after in zip(previous[0], journey))
                _, old_index, old_item, _, recorded_progress = previous
                old_progress = (old_index, old_item['placement'] == 'at')
                progress = (index, item['placement'] == 'at') if index is not None else None
                evidence = lambda value: max(value['timestamp'], value.get('predictionTimestamp') or 0)
                bound, stamp = item.get('upcomingStopIndex'), item.get('upcomingTimestamp')
                # A revised ETA may correct an earlier estimate, but cannot
                # undo progress already reported by the vehicle itself.
                corrected_forecast = (old_item['positionSource'] == 'predictions' and
                                      progress is not None and progress >= recorded_progress and
                                      bound is not None and old_index > bound and
                                      stamp is not None and 0 <= now - stamp <= 180 and
                                      stamp > (old_item.get('upcomingTimestamp') or old_item.get('predictionTimestamp') or 0))
                incoming_forecast = item.get('upcomingTimestamp') or item.get('predictionTimestamp')
                previous_forecast = old_item.get('upcomingTimestamp') or old_item.get('predictionTimestamp')
                older_forecast = incoming_forecast is not None and previous_forecast is not None and incoming_forecast < previous_forecast
                if older_forecast or not corrected_forecast and (progress is None or progress < old_progress or evidence(item) < evidence(old_item)):
                    # Never turn a missing forecast / inconsistent new reference
                    # into backward travel. Keep the original timestamps, and
                    # remember progress even after the icon expires so repeated
                    # bad packets cannot revive it at an already passed stop.
                    self.entries[key] = (journey, old_index, old_item, now, recorded_progress)
                    prediction = old_item.get('predictionTimestamp')
                    if 0 <= now - old_item['timestamp'] <= 180 and (
                        old_item['positionSource'] != 'predictions' or
                        prediction is not None and 0 <= now - prediction <= 180
                    ):
                        return old_index, old_item | {'retained': True}
                    return None
                observed_progress = max(observed_progress, recorded_progress)
            if index is None:
                return None
            self.entries[key] = (journey, index, item.copy(), now, observed_progress)
            return index, item
