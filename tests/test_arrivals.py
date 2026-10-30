"""All-line stop arrivals, including terminal-only stops and repeated stop IDs."""
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from google.transit import gtfs_realtime_pb2 as pb
from server import transit as t
from test_transit import fixture


class StopArrivalsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now=int(datetime(2026,10,30,10,0,tzinfo=t.ROME).timestamp())
        self.live={'available':False,'timestamp':None}
        for context in (patch.object(t,'DATA',Path(self.temp.name)), patch.object(t,'DB',Path(self.temp.name)/'transit.sqlite'), patch.object(t.time,'time',return_value=self.now), patch.object(t.realtime,'read',side_effect=lambda kind:self.live)):
            context.start(); self.addCleanup(context.stop)
        t.import_gtfs(fixture())

    def feed(self):
        f=pb.FeedMessage(); f.header.gtfs_realtime_version='2.0'; f.header.timestamp=self.now
        self.live={'available':True,'timestamp':self.now,'feed':f}
        return f

    def test_live_arrival_marks_only_fresh_vehicle_stopped_at_origin(self):
        feed = self.feed()
        update = feed.entity.add(); update.id = 'update'
        update.trip_update.trip.trip_id = 't1'
        update.trip_update.vehicle.label = '1234'
        event = update.trip_update.stop_time_update.add()
        event.stop_id = 'b'; event.arrival.time = self.now + 600
        entity = feed.entity.add(); entity.id = 'bus'
        vehicle = entity.vehicle
        vehicle.trip.trip_id = 't1'; vehicle.vehicle.label = '1234'
        vehicle.timestamp = self.now; vehicle.stop_id = 'a'
        vehicle.current_status = pb.VehiclePosition.STOPPED_AT
        def item():
            return next(a for a in t.arrivals('b')['arrivals'] if a['tripId'] == 't1')
        self.assertTrue(item()['atTerminus'])
        vehicle.stop_id = 'b'
        self.assertFalse(item()['atTerminus'])
        vehicle.stop_id = 'a'; vehicle.current_status = pb.VehiclePosition.IN_TRANSIT_TO
        self.assertFalse(item()['atTerminus'])
        vehicle.current_status = pb.VehiclePosition.STOPPED_AT; vehicle.timestamp = self.now - 91
        self.assertFalse(item()['atTerminus'])

    def test_stop_returns_all_lines_not_just_selected_line(self):
        arrivals=t.arrivals('b')['arrivals']
        self.assertEqual({a['line'] for a in arrivals},{'64','40'})
        self.assertEqual([a['time'] for a in arrivals],sorted(a['time'] for a in arrivals))

    def test_more_than_twenty_arrivals_are_returned(self):
        with sqlite3.connect(t.DB) as db:
            for i in range(45):
                trip=f'frequent-{i}'
                db.execute('INSERT INTO trips VALUES (?,?,?,?,?)',(trip,'r1' if i%2 else 'r2','daily',trip,'0'))
                at=36060+i*30
                db.execute('INSERT INTO times VALUES (?,?,?,?,?,?,?)',(trip,'b',1,at,at,0,0))
        self.assertEqual(len(t.arrivals('b')['arrivals']),47)

    def test_exact_stop_id_does_not_include_nearby_stop_with_same_name(self):
        with sqlite3.connect(t.DB) as db:
            db.execute('INSERT INTO stops VALUES (?,?,?,?)',('nearby','Cambio',41.91001,12.50001))
            db.execute('INSERT INTO trips VALUES (?,?,?,?,?)',('nearby-trip','r1','daily','Other platform','1'))
            db.execute('INSERT INTO times VALUES (?,?,?,?,?,?,?)',('nearby-trip','nearby',1,36060,36060,0,0))
        self.assertNotIn('nearby-trip',{a['tripId'] for a in t.arrivals('b')['arrivals']})

    def test_alighting_only_terminal_is_included_but_pass_through_is_not(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE times SET pickup=1,dropoff=0 WHERE trip_id='t1' AND stop_id='b'")
        self.assertIn('t1',{a['tripId'] for a in t.arrivals('b')['arrivals']})
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE times SET dropoff=1 WHERE trip_id='t1' AND stop_id='b'")
        self.assertNotIn('t1',{a['tripId'] for a in t.arrivals('b')['arrivals']})

    def test_arrival_time_is_used_instead_of_departure_time(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE times SET departure=36900 WHERE trip_id='t1' AND stop_id='b'")
        item=next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')
        self.assertEqual(item['time'],self.now+600)
        self.assertEqual(item['scheduledTime'],self.now+600)
        f=self.feed(); e=f.entity.add(); e.id='t1'; e.trip_update.trip.trip_id='t1'
        event=e.trip_update.stop_time_update.add(); event.stop_id='b'; event.arrival.delay=120; event.departure.delay=600
        item=next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')
        self.assertEqual(item['time'],self.now+720)
        self.assertEqual(item['kind'],'live')

    def test_canceled_trip_and_skipped_stop_are_excluded(self):
        f=self.feed()
        e=f.entity.add(); e.id='canceled'; e.trip_update.trip.trip_id='t2'; e.trip_update.trip.schedule_relationship=pb.TripDescriptor.CANCELED
        e=f.entity.add(); e.id='skipped'; e.trip_update.trip.trip_id='t1'
        event=e.trip_update.stop_time_update.add(); event.stop_id='b'; event.schedule_relationship=pb.TripUpdate.StopTimeUpdate.SKIPPED
        self.assertEqual(t.arrivals('b')['arrivals'],[])

    def test_loop_updates_only_matching_stop_sequence(self):
        with sqlite3.connect(t.DB) as db:
            db.execute('INSERT INTO trips VALUES (?,?,?,?,?)',('loop','r1','daily','Loop','0'))
            db.executemany('INSERT INTO times VALUES (?,?,?,?,?,?,?)', [('loop','b',10,36300,36300,0,0),('loop','b',20,37200,37200,0,0)])
        f=self.feed(); e=f.entity.add(); e.id='loop'; e.trip_update.trip.trip_id='loop'
        event=e.trip_update.stop_time_update.add(); event.stop_id='b'; event.stop_sequence=20; event.arrival.time=self.now+1500
        result=[a for a in t.arrivals('b')['arrivals'] if a['tripId']=='loop']
        self.assertEqual([(a['time']-self.now,a['kind']) for a in result],[(1500,'live'),(300,'scheduled')])

    def test_arrival_links_to_matching_route_and_direction(self):
        items=t.arrivals('b')['arrivals']
        for item in items:
            board=t.route_detail(item['routeId'],item['variantId'],self.now)
            self.assertEqual(board['selectedVariant']['headsign'],item['headsign'])
            self.assertTrue(any(s['stop_id']=='b' for s in board['stops']))

    def test_live_vehicle_number_comes_from_trip_update(self):
        f=self.feed(); e=f.entity.add(); e.id='vehicle-update'
        u=e.trip_update; u.trip.trip_id='t1'; u.vehicle.id='internal-id'; u.vehicle.label='1234'
        stop=u.stop_time_update.add(); stop.stop_sequence=20; stop.arrival.delay=60
        item=next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')
        self.assertEqual(item['vehicleId'],'1234')
        self.assertEqual(item['kind'],'live')

    def test_vehicle_number_falls_back_to_fresh_positions(self):
        updates=self.feed(); e=updates.entity.add(); e.id='prediction'; e.trip_update.trip.trip_id='t1'
        stop=e.trip_update.stop_time_update.add(); stop.stop_sequence=20; stop.arrival.delay=60
        positions=pb.FeedMessage(); positions.header.gtfs_realtime_version='2.0'; positions.header.timestamp=self.now
        e=positions.entity.add(); e.id='position'; v=e.vehicle; v.trip.trip_id='t1'; v.trip.route_id='r1'; v.vehicle.id='internal-5678'; v.vehicle.label='5678'; v.timestamp=self.now
        with patch.object(t.realtime,'read',side_effect=lambda kind:{'available':True,'timestamp':self.now,'feed':updates if kind=='updates' else positions}):
            item=next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')
            self.assertEqual(item['vehicleId'],'5678')
            v.timestamp=self.now+10
            with patch.object(t.time,'time',side_effect=[self.now,self.now+15]):
                self.assertEqual(next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')['vehicleId'],'5678')
            v.timestamp=self.now-91
            self.assertIsNone(next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')['vehicleId'])

    def test_live_arrival_precedes_earlier_programmed_arrival(self):
        f=self.feed(); e=f.entity.add(); e.id='live'; u=e.trip_update; u.trip.trip_id='t2'; u.timestamp=self.now
        event=u.stop_time_update.add(); event.stop_sequence=1; event.arrival.delay=600
        result=t.arrivals('b')['arrivals']
        self.assertEqual([a['kind'] for a in result],['live','scheduled'])
        self.assertGreater(result[0]['time'],result[1]['time'])

    def test_delayed_live_replaces_schedule_for_same_trip_instance(self):
        f=self.feed(); e=f.entity.add(); e.id='live'; u=e.trip_update; u.trip.trip_id='t1'; u.timestamp=self.now
        event=u.stop_time_update.add(); event.stop_sequence=20; event.arrival.delay=300
        rows=[a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['kind'],'live')
        self.assertEqual(rows[0]['time']-rows[0]['scheduledTime'],300)

    def test_stop_id_agrees_with_board_when_counter_conflicts(self):
        f=self.feed(); e=f.entity.add(); e.id='live'; u=e.trip_update; u.trip.trip_id='t1'; u.timestamp=self.now
        event=u.stop_time_update.add(); event.stop_sequence=10; event.stop_id='b'; event.arrival.delay=60
        item=next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')
        self.assertEqual(item['kind'],'live')
        self.assertEqual(item['time'],self.now+660)

    def test_older_duplicate_update_does_not_overwrite_newer(self):
        f=self.feed()
        for name,age,delay in [('new',0,300),('old',30,60)]:
            e=f.entity.add(); e.id=name; u=e.trip_update; u.trip.trip_id='t1'; u.timestamp=self.now-age
            event=u.stop_time_update.add(); event.stop_sequence=20; event.arrival.delay=delay
        self.assertEqual(next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')['time'],self.now+900)

    def test_internal_identifiers_are_not_public_fleet_numbers(self):
        f=self.feed(); e=f.entity.add(); e.id='entity-123'
        u=e.trip_update; u.trip.trip_id='t1'; u.vehicle.id='technical-456'
        event=u.stop_time_update.add(); event.stop_sequence=20; event.arrival.delay=60
        self.assertIsNone(next(a for a in t.arrivals('b')['arrivals'] if a['tripId']=='t1')['vehicleId'])

    def test_missing_vehicle_number_is_not_invented(self):
        self.assertTrue(all(a['vehicleId'] is None for a in t.arrivals('b')['arrivals']))


if __name__=='__main__':
    unittest.main()
