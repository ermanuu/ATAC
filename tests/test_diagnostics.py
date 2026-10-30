import unittest
from unittest.mock import patch
from google.transit import gtfs_realtime_pb2 as pb
from server import transit as t
from server.diagnostics import vehicle_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.positions=pb.FeedMessage(); self.updates=pb.FeedMessage()
        for f in (self.positions,self.updates):
            f.header.gtfs_realtime_version='2.0'; f.header.timestamp=1000
        for number in ('2610','9999'):
            e=self.positions.entity.add(); e.id='position-'+number
            v=e.vehicle; v.vehicle.id='rt-'+number; v.vehicle.label=number; v.trip.trip_id='trip-'+number; v.stop_id='74373'; v.current_stop_sequence=20; v.timestamp=990
            e=self.updates.entity.add(); e.id='update-'+number
            u=e.trip_update; u.vehicle.id='rt-'+number; u.vehicle.label=number; u.trip.trip_id='trip-'+number
            event=u.stop_time_update.add(); event.stop_id='74374'; event.stop_sequence=30; event.arrival.time=1120
        reader=patch.object(t.realtime,'read',side_effect=lambda kind,**kwargs:{'available':True,'timestamp':1000,'feed':self.positions if kind=='vehicles' else self.updates})
        self.reader=reader.start(); self.addCleanup(reader.stop)

    def test_snapshot_contains_raw_references_for_only_selected_bus(self):
        result=vehicle_diagnostics('2610')
        self.assertEqual(len(result['positions']['entities']),1)
        self.assertEqual(len(result['updates']['entities']),1)
        self.assertEqual(result['positions']['entities'][0]['vehicle']['stop_id'],'74373')
        self.assertEqual(result['updates']['entities'][0]['trip_update']['stop_time_update'][0]['stop_id'],'74374')
        self.assertNotIn('9999',str(result))

    def test_related_trip_update_is_included_even_without_vehicle_descriptor(self):
        self.updates.entity[0].trip_update.ClearField('vehicle')
        self.assertEqual(len(vehicle_diagnostics('rt-2610')['updates']['entities']),1)

    def test_refresh_is_forwarded_and_missing_vehicle_is_explicitly_empty(self):
        result=vehicle_diagnostics('absent',refresh=True)
        self.assertEqual(result['positions']['entities'],[])
        self.assertTrue(all(call.kwargs=={'force':True} for call in self.reader.call_args_list))
