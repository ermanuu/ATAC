import unittest
from server.variant_types import inactive_variants


def group(identifier, stops, trips=1):
    return {'id': identifier, 'direction': '0', 'headsign': 'Destinazione',
            'fromName': stops[0], 'toName': stops[-1], 'stopCount': len(stops),
            'stops': [{'stop_id': stop} for stop in stops],
            'trips': {str(i): {} for i in range(trips)}}


class VariantTypesTests(unittest.TestCase):
    def test_inactive_patterns_are_grouped_by_their_actual_path_relationship(self):
        groups = [group('main',['a','b','c','d'],20), group('short',['c','d']),
                  group('long',['x','a','b','c','d']), group('detour',['a','x','c','d']),
                  group('other',['x','y'])]
        variants = inactive_variants('64', groups, {'main'})
        self.assertEqual({v['id']:v['category'] for v in variants},
                         {'short':'Limitata','long':'Prolungata','detour':'Deviata','other':'Altra variante'})
        self.assertTrue(all('trips' not in v and 'stops' not in v for v in variants))

    def test_known_706_school_branch_is_distinguished_from_ordinary_service(self):
        groups = [group('main',['74353','74355','82073'],20), group('school',['82163','74355','82073'])]
        variants = inactive_variants('706', groups, set())
        self.assertEqual({v['id']:v['category'] for v in variants}, {'main':'Ordinaria','school':'Deviata scolastica'})
        self.assertEqual(inactive_variants('107', groups, set())[1]['category'], 'Deviata')
