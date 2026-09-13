import copy
import json
from pathlib import Path
import unittest

from ontology_poc_generator.public_ontology import auto_build_ontology, propose_value_aliases
from ontology_poc_generator.public_scope import scope
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class Reply:
    def __init__(self, content):
        self.content = content
        self.requests = []

    def complete_json(self, *, system_prompt, user_prompt):
        self.requests.append(json.loads(user_prompt))
        if isinstance(self.content, Exception):
            raise self.content
        text = self.content if isinstance(self.content, str) else json.dumps(self.content)
        return ModelCompletion(provider='fake', model='m', content=text)


def alias(value, target, source='complaints', target_source='recalls', type_='component'):
    return {'type': type_, 'source': source, 'value': value, 'target_source': target_source,
            'target_value': target, 'reasoning': 'same system, different spelling'}


class ValueAliasTests(unittest.TestCase):
    def setUp(self):
        self.bundle = copy.deepcopy(load('mini_bundle.json'))
        recall = copy.deepcopy(self.bundle['sources']['recalls']['records'][0])
        recall.update({'NHTSACampaignNumber': '18V576000', 'Model': 'BOLT EV', 'ModelYear': '2019',
                       'Component': 'SERVICE BRAKES, HYDRAULIC:FOUNDATION COMPONENTS:DISC:CALIPER'})
        self.bundle['sources']['recalls']['records'].append(recall)
        complaint = copy.deepcopy(next(r for r in self.bundle['sources']['complaints']['records']
                                       if r['odiNumber'] == 11749605))
        complaint.update({'odiNumber': 11800001, 'components': 'SERVICE BRAKES', 'summary': 'Brakes grind and pull.'})
        self.bundle['sources']['complaints']['records'].append(complaint)
        self.ontology = auto_build_ontology(self.bundle, Reply(load('reference_proposal.json')))
        self.assertEqual(self.ontology['status'], 'auto_built_verified')

    def brake_candidates(self, ontology):
        return {c['signal']['odi_number']: c for c in
                scope(ontology, self.bundle, {'campaign_number': '18V576000'})['candidates']}

    def test_without_alias_the_brake_complaint_is_missed(self):
        self.assertEqual(self.brake_candidates(self.ontology), {})

    def test_model_sees_values_that_only_one_source_has(self):
        gw = Reply({'aliases': []})
        propose_value_aliases(self.ontology, self.bundle, gw)
        component = gw.requests[0]['types']['component']
        self.assertIn('SERVICE BRAKES', component['map_from']['complaints'])
        self.assertIn('SERVICE BRAKES, HYDRAULIC', component['map_to']['recalls'])
        self.assertNotIn('AIR BAGS', component['map_from']['complaints'])
        self.assertNotIn('vehicle_model_year', gw.requests[0]['types'])

    def test_accepted_alias_links_the_brake_complaint_and_is_marked(self):
        before = copy.deepcopy(self.ontology)
        aligned = propose_value_aliases(self.ontology, self.bundle,
                                        Reply({'aliases': [alias('SERVICE BRAKES', 'SERVICE BRAKES, HYDRAULIC')]}))
        self.assertEqual(self.ontology, before)
        self.assertEqual(aligned['status'], 'auto_built_verified')
        self.assertEqual(aligned['human_review'], 'pending')
        (accepted,) = aligned['value_aliases']
        self.assertEqual((accepted['value'], accepted['target_value'], accepted['records_linked']),
                         ('SERVICE BRAKES', 'SERVICE BRAKES, HYDRAULIC', 1))
        c = self.brake_candidates(aligned)['11800001']
        self.assertTrue(c['via_alias'])
        self.assertEqual(c['part_match'], 'same_category')
        battery = {c['signal']['odi_number']: c for c in
                   scope(aligned, self.bundle, {'campaign_number': '21V650000'})['candidates']}
        self.assertFalse(battery['11600123']['via_alias'])

    def test_code_rejects_aliases_that_do_not_hold_in_the_data(self):
        proposals = [
            alias('BRAKES', 'SERVICE BRAKES, HYDRAULIC'),
            alias('SERVICE BRAKES', 'HYDRAULICS'),
            alias('AIR BAGS', 'AIR BAGS:FRONTAL'),
            alias('SERVICE BRAKES, HYDRAULIC', 'SERVICE BRAKES', source='recalls', target_source='complaints'),
            alias('SERVICE BRAKES', 'SERVICE BRAKES, HYDRAULIC'),
            alias('SERVICE BRAKES', 'ELECTRICAL SYSTEM'),
            alias('BOLT EV', 'BOLT EUV', type_='vehicle_model_year'),
        ]
        aligned = propose_value_aliases(self.ontology, self.bundle, Reply({'aliases': proposals}))
        self.assertEqual([a['value'] for a in aligned['value_aliases']], ['SERVICE BRAKES'])
        verdicts = [p['verdict'] for p in aligned['alias_proposals']]
        self.assertEqual(verdicts, ['rejected', 'rejected', 'rejected', 'rejected', 'accepted', 'rejected', 'rejected'])
        self.assertTrue(all(p['reason'] for p in aligned['alias_proposals'] if p['verdict'] == 'rejected'))

    def test_model_failure_leaves_the_ontology_usable(self):
        for reply in (Reply('not json'), Reply(RecognitionError('timeout')), Reply({'aliases': 'x'})):
            with self.subTest(reply=reply.content):
                aligned = propose_value_aliases(self.ontology, self.bundle, reply)
                self.assertEqual(aligned['value_aliases'], [])
                self.assertTrue(aligned['alias_error'])
                self.assertEqual(self.brake_candidates(aligned), {})


if __name__ == '__main__':
    unittest.main()
