"""A shown build may retry three times; its automatic question must share the action's budget."""
import base64
import copy
import json
import threading
import unittest

from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_ask_server import QUESTIONS, call
from tests import test_ontology_server as server_helpers
from tests.test_ontology_server import CSV, PROPOSAL


class CorrectingModel:
    def __init__(self, attempts):
        self.attempts = attempts
        self.chains = {}
        self.lock = threading.Lock()

    def complete_json(self, *, system_prompt, user_prompt):
        is_question = system_prompt == QUESTION_SYSTEM_PROMPT
        with self.lock:
            chain = self.chains.setdefault(threading.get_ident(), [])
            chain.append('question' if is_question else 'model')
            count = chain.count('model')
        proposal = copy.deepcopy(PROPOSAL)
        proposal['object_types'][0]['attributes'] += [{'source': 'orders', 'path': f'Missing{i}'}
                                                     for i in range(max(0, self.attempts - count))]
        return ModelCompletion(provider='fake', model='fake', content=json.dumps(QUESTIONS if is_question else proposal))


class UploadCallBudgetTests(unittest.TestCase):
    def test_third_correcting_attempt_keeps_verified_draft_and_defers_automatic_question(self):
        model = CorrectingModel(3)
        with server_helpers.OntologyServerTests().server(gateway=model) as (base, _):
            status, run = call(base, '/api/ontology/build', {'filename': 'orders.csv',
                               'content_base64': base64.b64encode(CSV).decode(), 'purpose': '客户订单数？'})
            self.assertEqual(status, 200, run)
            self.assertEqual(run['ontology']['status'], 'auto_built_verified')
            self.assertEqual(len(run['ontology']['attempts']), 3)
            self.assertLessEqual(max(map(len, model.chains.values())), 3)
            self.assertFalse(any('question' in chain for chain in model.chains.values()))
            deferred = run['evaluation']['asked'][0]
            self.assertEqual(deferred['items'], [])
            self.assertIn('单独提问', deferred['error'])
            self.assertEqual((deferred['answered'], deferred['total']), (0, 0))
            self.assertTrue(deferred['asked_at'])
            self.assertTrue(deferred['prompt_version'])

    def test_two_correcting_attempts_leave_one_call_for_the_automatic_question(self):
        model = CorrectingModel(2)
        with server_helpers.OntologyServerTests().server(gateway=model) as (base, _):
            status, run = call(base, '/api/ontology/build', {'filename': 'orders.csv',
                               'content_base64': base64.b64encode(CSV).decode(), 'purpose': '客户订单数？'})
            self.assertEqual(status, 200, run)
            self.assertEqual(run['ontology']['status'], 'auto_built_verified')
            self.assertEqual(len(run['ontology']['attempts']), 2)
            question_chains = [chain for chain in model.chains.values() if 'question' in chain]
            self.assertEqual(question_chains, [['model', 'model', 'question']])
            self.assertLessEqual(max(map(len, model.chains.values())), 3)
            self.assertEqual(run['evaluation']['asked'][0]['items'][0]['status'], 'answered')
