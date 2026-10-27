import copy
import unittest

from ontology_poc_generator.ontology_questions import run_query

ONTOLOGY = {
    'object_types': [
        {'key': 'contract', 'label': '合同授标', 'populated_from': [{'source': 'contracts', 'identity': {'award_key': 'award_key'}}],
         'attributes': [{'source': 'contracts', 'path': 'piid'}, {'source': 'contracts', 'path': 'agency'}, {'source': 'contracts', 'path': 'total'}]},
        {'key': 'vehicle', 'label': '母合同', 'populated_from': [{'source': 'vehicles', 'identity': {'vehicle_key': 'vehicle_key'}}], 'attributes': []},
        {'key': 'vendor', 'label': '承包商', 'populated_from': [{'source': 'vendors', 'identity': {'uei': 'uei'}}],
         'attributes': [{'source': 'vendors', 'path': 'name'}]},
    ],
    'relations': [
        {'key': 'contract_vehicle', 'from': 'contract', 'to': 'vehicle', 'label': '属于', 'source': 'contracts',
         'from_identity': {'award_key': 'award_key'}, 'to_identity': {'vehicle_key': 'vehicle_key'}},
        {'key': 'contract_vendor', 'from': 'contract', 'to': 'vendor', 'label': '授予', 'source': 'contracts',
         'from_identity': {'award_key': 'award_key'}, 'to_identity': {'uei': 'uei'}},
    ],
}
BUNDLE = {'sources': {
    'contracts': {'records': [
        {'award_key': '1425|F1|4732|GS03F102CA', 'piid': 'F1', 'agency': '4732', 'total': '100', 'vehicle_key': '4732|GS03F102CA', 'uei': 'V1'},
        {'award_key': '1425|F2|4732|GS03F102CA', 'piid': 'F2', 'agency': '4732', 'total': '50', 'vehicle_key': '4732|GS03F102CA', 'uei': 'V1'},
        {'award_key': '1425|F3|4732|OTHER', 'piid': 'F3', 'agency': '4732', 'total': '5', 'vehicle_key': '4732|OTHER', 'uei': 'V2'}]},
    'vehicles': {'records': [{'vehicle_key': '4732|GS03F102CA'}, {'vehicle_key': '4732|OTHER'}]},
    'vendors': {'records': [{'uei': 'V1', 'name': 'Acme'}, {'uei': 'V2', 'name': 'Bolt'}]}}}


def total_of(piid, **over):
    return {'start': 'contract', 'where': [{'field': 'piid', 'equals': piid}], 'via': [], 'group_by': None,
            'measure': {'field': 'total', 'op': 'sum'}, **over}


class FoundElsewhereTests(unittest.TestCase):
    def test_a_value_no_start_object_has_is_looked_up_in_the_numbers_of_the_other_objects(self):
        result = run_query(ONTOLOGY, BUNDLE, total_of('GS03F102CA'))
        self.assertEqual(result['status'], 'no_data')
        self.assertEqual(result['evidence']['found_elsewhere'],
                         [{'type': 'vehicle', 'field': 'piid', 'equals': 'GS03F102CA', 'count': 1, 'linked': 2}])
        self.assertEqual(result['evidence']['filters'][0]['after'], 0)   # the rest of the pack is as it was

    def test_the_value_matches_a_part_of_a_number_after_spaces_and_case_are_set_aside(self):
        result = run_query(ONTOLOGY, BUNDLE, total_of(' gs03f102ca'))
        self.assertEqual(result['evidence']['found_elsewhere'],
                         [{'type': 'vehicle', 'field': 'piid', 'equals': ' gs03f102ca', 'count': 1, 'linked': 2}])

    def test_a_value_found_nowhere_adds_nothing(self):
        result = run_query(ONTOLOGY, BUNDLE, total_of('NOPE'))
        self.assertEqual(result['status'], 'no_data')
        self.assertNotIn('found_elsewhere', result['evidence'])

    def test_only_a_value_the_start_objects_lack_is_looked_for(self):
        # agency 4732 is on every contract and piid F9 on none: the number 4732 turns up in the vehicles but is no news
        query = {'start': 'contract', 'where': [{'field': 'agency', 'equals': '4732'}, {'field': 'piid', 'equals': 'F9'}], 'via': []}
        result = run_query(ONTOLOGY, BUNDLE, query)
        self.assertEqual(result['status'], 'no_data')
        self.assertNotIn('found_elsewhere', result['evidence'])

    def test_conditions_that_each_hold_but_not_together_add_nothing(self):
        query = {'start': 'contract', 'where': [{'field': 'piid', 'equals': 'F1'}, {'field': 'total', 'equals': '5'}], 'via': []}
        result = run_query(ONTOLOGY, BUNDLE, query)
        self.assertEqual(result['status'], 'no_data')
        self.assertNotIn('found_elsewhere', result['evidence'])

    def test_an_answered_query_has_no_such_key(self):
        result = run_query(ONTOLOGY, BUNDLE, total_of('F1'))
        self.assertEqual(result['status'], 'answered')
        self.assertNotIn('found_elsewhere', result.get('evidence', {}))

    def test_every_missing_value_is_looked_up_and_each_type_that_has_it_is_listed(self):
        query = {'start': 'contract', 'where': [{'field': 'piid', 'equals': 'GS03F102CA'}, {'field': 'agency', 'equals': 'Acme'}], 'via': []}
        bundle = {'sources': {**BUNDLE['sources'], 'vendors': {'records': [{'uei': 'V1', 'name': 'Acme'}, {'uei': 'Acme', 'name': 'Bolt'}]}}}
        result = run_query(ONTOLOGY, bundle, query)
        self.assertEqual(result['evidence']['found_elsewhere'], [
            {'type': 'vehicle', 'field': 'piid', 'equals': 'GS03F102CA', 'count': 1, 'linked': 2},
            {'type': 'vendor', 'field': 'agency', 'equals': 'Acme', 'count': 1, 'linked': 0}])


    def test_a_value_many_objects_share_in_their_numbers_points_to_the_one_it_names(self):
        # each action's number carries its vehicle's piid: the value names the vehicle, the actions only refer to it
        ontology = copy.deepcopy(ONTOLOGY)
        ontology['object_types'].append({'key': 'action', 'label': '合同动作', 'populated_from': [
            {'source': 'actions', 'identity': {'action_key': 'action_key'}}], 'attributes': []})
        bundle = {'sources': {**BUNDLE['sources'], 'actions': {'records': [
            {'action_key': 'A1|GS03F102CA'}, {'action_key': 'A2|GS03F102CA'}, {'action_key': 'A3|GS03F102CA'}]}}}
        result = run_query(ontology, bundle, total_of('GS03F102CA'))
        self.assertEqual(result['evidence']['found_elsewhere'],
                         [{'type': 'vehicle', 'field': 'piid', 'equals': 'GS03F102CA', 'count': 1, 'linked': 2}])


if __name__ == '__main__':
    unittest.main()
