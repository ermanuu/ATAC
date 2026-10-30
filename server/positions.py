"""Bounded last-known positions across incomplete realtime snapshots."""
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
