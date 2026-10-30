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
        self.assertEqual([(a['time']-self.now,a['kind']) for a in result],[(300,'scheduled'),(1500,'live')])


if __name__=='__main__':
    unittest.main()
