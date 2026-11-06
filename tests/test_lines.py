"""Direction boards: time bounds, variants, GTFS-RT positioning and cancellation."""
from datetime import datetime
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from google.transit import gtfs_realtime_pb2 as pb
from server import transit as t
from server.app import Handler
from server.lines import daily_departures
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
        realtime = patch.object(t, 'realtime', t.Realtime())
        realtime.start()
        self.addCleanup(realtime.stop)
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

    def test_cached_catalog_is_invalidated_by_an_atomic_dataset_replacement(self):
        from server import lines
        with patch.object(lines, 'load_patterns', wraps=lines.load_patterns) as load:
            first = self.board()
            self.assertEqual(self.board()['stops'], first['stops'])
            self.assertEqual(load.call_count, 1)
            replacement = t.DB.with_name('replacement.sqlite')
            with sqlite3.connect(t.DB) as source, sqlite3.connect(replacement) as target:
                source.backup(target)
                target.execute("UPDATE stops SET name='Nuova origine' WHERE stop_id='a'")
            os.replace(replacement, t.DB)
            self.assertEqual(self.board()['stops'][0]['name'], 'Nuova origine')
            self.assertEqual(load.call_count, 2)

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

    def test_recent_old_position_is_explicitly_last_known(self):
        self.vehicle(self.feed('vehicles'), 'old', sequence=10, timestamp=self.now-91)
        item = self.board()['stops'][0]['vehiclesAt'][0]
        self.assertTrue(item['retained'])
        self.assertEqual(item['timestamp'], self.now-91)

    def test_board_uses_public_label_not_tracking_id(self):
        v=self.vehicle(self.feed('vehicles'), 'technical-123', sequence=10)
        v.vehicle.label='4512'
        item=self.board()['stops'][0]['vehiclesAt'][0]
        self.assertEqual(item['id'], 'technical-123')
        self.assertEqual(item['vehicleId'], '4512')
        v.vehicle.ClearField('label')
        self.assertIsNone(self.board()['stops'][0]['vehiclesAt'][0]['vehicleId'])

    def test_temporary_omission_keeps_last_known_icon(self):
        self.vehicle(self.feed('vehicles'), 'missing', sequence=10)
        self.feeds['vehicles']['retained']=['missing']
        item = self.board()['stops'][0]['vehiclesAt'][0]
        self.assertTrue(item['retained'])
        self.assertEqual(item['id'], 'missing')

    def test_temporary_feed_failure_keeps_bounded_last_known_icon(self):
        self.vehicle(self.feed('vehicles'), 'missing', sequence=10)
        self.feeds['vehicles']['available'] = False
        self.feeds['vehicles']['retained'] = ['missing']
        self.assertTrue(self.board()['stops'][0]['vehiclesAt'][0]['retained'])
        self.now += 181
        self.assertFalse(self.board()['stops'][0]['vehiclesAt'])

    def test_newer_packet_cannot_return_bus_to_passed_stop(self):
        v = self.vehicle(self.feed('vehicles'), 'bus', sequence=20, stop='b')
        self.assertEqual(self.board()['stops'][1]['vehiclesAt'][0]['id'], 'bus')
        original_timestamp = v.timestamp
        self.now += 10
        v.timestamp = self.now
        v.stop_id = 'a'; v.current_stop_sequence = 10
        board = self.board()
        self.assertFalse(board['stops'][0]['vehiclesAt'])
        item = board['stops'][1]['vehiclesAt'][0]
        self.assertTrue(item['retained'])
        self.assertEqual(item['timestamp'], original_timestamp)

    def test_departed_reference_cannot_move_icon_back_before_same_stop(self):
        v = self.vehicle(self.feed('vehicles'), 'bus', sequence=20, stop='b')
        self.board()
        self.now += 10; v.timestamp = self.now
        v.current_status = pb.VehiclePosition.IN_TRANSIT_TO
        board = self.board()
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertTrue(board['stops'][1]['vehiclesAt'][0]['retained'])

    def test_progress_resets_for_a_new_trip_on_same_pattern(self):
        self.add_trip('t-new', 36120)
        v = self.vehicle(self.feed('vehicles'), 'bus', sequence=20, stop='b')
        self.board()
        self.now += 10; v.timestamp = self.now
        v.trip.trip_id = 't-new'; v.stop_id = 'a'; v.current_stop_sequence = 10
        item = self.board()['stops'][0]['vehiclesAt'][0]
        self.assertEqual(item['tripId'], 't-new')
        self.assertFalse(item['retained'])

    def test_progress_resets_for_new_service_date_or_start_time(self):
        v = self.vehicle(self.feed('vehicles'), 'bus', sequence=20, stop='b')
        v.trip.start_date = '20261029'; v.trip.start_time = '10:00:00'
        self.board()
        for field, value in [('start_date', '20261030'), ('start_time', '11:00:00')]:
            self.now += 10; v.timestamp = self.now
            setattr(v.trip, field, value)
            v.stop_id = 'a'; v.current_stop_sequence = 10
            self.assertFalse(self.board()['stops'][0]['vehiclesAt'][0]['retained'])
            v.stop_id = 'b'; v.current_stop_sequence = 20
            self.board()

    def test_explicit_deletion_does_not_restore_previous_marker(self):
        f = self.feed('vehicles')
        self.vehicle(f, 'deleted', sequence=20, stop='b')
        self.board()
        f.entity[0].is_deleted = True
        self.assertTrue(all(not s['vehiclesAt'] and not s['vehiclesBefore'] for s in self.board()['stops']))

    def test_manual_board_refresh_forces_both_sources(self):
        selected=self.variant()
        t.route_detail('r1', selected, self.now, refresh=True)
        self.assertEqual(self.read.call_args_list[-2].kwargs, {'force':True})
        self.assertEqual(self.read.call_args_list[-1].kwargs, {'force':True})

    def test_departure_window_includes_exact_bounds(self):
        for name, at in [('too_early', 35699), ('start',35700), ('recent',35940), ('end',41400), ('too_late',41401)]:
            self.add_trip(name, at)
        result = self.board()
        self.assertEqual([d['tripId'] for d in result['departures']], ['start','recent','t1','end'])
        self.assertEqual(result['window'], {'from': self.now-300, 'to': self.now+5400})
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
        self.add_trip('late', 35699)
        f = self.feed('updates')
        e=f.entity.add(); e.id='late'; e.trip_update.trip.trip_id='late'
        event=e.trip_update.stop_time_update.add(); event.stop_sequence=10; event.departure.delay=120
        self.assertIn('late', [d['tripId'] for d in self.board()['departures']])
        event.departure.time=self.now+5401
        self.assertNotIn('late', [d['tripId'] for d in self.board()['departures']])

    def test_origin_icons_are_ordered_by_departure_instead_of_feed_order(self):
        self.add_trip('later', 37200)
        f = self.feed('vehicles')
        self.vehicle(f, 'later-bus', trip='later', stop='a', sequence=10)
        self.vehicle(f, 'first-bus', trip='t1', stop='a', sequence=10, timestamp=self.now-100)
        buses = self.board()['stops'][0]['vehiclesAt']
        self.assertEqual([v['id'] for v in buses], ['first-bus', 'later-bus'])
        self.assertTrue(buses[0]['retained'])
        self.assertEqual([v['departureTime'] for v in buses], [self.now, self.now+1200])

    def test_origin_icons_follow_live_departure_changes_and_fall_back_to_schedule(self):
        self.add_trip('later', 37200)
        f = self.feed('vehicles')
        self.vehicle(f, 'first-bus', trip='t1', stop='a', sequence=10)
        self.vehicle(f, 'later-bus', trip='later', stop='a', sequence=10)
        u = self.feed('updates').entity.add(); u.id = 'delay'
        u.trip_update.trip.trip_id = 't1'; u.trip_update.timestamp = self.now
        event = u.trip_update.stop_time_update.add(); event.stop_id = 'a'; event.departure.time = self.now+1500
        buses = self.board()['stops'][0]['vehiclesAt']
        self.assertEqual([v['id'] for v in buses], ['later-bus', 'first-bus'])
        self.assertEqual(buses[1]['departureKind'], 'live')
        u.trip_update.timestamp = self.now-181
        buses = self.board()['stops'][0]['vehiclesAt']
        self.assertEqual([v['id'] for v in buses], ['first-bus', 'later-bus'])
        self.assertEqual(buses[0]['departureKind'], 'scheduled')

    def test_late_parked_bus_is_sorted_even_if_its_departure_is_outside_the_strip(self):
        self.add_trip('late-parked', 35400)
        f = self.feed('vehicles')
        self.vehicle(f, 'on-time', trip='t1', stop='a', sequence=10)
        self.vehicle(f, 'overdue', trip='late-parked', stop='a', sequence=10)
        result = self.board()
        self.assertNotIn('late-parked', [d['tripId'] for d in result['departures']])
        buses = result['stops'][0]['vehiclesAt']
        self.assertEqual([v['id'] for v in buses], ['overdue', 'on-time'])
        self.assertEqual(buses[0]['departureTime'], self.now-600)

    def test_daily_departures_include_finished_and_later_trips_in_the_selected_pattern(self):
        self.add_trip('morning', 6*3600)
        self.add_trip('evening', 23*3600)
        self.add_trip('different-pattern', 12*3600, stops=('a', 'c'))
        result = daily_departures('r1', self.variant(), self.now)
        self.assertEqual([d['tripId'] for d in result['departures']], ['morning', 't1', 'evening'])
        self.assertEqual(result['date'], '2026-10-30')

    def test_timetable_includes_calendar_day_and_only_first_three_hours_next_day(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("INSERT INTO exceptions VALUES ('daily','20261029',2)")
        self.add_trip('start', 0)
        self.add_trip('end-of-day', 24*3600-1)
        self.add_trip('midnight', 24*3600)
        self.add_trip('last', 27*3600-1)
        self.add_trip('too-late', 27*3600)
        result = daily_departures('r1', self.variant(), self.now)
        self.assertEqual([d['tripId'] for d in result['departures']], ['start', 't1', 'end-of-day', 'midnight', 'last'])
        self.assertEqual(result['window']['to']-result['window']['from'], 27*3600)
        self.assertEqual(datetime.fromtimestamp(result['window']['from'], t.ROME).hour, 0)
        self.assertEqual(datetime.fromtimestamp(result['window']['to'], t.ROME).hour, 3)

    def test_daily_departures_include_previous_service_day_after_24_hours(self):
        self.now = int(datetime(2026,10,31,0,59,tzinfo=t.ROME).timestamp())
        result = daily_departures('r1', self.variant('Notturno'), self.now)
        self.assertEqual(result['date'], '2026-10-31')
        self.assertEqual([d['tripId'] for d in result['departures']], ['night'])
        self.assertEqual(result['departures'][0]['serviceDate'], '20261030')

    def test_operating_day_uses_rome_wall_clock_across_dst_change(self):
        self.now = int(datetime(2026,10,24,10,0,tzinfo=t.ROME).timestamp())
        result = daily_departures('r1', self.variant(), self.now)
        self.assertEqual(result['window']['to']-result['window']['from'], 28*3600)
        self.assertTrue(all(result['window']['from'] <= d['time'] < result['window']['to'] for d in result['departures']))

    def test_timetable_ignores_live_delay_and_live_cancellation_without_fetching_feeds(self):
        f = self.feed('updates')
        self.add_trip('canceled', 11*3600)
        u = f.entity.add(); u.id = 'updated'; u.trip_update.trip.trip_id = 't1'
        event = u.trip_update.stop_time_update.add(); event.stop_id = 'a'; event.departure.delay = 120
        u = f.entity.add(); u.id = 'canceled'; u.trip_update.trip.trip_id = 'canceled'
        u.trip_update.trip.schedule_relationship = pb.TripDescriptor.CANCELED
        result = daily_departures('r1', self.variant(), self.now, refresh=True)
        self.assertEqual([d['tripId'] for d in result['departures']], ['t1', 'canceled'])
        self.assertEqual(result['departures'][0]['time'], self.now)
        self.assertTrue(all(d['kind'] == 'scheduled' for d in result['departures']))
        self.assertNotIn('timestamp', result)
        self.read.assert_not_called()

    def test_parked_bus_is_identified_even_after_scheduled_departure(self):
        self.add_trip('late-parked', 35940)
        self.vehicle(self.feed('vehicles'), 'parked', trip='late-parked', stop='a', sequence=10)
        item = next(d for d in self.board()['departures'] if d['tripId'] == 'late-parked')
        self.assertTrue(item['atTerminus'])
        self.assertFalse(item['departed'])
        self.assertEqual(item['positionTimestamp'], self.now)
        timetable = daily_departures('r1', self.variant(), self.now)
        self.assertTrue(all('atTerminus' not in d and 'departed' not in d for d in timetable['departures']))

    def test_timetable_includes_after_midnight_times_in_both_gtfs_encodings(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("DELETE FROM exceptions WHERE date='20261031'")
        self.add_trip('zero-hour', 30*60)
        self.add_trip('over24', 24*3600+45*60)
        result = daily_departures('r1', self.variant(), self.now)
        self.assertEqual([d['tripId'] for d in result['departures']], ['zero-hour', 'over24', 't1', 'zero-hour', 'over24'])
        self.assertEqual([d['serviceDate'] for d in result['departures']], ['20261030', '20261029', '20261030', '20261031', '20261030'])

    def test_night_timetable_keeps_calendar_date_and_only_three_extra_hours(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE routes SET name='nMB' WHERE route_id='r1'")
            db.execute("INSERT INTO exceptions VALUES ('daily','20261029',2)")
        for trip, departure in [('morning',90*60),('evening',23*3600),('last',27*3600-1),('too-late',27*3600)]:
            self.add_trip(trip, departure)
        selected = self.variant()
        result = daily_departures('r1', selected, self.now)
        self.assertTrue(result['nightService'])
        self.assertEqual([d['tripId'] for d in result['departures']], ['morning', 't1', 'evening', 'last'])
        self.now = int(datetime(2026,10,31,3,0,tzinfo=t.ROME).timestamp())
        self.assertEqual(daily_departures('r1', selected, self.now)['date'], '2026-10-31')
        self.now = int(datetime(2026,10,31,6,1,tzinfo=t.ROME).timestamp())
        self.assertEqual(daily_departures('r1', selected, self.now)['date'], '2026-10-31')

    def test_inactive_line_keeps_timetable_directions_available(self):
        self.now = int(datetime(2026,10,30,15,0,tzinfo=t.ROME).timestamp())
        result = t.route_detail('r1', now=self.now)
        self.assertEqual(result['variants'], [])
        choices = {v['headsign']:v['id'] for v in result['timetableVariants']}
        self.assertEqual(set(choices), {'Cambio', 'Notturno'})
        timetable = daily_departures('r1', choices['Cambio'], self.now)
        self.assertEqual([d['tripId'] for d in timetable['departures']], ['t1'])
        self.read.assert_not_called()

    def test_explicit_timetable_date_can_find_service_on_another_day(self):
        selected = self.variant()
        off = daily_departures('r1', selected, self.now, date='2026-10-31')
        on = daily_departures('r1', selected, self.now, date='2026-11-01')
        self.assertEqual(off['departures'], [])
        self.assertEqual([d['tripId'] for d in on['departures']], ['t1'])
        self.assertEqual(on['departures'][0]['serviceDate'], '20261101')
        for invalid in ('2026-10-32', '2026-1-2', 'not-a-date'):
            with self.assertRaisesRegex(ValueError, 'Data non valida'):
                daily_departures('r1', selected, self.now, date=invalid)

    def test_timetables_keep_weekday_paths_separate_even_with_the_same_termini(self):
        self.add_trip('weekend-path', 11*3600, stops=('a','c','b'))
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE trips SET service_id='weekend' WHERE trip_id='weekend-path'")
            db.execute("INSERT INTO calendar VALUES ('weekend','20260101','20261231','0000011')")
        selected = self.variant()
        friday = daily_departures('r1', selected, self.now, date='2026-10-30')
        saturday = daily_departures('r1', selected, self.now, date='2026-10-31')
        self.assertEqual([d['tripId'] for d in friday['departures']], ['t1'])
        self.assertEqual(saturday['departures'], [])
        choices = t.route_detail('r1', now=self.now)['timetableVariants']
        choices = [v for v in choices if v['headsign']=='Cambio']
        self.assertEqual(len(choices), 2)
        weekend = next(v for v in choices if v['id'] != selected)
        friday_detour = daily_departures('r1', weekend['id'], self.now, date='2026-10-30')
        saturday_detour = daily_departures('r1', weekend['id'], self.now, date='2026-10-31')
        self.assertEqual(friday_detour['departures'], [])
        self.assertEqual([d['tripId'] for d in saturday_detour['departures']], ['weekend-path'])

    def test_same_day_detour_cannot_inherit_ordinary_departures(self):
        self.add_trip('detour', 12*3600, stops=('a','c','b'))
        picker = t.route_detail('r1', now=self.now)
        variant = next(v for v in picker['inactiveVariants'] if v['stopCount']==3)
        ordinary = daily_departures('r1', self.variant(), self.now)
        detour = daily_departures('r1', variant['id'], self.now)
        self.assertEqual([d['tripId'] for d in ordinary['departures']], ['t1'])
        self.assertEqual([d['tripId'] for d in detour['departures']], ['detour'])
        self.read.assert_not_called()

    def test_school_profiles_use_the_public_line_name_and_keep_their_own_trips(self):
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE routes SET name='708' WHERE route_id='r1'")
        for trip, minute in [('school-1',427),('school-2',436),('school-3',774),('school-4',830)]:
            self.add_trip(trip, minute*60, stops=('a','c','b'))
        self.add_trip('ordinary-late', 22*3600)
        picker = t.route_detail('r1', now=self.now)
        school = next(v for v in picker['inactiveVariants'] if v.get('schoolCode')=='DS')
        self.assertEqual(school['category'], 'Deviata scolastica')
        timetable = daily_departures('r1', school['id'], self.now)
        self.assertEqual([d['tripId'] for d in timetable['departures']], ['school-1','school-2','school-3','school-4'])
        self.assertEqual(timetable['selectedVariant']['schoolCode'], 'DS')
        morning = t.route_detail('r1', now=self.now-3*3600)
        self.assertEqual(next(v for v in morning['variants'] if v['id']==school['id'])['category'],'Deviata scolastica')
        self.read.assert_not_called()

    def test_bus_beyond_origin_is_marked_departed_and_retained_positions_are_ignored(self):
        self.vehicle(self.feed('vehicles'), 'moving', stop='b', sequence=20, status=pb.VehiclePosition.IN_TRANSIT_TO)
        item = self.board()['departures'][0]
        self.assertTrue(item['departed'])
        self.assertFalse(item['atTerminus'])
        self.feeds['vehicles']['retained'] = ['moving']
        self.assertNotIn('departed', self.board()['departures'][0])

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
        self.vehicle(f,'stale',sequence=10,timestamp=self.now-181)
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

    def test_indexed_feeds_preserve_progress_and_vehicles_without_a_route_id(self):
        v, _ = self.rome_forecast()
        v.trip.ClearField('route_id')
        for kind in ('vehicles', 'updates'):
            payload = self.feeds[kind]['feed'].SerializeToString()
            with patch.object(t, 'download', return_value=payload), patch.object(t.time, 'time', return_value=self.now):
                self.feeds[kind] = t.Realtime().read(kind)
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        item = board['stops'][2]['vehiclesBefore'][0]
        self.assertEqual(item['vehicleId'], '2641')
        self.assertEqual(item['positionSource'], 'predictions')
        self.assertFalse(item['retained'])

    def test_missing_forecast_does_not_restore_stale_upstream_reference(self):
        v, _ = self.rome_forecast()
        original = self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]
        self.feeds.pop('updates')
        self.now += 10; v.timestamp = self.now
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        item = board['stops'][2]['vehiclesBefore'][0]
        self.assertTrue(item['retained'])
        self.assertEqual(item['timestamp'], original['timestamp'])
        self.assertEqual(item['predictionTimestamp'], original['predictionTimestamp'])
        # Regressive packets cannot rejuvenate the old location or make the
        # icon reappear upstream after its visible history expires.
        self.now += 181; v.timestamp = self.now
        board = self.board('EUR FERMI (MB)')
        self.assertTrue(all(not s['vehiclesAt'] and not s['vehiclesBefore'] for s in board['stops']))
        v.stop_id = 'c'; v.current_stop_sequence = 30
        self.assertFalse(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]['retained'])

    def test_forecast_for_other_vehicle_does_not_move_icon(self):
        _,u=self.rome_forecast(); u.vehicle.id='other'; u.vehicle.label='2618'
        self.assertEqual(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'][0]['vehicleId'],'2641')

    def test_valid_arrival_forecast_is_not_rejected_due_to_newer_gps_clock(self):
        v,u=self.rome_forecast(); v.timestamp=self.now; u.timestamp=self.now-30
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'])

    def test_future_arrival_prevents_gps_from_putting_bus_after_that_stop(self):
        v, u = self.rome_forecast()
        u.stop_time_update[0].arrival.time = self.now + 30
        u.stop_time_update[1].arrival.time = self.now + 90
        v.position.latitude = 41.915; v.position.longitude = 12.505
        board = self.board('EUR FERMI (MB)')
        self.assertEqual(board['stops'][1]['vehiclesBefore'][0]['vehicleId'], '2641')
        self.assertFalse(board['stops'][2]['vehiclesBefore'])

    def test_earlier_future_eta_cannot_rewind_reported_next_stop(self):
        v, u = self.rome_forecast()
        v.stop_id = 'c'; v.current_stop_sequence = 30
        u.stop_time_update[0].arrival.time = self.now+30
        u.stop_time_update[1].arrival.time = self.now+90
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        item = board['stops'][2]['vehiclesBefore'][0]
        self.assertEqual(item['positionSource'], 'stop_id')
        self.assertEqual(item['referenceStopIndex'], 2)

    def test_moving_bus_is_departed_even_if_origin_prediction_is_still_in_future(self):
        v = self.vehicle(self.feed('vehicles'), 'left-early', stop='b', sequence=20, status=pb.VehiclePosition.IN_TRANSIT_TO)
        f = self.feed('updates'); e = f.entity.add(); e.id = 'late-origin-forecast'
        u = e.trip_update; u.trip.CopyFrom(v.trip); u.vehicle.CopyFrom(v.vehicle); u.timestamp = self.now
        event = u.stop_time_update.add(); event.stop_id = 'a'; event.departure.time = self.now+60
        event = u.stop_time_update.add(); event.stop_id = 'b'; event.arrival.time = self.now+120
        board = self.board()
        self.assertFalse(board['stops'][0]['vehiclesBefore'])
        self.assertTrue(board['stops'][1]['vehiclesBefore'])
        departure = board['departures'][0]
        self.assertEqual(departure['time'], self.now+60)
        self.assertEqual(departure['kind'], 'live')
        self.assertTrue(departure['departed'])
        self.assertFalse(departure['atTerminus'])

    def test_new_eta_cannot_rewind_measured_progress_on_same_journey(self):
        v, u = self.rome_forecast()
        v.stop_id = 'c'; v.current_stop_sequence = 30
        original = self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]
        self.now += 10; v.timestamp = self.now; u.timestamp = self.now
        v.stop_id = 'b'; v.current_stop_sequence = 20
        u.stop_time_update[0].arrival.time = self.now+30
        u.stop_time_update[1].arrival.time = self.now+90
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        item = board['stops'][2]['vehiclesBefore'][0]
        self.assertTrue(item['retained'])
        self.assertEqual(item['timestamp'], original['timestamp'])
        # Repeated contradictory packets cannot revive the bus upstream.
        self.now += 181; v.timestamp = self.now; u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now+30
        u.stop_time_update[1].arrival.time = self.now+90
        board = self.board('EUR FERMI (MB)')
        self.assertTrue(all(not s['vehiclesBefore'] and not s['vehiclesAt'] for s in board['stops']))
        v.stop_id = 'c'; v.current_stop_sequence = 30
        self.feeds.pop('updates')
        self.assertFalse(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]['retained'])

    def test_revised_forecast_cannot_cross_previously_reported_stop(self):
        self.add_trip('four-stops', 36000, headsign='Quattro', stops=('a','b','c','d'))
        v = self.vehicle(self.feed('vehicles'), 'bus', trip='four-stops', stop='c', sequence=30, status=pb.VehiclePosition.IN_TRANSIT_TO)
        f = self.feed('updates'); e = f.entity.add(); e.id = 'forecast'
        u = e.trip_update; u.trip.CopyFrom(v.trip); u.vehicle.CopyFrom(v.vehicle); u.timestamp = self.now
        for stop, delta in [('c',-10),('d',30)]:
            event = u.stop_time_update.add(); event.stop_id = stop; event.arrival.time = self.now+delta
        original = self.board('Quattro')['stops'][3]['vehiclesBefore'][0]
        self.assertEqual(original['positionSource'], 'predictions')
        self.assertEqual(original['referenceStopIndex'], 2)
        self.now += 10; v.timestamp = self.now; u.timestamp = self.now
        v.stop_id = 'b'; v.current_stop_sequence = 20
        u.ClearField('stop_time_update')
        for stop, delta in [('b',30),('c',90),('d',150)]:
            event = u.stop_time_update.add(); event.stop_id = stop; event.arrival.time = self.now+delta
        board = self.board('Quattro')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        item = board['stops'][3]['vehiclesBefore'][0]
        self.assertTrue(item['retained'])
        self.assertEqual(item['predictionTimestamp'], original['predictionTimestamp'])

    def test_omitted_journey_fields_do_not_reset_progress_but_a_new_date_does(self):
        v = self.vehicle(self.feed('vehicles'), 'bus', stop='b', sequence=20)
        v.trip.start_date = '20261030'; v.trip.start_time = '10:00:00'
        original = self.board()['stops'][1]['vehiclesAt'][0]
        self.now += 10; v.timestamp = self.now
        v.trip.ClearField('start_date'); v.trip.ClearField('start_time')
        v.stop_id = 'a'; v.current_stop_sequence = 10
        board = self.board()
        self.assertFalse(board['stops'][0]['vehiclesAt'])
        self.assertEqual(board['stops'][1]['vehiclesAt'][0]['timestamp'], original['timestamp'])
        v.trip.start_date = '20261031'
        self.assertFalse(self.board()['stops'][0]['vehiclesAt'][0]['retained'])

    def test_equal_timestamp_revision_cannot_rewind_an_estimated_marker(self):
        _, u = self.rome_forecast()
        original = self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]
        self.now += 1
        u.stop_time_update[0].arrival.time = self.now+30
        u.stop_time_update[1].arrival.time = self.now+90
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertEqual(board['stops'][2]['vehiclesBefore'][0]['predictionTimestamp'], original['predictionTimestamp'])

    def test_intermediate_estimate_does_not_forget_previously_reported_progress(self):
        v, u = self.rome_forecast()
        v.stop_id = 'c'; v.current_stop_sequence = 30
        self.assertEqual(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]['positionSource'], 'stop_id')
        self.now += 10; v.timestamp = u.timestamp = self.now
        v.stop_id = 'b'; v.current_stop_sequence = 20
        u.stop_time_update[0].arrival.time = self.now-5
        u.stop_time_update[1].arrival.time = self.now+30
        intermediate = self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'][0]
        self.assertEqual(intermediate['positionSource'], 'predictions')
        self.now += 10; v.timestamp = u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now+30
        u.stop_time_update[1].arrival.time = self.now+90
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        item = board['stops'][2]['vehiclesBefore'][0]
        self.assertTrue(item['retained'])
        self.assertEqual(item['predictionTimestamp'], intermediate['predictionTimestamp'])

    def test_newer_delayed_arrival_corrects_a_previous_forecast_that_was_too_far_ahead(self):
        _, u = self.rome_forecast()
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'])
        self.now += 10; u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now + 30
        u.stop_time_update[1].arrival.time = self.now + 90
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][2]['vehiclesBefore'])
        item = board['stops'][1]['vehiclesBefore'][0]
        self.assertEqual(item['vehicleId'], '2641')
        self.assertFalse(item['retained'])
        # A delayed older response must not move it back ahead again.
        u.timestamp = self.now - 10
        u.stop_time_update[0].arrival.time = self.now - 10
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def future_only_forecast(self):
        self.add_trip('2610',36000,headsign='RO TELLINI',stops=('a','b','c','d'))
        with sqlite3.connect(t.DB) as db:
            db.execute("UPDATE stops SET name='OCEANO ATLANTICO/PAVESE' WHERE stop_id='b'")
            db.execute("UPDATE stops SET name='OCEANO ATLANTICO/COLOMBO' WHERE stop_id='c'")
        v=self.vehicle(self.feed('vehicles'),'rt-2610',trip='2610',sequence=20,stop='b',status=pb.VehiclePosition.IN_TRANSIT_TO)
        v.vehicle.label='2610'
        f=self.feed('updates'); e=f.entity.add(); e.id='2610'; u=e.trip_update; u.trip.trip_id='2610'; u.vehicle.id='rt-2610'; u.vehicle.label='2610'; u.trip.start_date='20261030'; u.timestamp=self.now-120
        for sequence,delta in [(30,120),(40,240)]:
            event=u.stop_time_update.add(); event.stop_sequence=sequence; event.arrival.time=self.now+delta
        return v,u

    def test_2610_future_only_forecast_moves_from_pavese_to_colombo(self):
        self.future_only_forecast()
        board=self.board('RO TELLINI')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        item=board['stops'][2]['vehiclesBefore'][0]
        self.assertEqual(item['vehicleId'],'2610')
        self.assertEqual(item['positionSource'],'predictions')
        self.assertEqual(item['predictionTimestamp'],self.now-120)

    def test_omitted_prefix_with_just_passed_first_stop_advances_like_arrivals(self):
        _, u = self.future_only_forecast()
        u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now - 10
        u.stop_time_update[1].arrival.time = self.now + 50
        board = self.board('RO TELLINI')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertFalse(board['stops'][2]['vehiclesBefore'])
        self.assertEqual(board['stops'][3]['vehiclesBefore'][0]['vehicleId'], '2610')
        with patch.object(t.time, 'time', return_value=self.now):
            self.assertFalse([a for a in t.arrivals('c')['arrivals'] if a['tripId'] == '2610'])
            arrival = next(a for a in t.arrivals('d')['arrivals'] if a['tripId'] == '2610')
        self.assertEqual(arrival['kind'], 'live')
        self.assertEqual(arrival['time'], self.now + 50)

    def test_icon_leaves_passed_stop_even_without_next_eta(self):
        _, u = self.rome_forecast()
        del u.stop_time_update[1]
        board = self.board('EUR FERMI (MB)')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertEqual(board['stops'][2]['vehiclesBefore'][0]['vehicleId'], '2641')

    def test_passage_advances_only_one_step_before_a_missing_stop_update(self):
        v, u = self.future_only_forecast()
        v.stop_id = 'a'; v.current_stop_sequence = 10
        u.stop_time_update.clear()
        for sequence, delta in [(10, -10), (40, 60)]:
            event = u.stop_time_update.add(); event.stop_sequence = sequence
            event.arrival.time = self.now + delta
        board = self.board('RO TELLINI')
        self.assertEqual(board['stops'][1]['vehiclesBefore'][0]['vehicleId'], '2610')
        self.assertFalse(board['stops'][3]['vehiclesBefore'])

    def test_first_omitted_prefix_stop_with_future_departure_does_not_get_skipped(self):
        _, u = self.future_only_forecast()
        u.stop_time_update[0].arrival.time = self.now - 10
        u.stop_time_update[0].departure.time = self.now + 20
        board = self.board('RO TELLINI')
        self.assertTrue(board['stops'][2]['vehiclesBefore'])
        self.assertFalse(board['stops'][3]['vehiclesBefore'])

    def test_last_passed_stop_advances_to_terminal_without_a_terminal_eta(self):
        _, u = self.future_only_forecast()
        u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now - 10
        u.stop_time_update[1].schedule_relationship = pb.TripUpdate.StopTimeUpdate.NO_DATA
        board = self.board('RO TELLINI')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertFalse(board['stops'][2]['vehiclesBefore'])
        self.assertEqual(board['stops'][3]['vehiclesBefore'][0]['vehicleId'], '2610')

    def test_a_direct_passage_overrides_an_inconsistent_propagated_eta_upstream(self):
        v, u = self.future_only_forecast()
        u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now - 10
        u.stop_time_update[1].schedule_relationship = pb.TripUpdate.StopTimeUpdate.NO_DATA
        # An old origin event would propagate a future timetable-based ETA at
        # b, although the direct event at the later c is already in the past.
        event = u.stop_time_update.add(); event.stop_sequence = 10
        event.departure.time = self.now - 30
        board = self.board('RO TELLINI')
        self.assertFalse(board['stops'][1]['vehiclesBefore'])
        self.assertEqual(board['stops'][3]['vehiclesBefore'][0]['id'], v.vehicle.id)

    def test_one_recent_arrival_with_a_future_departure_does_not_leave_that_stop(self):
        _, u = self.future_only_forecast()
        u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now - 10
        u.stop_time_update[0].departure.time = self.now + 20
        u.stop_time_update[1].schedule_relationship = pb.TripUpdate.StopTimeUpdate.NO_DATA
        board = self.board('RO TELLINI')
        self.assertTrue(board['stops'][2]['vehiclesBefore'])
        self.assertFalse(board['stops'][3]['vehiclesBefore'])

    def test_an_omitted_bus_is_not_moved_using_only_elapsed_forecasts(self):
        _, u = self.future_only_forecast()
        u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now - 10
        u.stop_time_update[1].schedule_relationship = pb.TripUpdate.StopTimeUpdate.NO_DATA
        self.feeds['vehicles']['retained'] = ['rt-2610']
        board = self.board('RO TELLINI')
        self.assertTrue(board['stops'][1]['vehiclesBefore'][0]['retained'])
        self.assertFalse(board['stops'][3]['vehiclesBefore'])

    def test_newer_trip_assignment_does_not_leave_a_ghost_on_the_previous_direction(self):
        v, _ = self.rome_forecast()
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'])
        f = self.feed('updates'); e = f.entity.add(); e.id = 'new-assignment'
        u = e.trip_update; u.vehicle.CopyFrom(v.vehicle); u.trip.CopyFrom(v.trip)
        u.trip.trip_id = 'return-trip'; u.trip.direction_id = 1
        u.timestamp = self.now
        board = self.board('EUR FERMI (MB)')
        self.assertTrue(all(not s['vehiclesAt'] and not s['vehiclesBefore'] for s in board['stops']))

    def test_future_trip_assignment_does_not_hide_a_concurrent_current_trip_update(self):
        v, _ = self.rome_forecast()
        e = self.feeds['updates']['feed'].entity.add(); e.id = 'future-assignment'
        u = e.trip_update; u.vehicle.CopyFrom(v.vehicle); u.trip.CopyFrom(v.trip)
        u.trip.trip_id = 'return-trip'; u.timestamp = self.now
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'])

    def test_an_older_or_other_bus_assignment_cannot_remove_a_fresh_position(self):
        v, _ = self.rome_forecast()
        f = self.feed('updates'); e = f.entity.add(); e.id = 'old-assignment'
        u = e.trip_update; u.vehicle.CopyFrom(v.vehicle); u.trip.CopyFrom(v.trip)
        u.trip.trip_id = 'return-trip'; u.timestamp = v.timestamp - 1
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])
        u.timestamp = self.now; u.vehicle.id = 'other-bus'; u.vehicle.label = '2618'
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])

    def test_assignment_uses_position_feed_time_when_vehicle_timestamp_is_absent(self):
        v, _ = self.rome_forecast()
        v.ClearField('timestamp')
        f = self.feed('updates'); e = f.entity.add(); e.id = 'assignment'
        u = e.trip_update; u.vehicle.CopyFrom(v.vehicle); u.trip.CopyFrom(v.trip)
        u.trip.trip_id = 'return-trip'; u.timestamp = self.now - 1
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])
        # Conflicting assignments with the same timestamp are ambiguous too.
        u.timestamp = self.now
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])
        u.timestamp = self.now + 1; self.now += 1
        board = self.board('EUR FERMI (MB)')
        self.assertTrue(all(not s['vehiclesAt'] and not s['vehiclesBefore'] for s in board['stops']))

    def test_old_or_unordered_prefix_anchor_cannot_skip_to_future_stop(self):
        _, u = self.future_only_forecast()
        u.stop_time_update[0].arrival.time = self.now - 181
        self.assertTrue(self.board('RO TELLINI')['stops'][1]['vehiclesBefore'])
        u.stop_time_update[0].arrival.time = self.now + 120
        u.stop_time_update[1].arrival.time = self.now + 60
        self.assertTrue(self.board('RO TELLINI')['stops'][1]['vehiclesBefore'])

    def test_updated_eta_can_hold_bus_before_passage(self):
        _, u = self.rome_forecast()
        u.stop_time_update[0].arrival.time = self.now + 10
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])
        self.now += 15
        u.timestamp = self.now
        u.stop_time_update[0].arrival.time = self.now + 20
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][1]['vehiclesBefore'])
        self.now += 21
        self.assertTrue(self.board('EUR FERMI (MB)')['stops'][2]['vehiclesBefore'])

    def test_cached_live_events_advance_again_when_the_next_arrival_passes(self):
        v, u = self.future_only_forecast()
        v.stop_id = 'a'; v.current_stop_sequence = 10
        u.timestamp = self.now
        u.stop_time_update.clear()
        for sequence, delta in [(20, -10), (30, 10), (40, 50)]:
            event = u.stop_time_update.add(); event.stop_sequence = sequence
            event.arrival.time = self.now + delta
        self.assertTrue(self.board('RO TELLINI')['stops'][2]['vehiclesBefore'])
        with patch.object(t.time, 'time', return_value=self.now):
            self.assertTrue([a for a in t.arrivals('c')['arrivals'] if a['tripId'] == '2610'])
        # The source packet and GPS are unchanged: the stop's live ETA alone
        # crosses now, exactly as it does in the per-stop arrival list.
        self.now += 11
        board = self.board('RO TELLINI')
        self.assertFalse(board['stops'][2]['vehiclesBefore'])
        self.assertTrue(board['stops'][3]['vehiclesBefore'])
        with patch.object(t.time, 'time', return_value=self.now):
            self.assertFalse([a for a in t.arrivals('c')['arrivals'] if a['tripId'] == '2610'])

    def test_expired_future_only_forecast_cannot_move_bus(self):
        _,u=self.future_only_forecast(); u.timestamp=self.now-181
        self.assertTrue(self.board('RO TELLINI')['stops'][1]['vehiclesBefore'])

    def test_single_downstream_forecast_cannot_skip_unreported_stops(self):
        _,u=self.future_only_forecast(); del u.stop_time_update[1]
        self.assertTrue(self.board('RO TELLINI')['stops'][1]['vehiclesBefore'])

    def test_future_only_no_data_is_not_an_arrival_anchor(self):
        _,u=self.future_only_forecast(); u.stop_time_update[1].schedule_relationship=pb.TripUpdate.StopTimeUpdate.NO_DATA
        self.assertTrue(self.board('RO TELLINI')['stops'][1]['vehiclesBefore'])

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

    def test_last_known_icon_expires_after_three_minutes(self):
        feed=self.feed('vehicles')
        self.vehicle(feed,'expired',sequence=10,timestamp=self.now-181)
        self.vehicle(feed,'boundary',sequence=10,timestamp=self.now-180)
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
