"""On-demand public transit snapshots for investigating a reported bus marker."""
from datetime import datetime
from google.protobuf.json_format import MessageToDict
from . import transit as t


def vehicle_diagnostics(number, refresh=False):
    if not number or len(number) > 120:
        raise ValueError('Identificativo vettura non valido')
    positions = t.read_live('vehicles', refresh)
    updates = t.read_live('updates', refresh)
    vehicles, predictions = [], []
    trip_ids = set()
    for entity in positions.get('feed').entity if positions.get('feed') is not None else ():
        if not entity.is_deleted and entity.HasField('vehicle'):
            descriptor = entity.vehicle.vehicle
            if number in (descriptor.id, descriptor.label):
                vehicles.append(MessageToDict(entity, preserving_proto_field_name=True))
                trip_ids.add(entity.vehicle.trip.trip_id)
    for entity in updates.get('feed').entity if updates.get('feed') is not None else ():
        if not entity.is_deleted and entity.HasField('trip_update'):
            update = entity.trip_update
            if number in (update.vehicle.id, update.vehicle.label) or update.trip.trip_id in trip_ids:
                predictions.append(MessageToDict(entity, preserving_proto_field_name=True))
    metadata = lambda live: {k: v for k, v in live.items() if k in ('available', 'timestamp', 'error', 'retained', 'feedTimestamps')}
    return {'schema': 1, 'collectedAt': datetime.fromtimestamp(t.time.time(), t.ROME).isoformat(),
            'vehicle': number, 'positions': metadata(positions) | {'entities': vehicles},
            'updates': metadata(updates) | {'entities': predictions}}
