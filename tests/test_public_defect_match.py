import copy
import importlib
import json
from pathlib import Path
import unittest

from ontology_poc_generator.public_ontology import auto_build_ontology
from ontology_poc_generator.public_scope import scope
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


class OneReply:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(self.reply))


class Matcher:
    """Answers each batch through `decide(item) -> result dict or None (omit)`."""

    def __init__(self, decide):
        self.decide = decide
        self.calls = []

    def complete_json(self, *, system_prompt, user_prompt):
        request = json.loads(user_prompt)
        self.calls.append(request)
        results = [r for r in (self.decide(item) for item in request['complaints']) if r is not None]
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps({'results': results}))


class DefectMatchTests(unittest.TestCase):
    def api(self):
        module = importlib.import_module('ontology_poc_generator.public_scope')
        self.assertTrue(hasattr(module, 'check_candidates'), 'complaint text check is not implemented')
        return module

    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.ontology = auto_build_ontology(self.bundle, OneReply(load('reference_proposal.json')))
        self.scope = scope(self.ontology, self.bundle, {'campaign_number': '21V650000'})

    def check(self, gateway, **kw):
        return self.api().check_candidates(self.scope, self.ontology, self.bundle, gateway, **kw)

    def verdicts(self, result):
        return {c['signal']['odi_number']: c['text_check'] for c in result['candidates']}

    def test_batches_and_records_model_and_prompt_version(self):
        gw = Matcher(lambda item: {'id': item['id'], 'reasoning': 'r', 'verdict': 'no', 'evidence': ''})
        before = copy.deepcopy(self.scope)
        result = self.check(gw, batch_size=2)
        self.assertEqual([len(c['complaints']) for c in gw.calls], [2, 1])
        self.assertEqual(self.scope, before)
        for check in self.verdicts(result).values():
            self.assertEqual((check['verdict'], check['model'], check['prompt_version']),
                             ('no', 'deepseek-flash', 'public_defect_match.v2'))

    def test_recall_and_complaint_text_come_from_declared_attributes(self):
        gw = Matcher(lambda item: {'id': item['id'], 'reasoning': 'r', 'verdict': 'no', 'evidence': ''})
        self.check(gw)
        request = gw.calls[0]
        self.assertIn('could catch fire when charged to full or nearly full capacity', request['recall_defect'])
        fire = next(i for i in request['complaints'] if i['id'] == '11600123')
        self.assertIn('smoke coming from under the driver side seat', fire['text'])

    def test_yes_needs_evidence_that_really_is_in_the_complaint(self):
        def decide(item):
            if item['id'] == '11600123':
                return {'id': item['id'], 'reasoning': 'r', 'verdict': 'yes',
                        'evidence': 'smoke coming from under the driver side seat'}
            return {'id': item['id'], 'reasoning': 'r', 'verdict': 'yes', 'evidence': 'battery exploded twice'}
        v = self.verdicts(self.check(Matcher(decide)))
        self.assertEqual(v['11600123']['verdict'], 'yes')
        self.assertEqual(v['11429891']['verdict'], 'unknown')
        self.assertIn('evidence', v['11429891']['reasoning'])

    def test_missing_or_invalid_answers_become_unknown(self):
        def decide(item):
            if item['id'] == '11429891':
                return None
            return {'id': item['id'], 'reasoning': 'r', 'verdict': 'maybe', 'evidence': ''}
        v = self.verdicts(self.check(Matcher(decide)))
        self.assertEqual({k: c['verdict'] for k, c in v.items()},
                         {'11429891': 'unknown', '11429913': 'unknown', '11600123': 'unknown'})

    def test_failed_batch_marks_only_that_batch(self):
        class Flaky(Matcher):
            def complete_json(self, *, system_prompt, user_prompt):
                if not self.calls:
                    self.calls.append(json.loads(user_prompt))
                    raise RecognitionError('timeout')
                return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)
        gw = Flaky(lambda item: {'id': item['id'], 'reasoning': 'r', 'verdict': 'no', 'evidence': ''})
        v = self.verdicts(self.check(gw, batch_size=2))
        self.assertEqual([v[k]['verdict'] for k in ('11429891', '11429913', '11600123')], ['unknown', 'unknown', 'no'])
        self.assertIn('model request failed', v['11429891']['reasoning'])


if __name__ == '__main__':
    unittest.main()
