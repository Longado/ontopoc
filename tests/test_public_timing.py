import copy
import json
from pathlib import Path
import unittest

from ontology_poc_generator.public_ontology import auto_build_ontology, verify_proposal
from ontology_poc_generator.public_scope import scope
from ontology_poc_generator.recognition import ModelCompletion

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def with_time_fields(proposal, recall_path='ReportReceivedDate', complaint_path='dateComplaintFiled'):
    p = copy.deepcopy(proposal)
    for t in p['object_types']:
        if t['key'] == 'recall_campaign':
            t['time_field'] = {'source': 'recalls', 'path': recall_path}
        if t['key'] == 'complaint':
            t['time_field'] = {'source': 'complaints', 'path': complaint_path}
    return p


class Reply:
    def __init__(self, proposal):
        self.proposal = proposal

    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='m', content=json.dumps(self.proposal))


class TimeFieldTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.proposal = load('reference_proposal.json')

    def codes(self, proposal):
        return {e['code'] for e in verify_proposal(proposal, self.bundle)['errors']}

    def test_declared_time_fields_must_be_real_date_fields(self):
        self.assertEqual(self.codes(with_time_fields(self.proposal)), set())
        self.assertIn('time_field_invalid', self.codes(with_time_fields(self.proposal, complaint_path='summary')))
        self.assertIn('time_field_invalid', self.codes(with_time_fields(self.proposal, recall_path='NoSuchDate')))
        wrong_source = with_time_fields(self.proposal)
        next(t for t in wrong_source['object_types'] if t['key'] == 'complaint')['time_field']['source'] = 'recalls'
        self.assertIn('time_field_invalid', self.codes(wrong_source))

    def test_a_month_is_never_given_a_day_count(self):
        from ontology_poc_generator.public_scope import _timing
        self.assertEqual(_timing('2026-03', '2026-05'), {'event_date': '2026-03', 'signal_date': '2026-05', 'relation': 'after', 'days': None, 'months': 2})
        self.assertEqual(_timing('2026-03-15', '2026-03')['relation'], 'same_month')      # not "14 days earlier"
        self.assertEqual(_timing('2026-03-15', '2026-03')['days'], None)
        self.assertEqual(_timing('2025-12', '2025-10')['months'], -2)
        self.assertEqual(_timing('2026-03-01T09:00:00', '2026-03-05 10:00')['days'], 4)       # timestamps are their day
        self.assertEqual(_timing('2026-03-10', '2026-03-10')['relation'], 'same_day')

    def run_scope(self, proposal, campaign):
        ontology = auto_build_ontology(self.bundle, Reply(proposal))
        self.assertEqual(ontology['status'], 'auto_built_verified')
        return {c['signal']['odi_number']: c for c in
                scope(ontology, self.bundle, {'campaign_number': campaign})['candidates']}

    def test_candidates_are_placed_before_or_after_the_recall(self):
        battery = self.run_scope(with_time_fields(self.proposal), '21V650000')
        self.assertEqual(battery['11600123']['timing'],
                         {'event_date': '2021-08-20', 'signal_date': '2024-07-08', 'relation': 'after', 'days': 1053})
        self.assertEqual(battery['11429891']['timing']['relation'], 'same_day')
        earlier = self.run_scope(with_time_fields(self.proposal), '20V701000')
        self.assertEqual(earlier['11429913']['timing'], {'event_date': '2020-11-13', 'signal_date': '2021-08-20',
                                                         'relation': 'after', 'days': 280})

    def test_without_time_fields_timing_is_unknown(self):
        battery = self.run_scope(self.proposal, '21V650000')
        self.assertIsNone(battery['11600123']['timing'])


if __name__ == '__main__':
    unittest.main()
