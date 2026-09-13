import copy
import json
from pathlib import Path
import unittest

from ontology_poc_generator.nhtsa_sources import load_source_bundle, referenced_campaigns
from ontology_poc_generator.public_ontology import auto_build_ontology, propose_value_aliases
from ontology_poc_generator.public_review_pack import build_review_pack
from ontology_poc_generator.public_scope import check_candidates, scope
from ontology_poc_generator.recognition import ModelCompletion

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/nhtsa'


class Reply:
    def __init__(self, content):
        self.content = content

    def complete_json(self, *, system_prompt, user_prompt):
        content = self.content(json.loads(user_prompt)) if callable(self.content) else self.content
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(content))


def reference_with_time_and_filter():
    p = json.loads((FIXTURES / 'reference_proposal.json').read_text(encoding='utf-8'))
    for t in p['object_types']:
        if t['key'] == 'recall_campaign':
            t['time_field'] = {'source': 'recalls', 'path': 'ReportReceivedDate'}
        if t['key'] == 'complaint':
            t['time_field'] = {'source': 'complaints', 'path': 'dateComplaintFiled'}
        if t['key'] == 'vehicle_model_year':
            t['populated_from'][1]['where'] = [{'path': 'products[].type', 'equals': 'Vehicle'},
                                               {'path': 'products[].productMake', 'equals': 'CHEVROLET'}]
    return p


class ReferenceTests(unittest.TestCase):
    def test_short_recall_numbers_in_text_resolve_to_campaigns(self):
        text = 'vehicles previously recalled under NHTSA recall number 20V-701. Also see 21V650000.'
        self.assertEqual(referenced_campaigns(text, ['20V701000', '21V560000', '21V650000']), ['20V701000', '21V650000'])
        self.assertEqual(referenced_campaigns('no references here', ['20V701000']), [])


class SeriesPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_source_bundle(ROOT / 'examples/nhtsa/chevrolet_bolt_2017_2023.json')
        ontology = auto_build_ontology(cls.bundle, Reply(reference_with_time_and_filter()))
        assert ontology['status'] == 'auto_built_verified', ontology['verification']
        ontology = propose_value_aliases(ontology, cls.bundle, Reply({'aliases': [{
            'type': 'component', 'source': 'complaints', 'value': 'SERVICE BRAKES', 'target_source': 'recalls',
            'target_value': 'SERVICE BRAKES, HYDRAULIC', 'reasoning': 'same brake system'}]}))
        checked = check_candidates(scope(ontology, cls.bundle, {'campaign_number': '21V650000'}), ontology, cls.bundle,
                                   Reply(lambda req: {'results': [{'id': i['id'], 'reasoning': 'r', 'verdict': 'no',
                                                                   'evidence': ''} for i in req['complaints']]}))
        cls.report = {'requested_model': 'deepseek-flash', 'started_at': '2026-09-13T00:00:00+00:00',
                      'ontology': ontology, 'scopes': {'21V650000': checked}}
        cls.pack = build_review_pack(cls.report, cls.bundle)
        cls.recalls = {r['id']: r for r in cls.pack['recalls']}

    def test_recalls_group_by_part_and_chain_by_explicit_references(self):
        self.assertEqual(len(self.pack['groups']), 6)
        battery = [r for r in self.pack['recalls'] if r['series'] == '20V701000']
        self.assertEqual([r['id'] for r in battery], ['20V701000', '21V560000', '21V650000', '24V481000', '24V812000'])
        self.assertEqual(self.recalls['24V812000']['references'], ['21V650000'])
        self.assertEqual(self.recalls['24V812000']['date'], '2024-10-31')
        self.assertEqual(self.recalls['21V517000']['group'], self.recalls['23V567000']['group'])
        self.assertNotEqual(self.recalls['21V517000']['series'], self.recalls['23V567000']['series'])

    def test_text_checks_are_shared_within_a_series_only(self):
        later = self.recalls['24V812000']
        self.assertTrue(later['text_checked'])
        self.assertTrue(all(c['text_check'] and c['text_check']['verdict'] == 'no' for c in later['candidates']))
        self.assertFalse(self.recalls['23V567000']['text_checked'])

    def test_candidates_carry_timing_alias_and_flags(self):
        battery = {c['id']: c for c in self.recalls['21V650000']['candidates']}
        self.assertEqual(battery['11600123']['timing']['relation'], 'after')
        self.assertFalse(battery['11600123']['via_alias'])
        self.assertEqual(self.pack['signals']['11600123']['flags'], ['fire'])
        self.assertEqual(self.pack['signals']['11600123']['date'], '2024-07-08')
        brakes = self.recalls['20V808000']['candidates']
        self.assertTrue(brakes and all(c['via_alias'] for c in brakes))
        outside = [c for c in battery.values() if c['bucket'] == 'outside_all']
        self.assertEqual({c['timing']['relation'] for c in outside}, {'after'})

    def test_no_tires_or_placeholders_become_vehicles(self):
        objects = {o for s in self.pack['signals'].values() for o in s['objects']}
        self.assertFalse([o for o in objects if not o.startswith('CHEVROLET ')], objects)

    def test_page_facts_for_confirmation_and_blind_spots(self):
        o = self.pack['ontology']
        self.assertEqual([(a['value'], a['target_value']) for a in o['value_aliases']],
                         [('SERVICE BRAKES', 'SERVICE BRAKES, HYDRAULIC')])
        self.assertEqual({t['key']: t['time_field']['path'] for t in o['object_types'] if t.get('time_field')},
                         {'recall_campaign': 'ReportReceivedDate', 'complaint': 'dateComplaintFiled'})
        self.assertEqual(self.pack['source']['events'], 13)
        blind = self.pack['unconsidered']
        self.assertEqual(blind['count'] + len({c['id'] for r in self.pack['recalls'] for c in r['candidates']}), 679)
        self.assertEqual(dict(blind['top_parts'])['UNKNOWN OR OTHER'] >= 46, True)


if __name__ == '__main__':
    unittest.main()
