"""Direction boards: time bounds, variants, GTFS-RT positioning and cancellation."""
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from google.transit import gtfs_realtime_pb2 as pb
from server import transit as t
from server.app import Handler
from test_transit import fixture


class LineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, value in [('DATA', Path(self.temp.name)), ('DB', Path(self.temp.name)/'transit.sqlite')]:
            context = patch.object(t, name, value)
            context.start()
            self.addCleanup(context.stop)
        t.import_gtfs(fixture())
        self.now = int(datetime(2026, 10, 30, 10, 0, tzinfo=t.ROME).timestamp())
        self.feeds = {}
        self.reader = patch.object(t.realtime, 'read', side_effect=lambda kind, **kwargs: self.feeds.get(kind, {'available': False, 'timestamp': None}))
        self.read = self.reader.start()
        self.addCleanup(self.reader.stop)

    def variant(self, headsign='Cambio'):
        return next(v['id'] for v in t.route_detail('r1', now=self.now)['variants'] if v['headsign'] == headsign)

    def board(self, headsign='Cambio'):
        return t.route_detail('r1', self.variant(headsign), self.now)

    def add_trip(self, trip, departure, headsign='Cambio', direction='0', stops=('a','b')):
        with sqlite3.connect(t.DB) as db:
            db.execute('INSERT INTO trips VALUES (?,?,?,?,?)', (trip,'r1','daily',headsign,direction))
            db.executemany('INSERT INTO times VALUES (?,?,?,?,?,?,?)', (
                (trip, stop, (i+1)*10, departure+i*600, departure+i*600, 0, 0) for i,stop in enumerate(stops)))

    def feed(self, kind):
        f = pb.FeedMessage()
        f.header.gtfs_realtime_version = '2.0'
        f.header.timestamp = self.now
        self.feeds[kind] = {'available': True, 'timestamp': self.now, 'feed': f}
        return f

    def vehicle(self, feed, identifier, trip='t1', sequence=None, stop='', status=pb.VehiclePosition.STOPPED_AT, timestamp=None):
        entity = feed.entity.add()
        entity.id = identifier
        v = entity.vehicle
        v.vehicle.id = identifier
        v.trip.trip_id = trip
        v.trip.route_id = 'r1'
        v.timestamp = self.now if timestamp is None else timestamp
        v.current_status = status
        if sequence is not None:
            v.current_stop_sequence = sequence
        v.stop_id = stop
        return v

    def test_direction_picker_does_not_request_vehicles(self):
        result = t.route_detail('r1', now=self.now)
        self.assertEqual(len(result['variants']), 1)
        self.assertNotIn('departures', result)
        self.assertNotIn('vehicles', result)
        self.read.assert_not_called()
        self.assertEqual(result['variants'][0]['fromName'], 'Origine')

    def test_picker_excludes_finished_and_later_variants(self):
        self.add_trip('school', 8*3600, headsign='Scuola')
        self.add_trip('deviation', 12*3600, headsign='Deviata')
        self.add_trip('running', 9*3600+55*60, headsign='In viaggio')
        self.add_trip('next', 11*3600, headsign='Prossima')
        names = {v['headsign'] for v in t.route_detail('r1', now=self.now)['variants']}
        self.assertEqual(names, {'Cambio', 'In viaggio', 'Prossima'})

    def test_picker_obeys_service_exception(self):
        now = int(datetime(2026, 10, 31, 10, 0, tzinfo=t.ROME).timestamp())
        self.assertEqual(t.route_detail('r1', now=now)['variants'], [])

    def test_old_position_is_not_drawn_as_current(self):
        self.vehicle(self.feed('vehicles'), 'old', sequence=10, timestamp=self.now-91)
        self.assertEqual(self.board()['stops'][0]['vehiclesAt'], [])

    def test_board_uses_public_label_not_tracking_id(self):
        v=self.vehicle(self.feed('vehicles'), 'technical-123', sequence=10)
        v.vehicle.label='4512'
        item=self.board()['stops'][0]['vehiclesAt'][0]
        self.assertEqual(item['id'], 'technical-123')
        self.assertEqual(item['vehicleId'], '4512')
        v.vehicle.ClearField('label')
        self.assertIsNone(self.board()['stops'][0]['vehiclesAt'][0]['vehicleId'])

    def test_history_only_positions_are_not_current_bus_icons(self):
        self.vehicle(self.feed('vehicles'), 'missing', sequence=10)
        self.feeds['vehicles']['retained']=['missing']
        self.assertEqual(self.board()['stops'][0]['vehiclesAt'], [])

    def test_manual_board_refresh_forces_both_sources(self):
        selected=self.variant()
        t.route_detail('r1', selected, self.now, refresh=True)
        self.assertEqual(self.read.call_args_list[-2].kwargs, {'force':True})
        self.assertEqual(self.read.call_args_list[-1].kwargs, {'force':True})

    def test_departure_window_includes_exact_bounds(self):
        for name, at in [('too_early', 35399), ('start',35400), ('recent',35940), ('end',39600), ('too_late',39601)]:
            self.add_trip(name, at)
        result = self.board()
        self.assertEqual([d['tripId'] for d in result['departures']], ['start','recent','t1','end'])
        self.assertEqual(result['window'], {'from': self.now-600, 'to': self.now+3600})
        self.assertTrue(all(d['kind'] == 'scheduled' for d in result['departures']))

    def test_same_headsign_different_pattern_gets_separate_choice(self):
        self.add_trip('alternative', 36000, stops=('a','c'))
        result = t.route_detail('r1', now=self.now)
        variants = [v for v in result['variants'] if v['direction'] == '0']
        self.assertEqual(len(variants), 2)
        for v in variants:
            board = t.route_detail('r1', v['id'], self.now)
            self.assertEqual(len(board['departures']), 1)
            self.assertEqual(board['stops'][-1]['name'], v['toName'])

    def test_invalid_variant_and_route(self):
        with self.assertRaisesRegex(ValueError, 'Direzione non disponibile'):
            t.route_detail('r1', 'invalid', self.now)
        with self.assertRaisesRegex(ValueError, 'Linea autobus non trovata'):
            t.route_detail('missing', now=self.now)

    def test_after_midnight_uses_previous_service_day(self):
        self.now = int(datetime(2026,10,31,0,59,tzinfo=t.ROME).timestamp())
        departures = self.board('Notturno')['departures']
        self.assertEqual([d['tripId'] for d in departures], ['night'])
        self.assertEqual(departures[0]['serviceDate'], '20261030')

    def test_terminal_live_delay_and_cancellation(self):
        f = self.feed('updates')
        e = f.entity.add(); e.id = 'update'
        u = e.trip_update; u.trip.trip_id = 't1'; u.trip.start_date = '20261030'
        event = u.stop_time_update.add(); event.stop_sequence = 10; event.departure.delay = 120
        departure = self.board()['departures'][0]
        self.assertEqual(departure['time'], self.now+120)
        self.assertEqual(departure['scheduledTime'], self.now)
        self.assertEqual(departure['kind'], 'live')
        u.trip.schedule_relationship = pb.TripDescriptor.CANCELED
        self.assertEqual(self.board()['departures'], [])

    def test_arrival_at_terminus_is_not_a_departure_prediction(self):
        f = self.feed('updates')
        e = f.entity.add(); e.id = 'arrival-only'
        u = e.trip_update; u.trip.trip_id = 't1'
        event = u.stop_time_update.add(); event.stop_id = 'a'; event.arrival.time = self.now-300
        self.assertEqual(self.board()['departures'][0]['kind'], 'scheduled')

    def test_live_predictions_are_filtered_by_adjusted_time(self):
        self.add_trip('late', 35399)
        f = self.feed('updates')
        e=f.entity.add(); e.id='late'; e.trip_update.trip.trip_id='late'
        event=e.trip_update.stop_time_update.add(); event.stop_sequence=10; event.departure.delay=120
        self.assertIn('late', [d['tripId'] for d in self.board()['departures']])
        event.departure.time=self.now+3601
        self.assertNotIn('late', [d['tripId'] for d in self.board()['departures']])

    def test_wrong_day_and_stale_update_keep_scheduled_time(self):
        f = self.feed('updates')
        e=f.entity.add(); e.id='old'; u=e.trip_update; u.trip.trip_id='t1'; u.trip.start_date='20261031'
        event=u.stop_time_update.add(); event.stop_id='a'; event.departure.delay=300
        self.assertEqual(self.board()['departures'][0]['kind'], 'scheduled')
        u.trip.start_date='20261030'; u.timestamp=self.now-181
        self.assertEqual(self.board()['departures'][0]['kind'], 'scheduled')

    def test_positioning_at_stop_and_between_stops_without_gps(self):
        f = self.feed('vehicles')
        self.vehicle(f,'stopped',sequence=10,stop='a')
        self.vehicle(f,'moving',sequence=20,stop='b',status=pb.VehiclePosition.IN_TRANSIT_TO)
        self.vehicle(f,'opposite',trip='night',sequence=1,stop='a')
        self.vehicle(f,'stale',sequence=10,timestamp=self.now-91)
        conflicting = self.vehicle(f,'conflicting-direction',sequence=10,stop='a')
        conflicting.trip.direction_id = 1
        result=self.board()
        self.assertEqual([v['id'] for v in result['stops'][0]['vehiclesAt']], ['stopped'])
        self.assertEqual([v['id'] for v in result['stops'][1]['vehiclesBefore']], ['moving'])
        self.assertFalse(result['stops'][1]['vehiclesAt'])

    def test_loop_stop_sequence_locates_second_occurrence(self):
        self.add_trip('loop',36000,headsign='Anello',stops=('a','b','a'))
        f=self.feed('vehicles'); self.vehicle(f,'loop-bus',trip='loop',sequence=30,stop='a')
        result=self.board('Anello')
        self.assertFalse(result['stops'][0]['vehiclesAt'])
        self.assertEqual(result['stops'][2]['vehiclesAt'][0]['id'], 'loop-bus')

    def test_gps_fallback_is_labelled_and_far_positions_are_not_placed(self):
        f=self.feed('vehicles')
        v=self.vehicle(f,'approx'); v.position.latitude=41.91; v.position.longitude=12.50
        v=self.vehicle(f,'far'); v.position.latitude=0; v.position.longitude=0
        result=self.board()
        self.assertTrue(result['stops'][1]['vehiclesAt'][0]['estimated'])
        self.assertEqual(result['unplacedVehicleCount'],1)

    def test_unknown_trip_needs_explicit_direction_and_correct_route(self):
        f=self.feed('vehicles')
        self.vehicle(f,'no-direction',trip='unknown',stop='b')
        v=self.vehicle(f,'unambiguous',trip='unknown2',stop='b'); v.trip.direction_id=0
        v=self.vehicle(f,'wrong-route',trip='unknown3',stop='b'); v.trip.direction_id=0; v.trip.route_id='r2'
        result=self.board()
        self.assertEqual([v['id'] for v in result['stops'][1]['vehiclesAt']],['unambiguous'])

    def test_gps_advances_bus_when_stop_sequence_is_stuck(self):
        self.add_trip('progress',36000,headsign='Progress',stops=('a','b','c'))
        feed=self.feed('vehicles')
        v=self.vehicle(feed,'advancing',trip='progress',sequence=10,stop='a')
        v.position.latitude=41.90; v.position.longitude=12.49
        self.assertEqual(self.board('Progress')['stops'][0]['vehiclesAt'][0]['id'],'advancing')
        self.now += 15; v.timestamp=self.now
        v.position.latitude=41.905; v.position.longitude=12.495
        first=self.board('Progress')
        self.assertFalse(first['stops'][0]['vehiclesAt'])
        self.assertEqual(first['stops'][1]['vehiclesBefore'][0]['id'],'advancing')
        self.assertTrue(first['stops'][1]['vehiclesBefore'][0]['estimated'])
        self.now += 15; v.timestamp=self.now
        v.position.latitude=41.915; v.position.longitude=12.505
        second=self.board('Progress')
        self.assertFalse(second['stops'][1]['vehiclesBefore'])
        self.assertEqual(second['stops'][2]['vehiclesBefore'][0]['id'],'advancing')

    def test_stop_id_wins_over_conflicting_sequence_counter(self):
        self.add_trip('rome',36000,headsign='EUR FERMI (MB)',stops=('a','b','c'))
        v=self.vehicle(self.feed('vehicles'),'2641',trip='rome',sequence=20,stop='c',status=pb.VehiclePosition.IN_TRANSIT_TO)
        v.vehicle.label='2641'
        v.position.latitude=41.905; v.position.longitude=12.495
        board=self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertEqual(board['stops'][2]['vehiclesBefore'][0]['vehicleId'],'2641')
        self.assertEqual(board['stops'][2]['vehiclesBefore'][0]['positionSource'],'stop_id')

    def test_gps_does_not_regress_valid_next_stop(self):
        self.add_trip('rome',36000,headsign='EUR FERMI (MB)',stops=('a','b','c'))
        v=self.vehicle(self.feed('vehicles'),'2641',trip='rome',sequence=30,stop='c',status=pb.VehiclePosition.IN_TRANSIT_TO)
        v.position.latitude=41.905; v.position.longitude=12.495
        board=self.board('EUR FERMI (MB)')
        self.assertEqual(board['stops'][2]['vehiclesBefore'][0]['id'],'2641')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])

    def rome_forecast(self):
        self.add_trip('rome',36000,headsign='EUR FERMI (MB)',stops=('a','b','c'))
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE stops SET name='NAIROBI/S. EUGENIO (H)' WHERE stop_id='b'")
            db.execute("UPDATE stops SET name='AFRICA/ARTE' WHERE stop_id='c'")
        v=self.vehicle(self.feed('vehicles'),'technical-2641',trip='rome',sequence=20,stop='b',status=pb.VehiclePosition.IN_TRANSIT_TO,timestamp=self.now-30)
        v.vehicle.label='2641'
        updates=self.feed('updates'); e=updates.entity.add(); e.id='forecast-2641'
        u=e.trip_update; u.trip.trip_id='rome'; u.trip.start_date='20261030'
        u.vehicle.id='technical-2641'; u.vehicle.label='2641'; u.timestamp=self.now
        event=u.stop_time_update.add(); event.stop_sequence=20; event.arrival.time=self.now-15
        event=u.stop_time_update.add(); event.stop_sequence=30; event.arrival.time=self.now+20
        return v,u

    def test_2641_forecast_is_before_africa_not_nairobi(self):
        self.rome_forecast()
        board=self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertEqual(board['stops'][2]['name'],'AFRICA/ARTE')
        item=board['stops'][2]['vehiclesBefore'][0]
        self.assertEqual(item['vehicleId'],'2641')
        self.assertEqual(item['positionSource'],'predictions')
        self.assertEqual(item['timestamp'],self.now-30)
        self.assertEqual(item['predictionTimestamp'],self.now)

    def test_forecast_for_other_vehicle_does_not_move_icon(self):
        _,u=self.rome_forecast(); u.vehicle.id='other'; u.vehicle.label='2618'
        self.assertEqual(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'][0]['vehicleId'],'2641')

    def test_older_forecast_cannot_override_newer_position(self):
        v,u=self.rome_forecast(); v.timestamp=self.now; u.timestamp=self.now-30
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_equal_timestamp_forecast_can_resolve_next_arrival(self):
        v,_=self.rome_forecast(); v.timestamp=self.now
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'])

    def test_missing_earlier_prediction_cannot_skip_a_stop(self):
        _,u=self.rome_forecast(); del u.stop_time_update[0]
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_dwell_departure_still_future_does_not_advance(self):
        _,u=self.rome_forecast(); u.stop_time_update[0].departure.time=self.now+10
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_delay_only_forecasts_resolve_same_next_stop(self):
        self.now += 1200
        _,u=self.rome_forecast()
        u.stop_time_update[0].arrival.ClearField('time'); u.stop_time_update[0].arrival.delay=590
        u.stop_time_update[1].arrival.ClearField('time'); u.stop_time_update[1].arrival.delay=20
        self.assertEqual(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]['positionSource'],'predictions')

    def test_forecast_without_vehicle_identity_does_not_move_icon(self):
        _,u=self.rome_forecast(); u.ClearField('vehicle')
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_no_data_event_cannot_be_treated_as_passed_stop(self):
        _,u=self.rome_forecast(); u.stop_time_update[0].schedule_relationship=pb.TripUpdate.StopTimeUpdate.NO_DATA
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_newer_no_data_supersedes_older_progress_forecast(self):
        _,u=self.rome_forecast(); u.timestamp=self.now-5
        newer=self.feeds['updates']['feed'].entity.add(); newer.id='newer'
        newer.trip_update.CopyFrom(u); newer.trip_update.timestamp=self.now
        newer.trip_update.stop_time_update[0].schedule_relationship=pb.TripUpdate.StopTimeUpdate.NO_DATA
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_prediction_on_wrong_service_day_does_not_move_icon(self):
        _,u=self.rome_forecast(); u.trip.start_date='20261031'
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_moving_bus_advances_past_declared_next_stop(self):
        self.add_trip('progress',36000,headsign='Progress',stops=('a','b','c'))
        feed=self.feed('vehicles')
        v=self.vehicle(feed,'passed',trip='progress',sequence=20,stop='b',status=pb.VehiclePosition.IN_TRANSIT_TO)
        v.position.latitude=41.915; v.position.longitude=12.505
        board=self.board('Progress')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertEqual(board['stops'][2]['vehiclesBefore'][0]['id'],'passed')

    def test_vehicle_icon_expires_after_ninety_seconds(self):
        feed=self.feed('vehicles')
        self.vehicle(feed,'expired',sequence=10,timestamp=self.now-91)
        self.vehicle(feed,'boundary',sequence=10,timestamp=self.now-90)
        self.assertEqual([v['id'] for v in self.board()['stops'][0]['vehiclesAt']],['boundary'])

    def test_feed_updated_during_download_is_not_discarded_as_future(self):
        selected=self.variant()
        feed=self.feed('vehicles')
        self.vehicle(feed,'fresh-during-fetch',sequence=10,timestamp=self.now+10)
        with patch('server.lines.time.time',side_effect=[self.now,self.now+20]):
            board=t.route_detail('r1',selected)
        self.assertEqual(board['stops'][0]['vehiclesAt'][0]['id'],'fresh-during-fetch')

    def test_api_forwards_selected_direction(self):
        handler=object.__new__(Handler)
        handler.path=f'/api/routes/r1?variant={self.variant()}'
        handler.respond=Mock()
        with patch.object(t.time,'time',return_value=self.now):
            handler.do_GET()
        code, response=handler.respond.call_args.args
        self.assertEqual(code,200)
        self.assertEqual(response['selectedVariant']['headsign'],'Cambio')
        self.assertEqual([s['stop_id'] for s in response['stops']],['a','b'])


if __name__ == '__main__':
    unittest.main()
