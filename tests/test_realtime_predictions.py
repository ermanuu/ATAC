"""GTFS-RT propagation through omitted stops, not timetable-only arrivals."""
import unittest
from google.transit import gtfs_realtime_pb2 as pb
from server.realtime_utils import stop_predictions


class RealtimePredictionTests(unittest.TestCase):
    def setUp(self):
        self.stops = [dict(stop_id=str(i), sequence=i, arrival=200+i*30, departure=200+i*30) for i in range(4)]
        self.update = pb.TripUpdate()
        self.update.trip.trip_id = 'live-trip'

    def event(self, index):
        event = self.update.stop_time_update.add()
        event.stop_id = str(index); event.stop_sequence = index
        return event

    def test_omitted_stop_inherits_live_departure_delay_and_absolute_time_wins(self):
        first = self.event(0)
        first.departure.time = 1300; first.departure.delay = 999
        self.event(2).arrival.time = 1390
        predictions = stop_predictions(self.update, self.stops, 1000)
        self.assertEqual(predictions[1]['arrival'], 1330)
        self.assertEqual(predictions[1]['source'], 'propagated')
        self.assertEqual(predictions[2]['arrival'], 1390)
        self.assertEqual(predictions[2]['source'], 'direct')

    def test_no_data_stops_propagation_until_next_explicit_live_event(self):
        self.event(0).departure.time = 1300
        self.event(1).schedule_relationship = pb.TripUpdate.StopTimeUpdate.NO_DATA
        self.event(3).arrival.time = 1500
        predictions = stop_predictions(self.update, self.stops, 1000)
        self.assertTrue(predictions[1]['noData'])
        self.assertNotIn(2, predictions)
        self.assertEqual(predictions[3]['arrival'], 1500)

    def test_skipped_stop_does_not_erase_the_live_delay_of_following_stops(self):
        self.event(0).departure.time = 1300
        self.event(1).schedule_relationship = pb.TripUpdate.StopTimeUpdate.SKIPPED
        predictions = stop_predictions(self.update, self.stops, 1000)
        self.assertTrue(predictions[1]['skipped'])
        self.assertEqual(predictions[2]['arrival'], 1360)

    def test_later_eta_is_not_propagated_backwards_to_an_unknown_earlier_stop(self):
        self.event(2).arrival.time = 1390
        predictions = stop_predictions(self.update, self.stops, 1000)
        self.assertNotIn(0, predictions)
        self.assertNotIn(1, predictions)
