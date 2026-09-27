"""Acceptance must use the person's current decisions and confirmed formulas, including after a rerun."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest

from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from tests.test_derived_measures import AMOUNT, BY_CUSTOMER, CSV, Model
from tests.test_ontology_ask_server import call
from tests import test_ontology_server as server_helpers

UPLOAD = {'filename': 'lines.csv', 'content_base64': base64.b64encode(CSV).decode()}
COUNT = {**BY_CUSTOMER, 'measure': None}
ITEM = {'question': '每个客户有几条订单明细？', 'query': COUNT, 'note': ''}


def decisions(run, verdict='wrong'):
    return {'types': {t['key']: {'verdict': 'ok'} for t in run['ontology']['object_types']},
            'relations': {'line_of_customer': {'verdict': verdict}}, 'added': []}


class ReviewedAcceptanceTests(unittest.TestCase):
    def test_saving_acceptance_respects_a_rejected_relation(self):
        with server_helpers.OntologyServerTests().server(gateway=Model()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            code, _ = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions(run)})
            self.assertEqual(code, 200)
            code, saved = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [ITEM]})
            self.assertEqual(code, 200)
            self.assertEqual(saved['evaluation']['acceptance']['answered'], 0)
            self.assertEqual(saved['evaluation']['acceptance']['items'][0]['status'], 'broken')

    def test_confirmation_rechecks_existing_acceptance_and_persists_it(self):
        with server_helpers.OntologyServerTests().server(gateway=Model()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            _, saved = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [ITEM]})
            self.assertEqual(saved['evaluation']['acceptance']['answered'], 1)
            _, reviewed = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions(run)})
            self.assertEqual(reviewed['evaluation']['acceptance']['answered'], 0)
            stored = json.loads((out / run['saved_as']).read_text())
            self.assertEqual(stored['evaluation']['acceptance']['items'][0]['status'], 'broken')
            # A correction can also restore a previously broken acceptance query.
            _, restored = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions(run, 'ok')})
            self.assertEqual(restored['evaluation']['acceptance']['answered'], 1)

    def test_rerun_does_not_revive_a_relation_rejected_in_the_saved_reference(self):
        with server_helpers.OntologyServerTests().server(gateway=Model()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [ITEM]})
            call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions(run)})
            _, rerun = call(base, '/api/ontology/build', UPLOAD)
            self.assertEqual(rerun['evaluation']['reference']['suggested']['relations']['line_of_customer']['verdict'], 'wrong')
            self.assertEqual(rerun['evaluation']['acceptance']['answered'], 0)

    def test_confirmed_formula_can_be_saved_and_rechecked_as_acceptance(self):
        with server_helpers.OntologyServerTests().server(gateway=Model()) as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            call(base, '/api/ontology/derived', {'saved_as': run['saved_as'], 'derive': AMOUNT})
            _, saved = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [{**ITEM, 'query': BY_CUSTOMER}]})
            self.assertEqual(saved['evaluation']['acceptance']['answered'], 1)
            self.assertEqual(saved['evaluation']['acceptance']['items'][0]['answer']['groups'], [['C1', 30, 2], ['C2', 3, 1]])
            _, rerun = call(base, '/api/ontology/build', UPLOAD)
            self.assertEqual(rerun['evaluation']['acceptance']['answered'], 1)
            self.assertFalse(rerun['evaluation']['acceptance']['items'][0]['changed'])


class WaitingModel(Model):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == QUESTION_SYSTEM_PROMPT:
            self.entered.set()
            if not self.release.wait(10):
                raise RuntimeError('test did not release the waiting question')
        return super().complete_json(system_prompt=system_prompt, user_prompt=user_prompt)


class AskConfirmationRaceTests(unittest.TestCase):
    def test_confirmation_changed_during_model_wait_refuses_old_answer_without_writing_it(self):
        for personal in (True, False):
            with self.subTest(personal=personal):
                model = WaitingModel()
                with server_helpers.OntologyServerTests().server(gateway=model) as (base, out):
                    _, run = call(base, '/api/ontology/build', UPLOAD)
                    call(base, '/api/ontology/derived', {'saved_as': run['saved_as'], 'derive': AMOUNT})
                    payload = {'saved_as': run['saved_as'], **({'question': '每个客户买了多少钱？'} if personal else {})}
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(call, base, '/api/ontology/ask', payload)
                        try:
                            self.assertTrue(model.entered.wait(5))
                            code, _ = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions(run)})
                            self.assertEqual(code, 200)
                        finally:
                            model.release.set()
                        code, body = future.result(timeout=10)
                    self.assertEqual(code, 409, body)
                    self.assertIn('确认', body['error'])
                    stored = json.loads((out / run['saved_as']).read_text())
                    self.assertFalse(stored['evaluation'].get('asked'))
                    self.assertFalse(stored['evaluation'].get('questions'))
                    self.assertEqual(stored['confirmation']['decisions']['relations']['line_of_customer']['verdict'], 'wrong')
                    self.assertEqual(len(model.asked), 1)
