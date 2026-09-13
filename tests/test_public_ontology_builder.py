import importlib
import json
from pathlib import Path
import unittest

from ontology_poc_generator.nhtsa_sources import bundle_content_hash
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class FakeGateway:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append({'system': system_prompt, 'user': user_prompt})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return ModelCompletion(provider='fake', model='deepseek-flash', content=content)


class AutoBuildOntologyTests(unittest.TestCase):
    def api(self):
        module = importlib.import_module('ontology_poc_generator.public_ontology')
        self.assertTrue(hasattr(module, 'auto_build_ontology'), 'auto ontology builder is not implemented')
        return module

    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.recorded = load('recorded_modeler_attempts.json')

    def test_code_errors_are_sent_back_and_second_attempt_passes(self):
        gw = FakeGateway(self.recorded)
        o = self.api().auto_build_ontology(self.bundle, gw)
        self.assertEqual(o['schema'], 'public_ontology.v1')
        self.assertEqual(o['status'], 'auto_built_verified')
        self.assertEqual(o['human_review'], 'pending')
        self.assertEqual([[e['code'] for e in a['errors']] for a in o['attempts']], [['role_relation_missing'], []])
        retry = json.loads(gw.calls[1]['user'])
        self.assertEqual([e['code'] for e in retry['errors_found_by_code']], ['role_relation_missing'])
        self.assertEqual(retry['previous_proposal'], self.recorded[0])
        self.assertEqual(o['verification']['errors'], [])
        self.assertEqual(o['verification']['metrics']['shared_across_sources']['vehicle_model_year'], 2)

    def test_output_carries_provenance_and_stable_ids(self):
        o = self.api().auto_build_ontology(self.bundle, FakeGateway(self.recorded))
        self.assertEqual(o['source_bundle_hash'], bundle_content_hash(self.bundle))
        self.assertEqual(o['model'], 'deepseek-flash')
        self.assertEqual(o['prompt_version'], 'public_ontology_modeler.v2')
        self.assertEqual(o['evidence_scope'], 'public_data')
        self.assertTrue(all(t['type_id'].startswith('entity_type_') for t in o['object_types']))
        self.assertTrue(all(r['relation_type_id'].startswith('relation_type_') for r in o['relations']))
        again = self.api().auto_build_ontology(self.bundle, FakeGateway(self.recorded))
        self.assertEqual([t['type_id'] for t in o['object_types']], [t['type_id'] for t in again['object_types']])
        self.assertEqual(o['data_gaps'], self.recorded[1]['open_questions'])

    def test_stops_when_errors_do_not_shrink(self):
        gw = FakeGateway([self.recorded[0], self.recorded[0], self.recorded[1]])
        o = self.api().auto_build_ontology(self.bundle, gw)
        self.assertEqual(o['status'], 'blocked')
        self.assertEqual(len(gw.calls), 2)
        self.assertEqual([e['code'] for e in o['verification']['errors']], ['role_relation_missing'])

    def test_non_json_and_model_failure_block_without_raising(self):
        o = self.api().auto_build_ontology(self.bundle, FakeGateway(['not json', 'still not json']))
        self.assertEqual(o['status'], 'blocked')
        self.assertEqual(o['attempts'][0]['errors'][0]['code'], 'invalid_response')
        failing = FakeGateway([RecognitionError('timeout'), RecognitionError('timeout')])
        o = self.api().auto_build_ontology(self.bundle, failing)
        self.assertEqual(o['status'], 'blocked')
        self.assertEqual(o['attempts'][0]['errors'][0]['code'], 'model_request_failed')

    def test_model_sees_field_catalog_not_full_records(self):
        gw = FakeGateway(self.recorded)
        self.api().auto_build_ontology(self.bundle, gw)
        first = json.loads(gw.calls[0]['user'])
        self.assertEqual(set(first), {'decision', 'sources'})
        self.assertIn('summary', first['sources']['complaints']['fields'])
        late = next(r for r in self.bundle['sources']['complaints']['records'] if r['odiNumber'] == 11600123)
        self.assertNotIn(late['summary'][:60], gw.calls[0]['user'])

    def test_model_cannot_mark_its_own_ontology_reviewed(self):
        tampered = [dict(self.recorded[1], human_review='confirmed', status='published')]
        o = self.api().auto_build_ontology(self.bundle, FakeGateway(tampered))
        self.assertEqual(o['human_review'], 'pending')
        self.assertEqual(o['status'], 'auto_built_verified')


if __name__ == '__main__':
    unittest.main()
