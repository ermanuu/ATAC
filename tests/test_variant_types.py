import unittest
from unittest.mock import patch
from server.variant_types import inactive_variants, SCHOOL_SERVICES


def group(identifier, stops, trips=1):
    return {'id': identifier, 'direction': '0', 'headsign': 'Destinazione',
            'fromName': stops[0], 'toName': stops[-1], 'stopCount': len(stops),
            'stops': [{'stop_id': stop, 'name': stop.upper()} for stop in stops],
            'trips': {f'{identifier}:{i}': {} for i in range(trips)}}


def sequences(item, times):
    return {trip: [{'departure':int(time[:2])*3600+int(time[3:])*60}]
            for trip,time in zip(item['trips'], times)}


class VariantTypesTests(unittest.TestCase):
    def test_inactive_patterns_are_grouped_by_their_actual_path_relationship(self):
        groups = [group('main',['a','b','c','d'],20), group('short',['c','d']),
                  group('long',['x','a','b','c','d']), group('detour',['a','x','c','d']),
                  group('other',['x','y'])]
        variants = inactive_variants('64', groups, {'main'})
        self.assertEqual({v['id']:v['category'] for v in variants},
                         {'short':'Limitata','long':'Prolungata','detour':'Deviata','other':'Altra variante'})
        self.assertTrue(all('trips' not in v and 'stops' not in v for v in variants))
        self.assertEqual(next(v for v in variants if v['id']=='detour')['pathNote'], 'Via X')

    def test_known_706_school_branch_is_distinguished_from_ordinary_service(self):
        groups = [group('main',['74353','74355','82073'],20), group('school',['82163','74355','82073'],2)]
        times = sequences(groups[1], ['13:10','14:10'])
        variants = inactive_variants('706', groups, set(), times)
        self.assertEqual({v['id']:v['category'] for v in variants}, {'main':'Ordinaria','school':'Deviata scolastica'})
        self.assertEqual(inactive_variants('107', groups, set(), times)[1]['category'], 'Deviata')

    def test_school_profiles_apply_across_lines_and_variant_types(self):
        cases = [('708','07:07','Deviata scolastica'),('078','07:10','Deviata scolastica'),
                 ('73','06:50','Prolungata scolastica'),('107','07:30','Limitata scolastica'),
                 ('201','07:40','Deviata limitata scolastica'),('344','06:45','Deviata prolungata scolastica')]
        for line, time, expected in cases:
            with self.subTest(line=line):
                main = group('main',['a','b','c','d'],20)
                school = group('school',['a','x','c','d'])
                result = inactive_variants(line, [main,school], {'main'}, sequences(school,[time]))
                self.assertEqual(result[0]['category'], expected)

    def test_a_school_time_cannot_relabel_a_full_ordinary_or_unmatched_service(self):
        main = group('main',['a','b','c','d'],20)
        other = group('other',['a','x','c','d'],2)
        for line, times in [('708',['07:07','23:38']),('708',['07:08','13:50']),('999',['07:07','13:50'])]:
            with self.subTest(line=line,times=times):
                result = inactive_variants(line,[main,other],{'main'},sequences(other,times))
                self.assertEqual(result[0]['category'],'Deviata')
                self.assertNotIn('schoolCode',result[0])

    def test_missing_timetable_data_cannot_prove_school_service(self):
        main = group('main',['a','b','c','d'],20)
        other = group('other',['a','x','c','d'])
        self.assertEqual(inactive_variants('708',[main,other],{'main'})[0]['category'],'Deviata')

    def test_a_verified_ordered_school_path_survives_a_timetable_change(self):
        main = group('main',['a','b','c','d'],20)
        school = group('school',['a','x','c','d'])
        rule = {'code':'DS','stops':['a','x','c','d']}
        with patch.dict(SCHOOL_SERVICES,{'TEST-LINE':[rule]}):
            result = inactive_variants('test-line',[main,school],{'main'},sequences(school,['07:18']))
            self.assertEqual(result[0]['category'],'Deviata scolastica')
            rule['stops'] = ['a','c','x','d']
            self.assertEqual(inactive_variants('test-line',[main,school],{'main'})[0]['category'],'Deviata')

    def test_school_origin_names_ignore_punctuation_without_merging_destinations(self):
        school = group('school',['a','x','d'],2)
        school.update(fromName='I.T.A.S. EMILIO SERENI',toName='MONDAVIO')
        result = inactive_variants('508',[school],set(),sequences(school,['13:50','14:40']))
        self.assertEqual(result[0]['schoolCode'],'DLS')
