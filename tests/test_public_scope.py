import copy
import importlib
import json
from pathlib import Path
import unittest

from ontology_poc_generator.public_ontology import auto_build_ontology
from ontology_poc_generator.recognition import ModelCompletion

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class OneReply:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.reply))


def ev(model, year):
    return {'make': 'CHEVROLET', 'model': model, 'model_year': year}


class PublicScopeTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('ontology_poc_generator.public_scope'),
                             'public scope query is not implemented')
        return importlib.import_module('ontology_poc_generator.public_scope')

    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.ontology = auto_build_ontology(self.bundle, OneReply(load('reference_proposal.json')))
        self.assertEqual(self.ontology['status'], 'auto_built_verified')

    def run_scope(self, campaign):
        return self.api().scope(self.ontology, self.bundle, {'campaign_number': campaign})

    def by_signal(self, result):
        return {c['signal']['odi_number']: c for c in result['candidates']}

    def test_battery_recall_covers_its_model_years(self):
        r = self.run_scope('21V650000')
        self.assertEqual(r['schema'], 'public_scope_result.v1')
        self.assertEqual(r['covered'], [ev('BOLT EUV', '2022'), ev('BOLT EV', '2020'), ev('BOLT EV', '2021'),
                                        ev('BOLT EV', '2022')])
        self.assertEqual(r['mechanism'], [{'component_name': 'ELECTRICAL SYSTEM:PROPULSION SYSTEM:TRACTION BATTERY'}])
        self.assertIn('待质量工程师复核', r['boundary'])

    def test_battery_candidates_fall_into_three_buckets(self):
        c = self.by_signal(self.run_scope('21V650000'))
        self.assertEqual(c['11429891']['bucket'], 'inside_scope')
        self.assertEqual(c['11600123']['bucket'], 'outside_all')
        self.assertEqual(c['11600123']['part_match'], 'same_category')
        self.assertEqual(c['11600123']['objects'], [ev('BOLT EV', '2023')])
        self.assertEqual(c['11429913']['bucket'], 'covered_by_other_event')
        self.assertEqual(c['11429913']['other_events'], [{'campaign_number': '20V701000'}])
        self.assertNotIn('11749605', c)
        self.assertNotIn('11492459', c)

    def test_candidate_points_back_to_its_source_record(self):
        c = self.by_signal(self.run_scope('21V650000'))['11600123']
        (ref,) = c['source_refs']
        self.assertEqual(self.bundle['sources'][ref['source']]['records'][ref['index']]['odiNumber'], 11600123)
        self.assertIsNone(c['text_check'])

    def test_airbag_recall_uses_same_code(self):
        c = self.by_signal(self.run_scope('21V517000'))
        self.assertEqual(list(c), ['11492459'])
        self.assertEqual(c['11492459']['bucket'], 'outside_all')

    def test_refuses_blocked_ontology_other_bundle_or_unknown_event(self):
        api = self.api()
        blocked = dict(self.ontology, status='blocked')
        with self.assertRaises(api.ScopeError):
            api.scope(blocked, self.bundle, {'campaign_number': '21V650000'})
        other = copy.deepcopy(self.bundle)
        other['sources']['complaints']['records'].pop()
        with self.assertRaises(api.ScopeError):
            api.scope(self.ontology, other, {'campaign_number': '21V650000'})
        with self.assertRaises(api.ScopeError):
            self.run_scope('99V999000')

    def test_result_is_deterministic_and_bound_to_ontology(self):
        a, b = self.run_scope('21V650000'), self.run_scope('21V650000')
        self.assertEqual(a, b)
        self.assertRegex(a['ontology_hash'], r'^[0-9a-f]{64}$')
        self.assertEqual([c['signal']['odi_number'] for c in a['candidates']], ['11429891', '11429913', '11600123'])


if __name__ == '__main__':
    unittest.main()
