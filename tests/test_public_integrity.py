"""Reproductions from the 2026-09-13 code review: the source-bundle anchor must hold on every path."""
import copy
import json
from pathlib import Path
import unittest

from ontology_poc_generator.nhtsa_sources import build_nhtsa_bundle
from ontology_poc_generator.public_review_pack import PackError, build_review_pack
from ontology_poc_generator.public_scope import ScopeError, check_candidates, scope
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_public_review_pack import make_report

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class NoMatch:
    def complete_json(self, *, system_prompt, user_prompt):
        items = json.loads(user_prompt)['complaints']
        return ModelCompletion(provider='fake', model='m', content=json.dumps(
            {'results': [{'id': i['id'], 'reasoning': '', 'verdict': 'no', 'evidence': ''} for i in items]}))


class SourceAnchorTests(unittest.TestCase):
    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.report = make_report(self.bundle)

    def test_pack_refuses_other_bundle_even_without_events(self):
        other = copy.deepcopy(self.bundle)
        other['sources']['recalls']['records'] = []
        with self.assertRaises(PackError):
            build_review_pack(self.report, other)

    def test_text_check_refuses_other_bundle(self):
        result = scope(self.report['ontology'], self.bundle, {'campaign_number': '21V650000'})
        other = copy.deepcopy(self.bundle)
        other['sources']['complaints']['records'][0]['summary'] = 'changed after the ontology was built'
        with self.assertRaises(ScopeError):
            check_candidates(result, self.report['ontology'], other, NoMatch())

    def test_bundle_does_not_share_record_objects_with_the_caller(self):
        record = {'NHTSACampaignNumber': 'X', 'Model': 'M', 'ModelYear': '2020'}
        bundle = build_nhtsa_bundle([
            {'kind': 'recalls', 'url': 'https://r', 'retrieved_at': 't', 'payload': {'results': [record]}},
            {'kind': 'complaints', 'url': 'https://c', 'retrieved_at': 't', 'payload': {'results': []}},
        ], decision='d')
        record['Model'] = 'CHANGED'
        self.assertEqual(bundle['sources']['recalls']['records'][0]['Model'], 'M')


if __name__ == '__main__':
    unittest.main()
