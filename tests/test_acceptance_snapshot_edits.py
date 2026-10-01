"""Editing other questions cannot change the identity evidence of an already accepted query."""
import base64
import copy
import json
import unittest

from ontology_poc_generator.recognition import ModelCompletion
from ontology_poc_generator.mcp_server import LocalService, handle
from ontology_poc_generator.ontology_questions import QUESTION_SYSTEM_PROMPT
from tests.test_ontology_ask_server import call
from tests import test_ontology_server as server_helpers
from tests.test_ontology_server import PROPOSAL


CSV = '订单号,客户编号,金额,BillToId\nO1,C1,100,C1\nO2,C2,50,C2\n'.encode('utf-8')
UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
A = {'question': '购买客户数？', 'query': {'start': 'order', 'via': ['order_customer']}, 'note': '按购买客户编号'}
B = {'question': '订单数？', 'query': {'start': 'order'}, 'note': ''}


class BoundModel:
    column = '客户编号'

    def complete_json(self, *, system_prompt, user_prompt):
        if system_prompt == QUESTION_SYSTEM_PROMPT:
            return ModelCompletion(provider='fake', model='fake', content=json.dumps({'questions': [A]}))
        proposal = copy.deepcopy(PROPOSAL)
        proposal['object_types'][0]['attributes'].append({'source': 'orders', 'path': 'BillToId'})
        proposal['relations'][0].update(from_identity={'order_id': '订单号'}, to_identity={'customer_id': self.column})
        return ModelCompletion(provider='fake', model='fake', content=json.dumps(proposal))


class AcceptanceSnapshotEditTests(unittest.TestCase):
    def test_removing_another_question_keeps_broken_snapshot_even_from_an_older_client(self):
        model = BoundModel()
        with server_helpers.OntologyServerTests().server(gateway=model) as (base, _):
            first = call(base, '/api/ontology/build', UPLOAD)[1]
            call(base, '/api/ontology/acceptance', {'saved_as': first['saved_as'], 'items': [A, B]})
            model.column = 'BillToId'
            again = call(base, '/api/ontology/build', UPLOAD)[1]
            original = again['evaluation']['acceptance']['items'][0]
            self.assertEqual(original['status'], 'broken')
            for extra in ({}, {'snapshot': {'types': [], 'relations': []}}):
                with self.subTest(client_context=extra):
                    status, edited = call(base, '/api/ontology/acceptance',
                                          {'saved_as': again['saved_as'], 'items': [{**A, **extra}]})
                    self.assertEqual(status, 200, edited)
                    kept = edited['evaluation']['acceptance']['items'][0]
                    self.assertEqual(kept['status'], 'broken')
                    self.assertEqual(kept['snapshot'], original['snapshot'])
            rerun = call(base, '/api/ontology/build', UPLOAD)[1]
            self.assertEqual(rerun['evaluation']['acceptance']['items'][0]['status'], 'broken')

    def test_deliberately_removing_and_accepting_again_uses_the_current_binding(self):
        model = BoundModel()
        with server_helpers.OntologyServerTests().server(gateway=model) as (base, _):
            first = call(base, '/api/ontology/build', UPLOAD)[1]
            call(base, '/api/ontology/acceptance', {'saved_as': first['saved_as'], 'items': [A]})
            model.column = 'BillToId'
            again = call(base, '/api/ontology/build', UPLOAD)[1]
            call(base, '/api/ontology/acceptance', {'saved_as': again['saved_as'], 'items': []})
            accepted = call(base, '/api/ontology/acceptance', {'saved_as': again['saved_as'], 'items': [A]})[1]
            item = accepted['evaluation']['acceptance']['items'][0]
            self.assertEqual(item['status'], 'answered')
            self.assertEqual(item['snapshot']['relations'][0]['to_identity'], {'customer_id': 'BillToId'})

    def test_explicit_mcp_reaccept_uses_the_new_binding_without_reaccepting_other_questions(self):
        model = BoundModel()
        with server_helpers.OntologyServerTests().server(gateway=model) as (base, _):
            first = call(base, '/api/ontology/build', UPLOAD)[1]
            call(base, '/api/ontology/acceptance', {'saved_as': first['saved_as'], 'items': [A, B]})
            model.column = 'BillToId'
            again = call(base, '/api/ontology/build', UPLOAD)[1]
            old = again['evaluation']['acceptance']['items']
            self.assertEqual(old[0]['status'], 'broken')
            asked = call(base, '/api/ontology/ask', {'saved_as': again['saved_as'], 'question': A['question']})[1]
            self.assertEqual(asked['evaluation']['asked'][-1]['items'][0]['status'], 'answered')
            response = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'fix_question',
                               'arguments': {'saved_as': again['saved_as'], 'question': A['question'],
                                             'note': '明确认可 BillToId 口径'}}}, LocalService(base))['result']
            self.assertFalse(response.get('isError'), response)
            items = response['structuredContent']['acceptance']['items']
            new_a = next(item for item in items if item['question'] == A['question'])
            kept_b = next(item for item in items if item['question'] == B['question'])
            self.assertEqual(new_a['status'], 'answered')
            self.assertEqual(new_a['snapshot']['relations'][0]['to_identity'], {'customer_id': 'BillToId'})
            self.assertEqual(kept_b['snapshot'], old[1]['snapshot'])
