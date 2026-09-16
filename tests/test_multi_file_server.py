import base64
import unittest

import json

from ontology_poc_generator.recognition import ModelCompletion
from tests.test_ontology_ask_server import call
from tests.test_ontology_server import OntologyServerTests

PROPOSAL = {
    'reasoning': 'orders reference customers', 'ignored_fields': [], 'open_questions': [],
    'object_types': [
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'customer_id': '客户编号'}},
                                                             {'source': '订单', 'identity': {'customer_id': '客户编号'}}],
         'attributes': [{'source': '客户', 'path': '名称'}], 'rationale': 'r'},
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': '订单', 'identity': {'order_id': '订单号'}}],
         'attributes': [{'source': '订单', 'path': '金额'}], 'rationale': 'r'},
    ],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': '订单', 'meaning': '订单属于客户'}],
}


class TwoTableModel:
    """A model that proposes an ontology fitting both uploaded tables."""

    def complete_json(self, *, system_prompt, user_prompt):
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(PROPOSAL, ensure_ascii=False))

CUSTOMERS = '客户编号,名称\nC1,甲\nC2,乙\n'.encode('utf-8')
ORDERS = '订单号,客户编号,金额\nO1,C1,100\nO2,C2,50\n'.encode('utf-8')
def part(name, data):
    return {'filename': name, 'content_base64': base64.b64encode(data).decode()}


class MultiFileServerTests(unittest.TestCase):
    def test_a_batch_of_tables_is_built_as_one_and_found_again_next_time(self):
        with OntologyServerTests().server(gateway=TwoTableModel()) as (base, _):
            payload = {'files': [part('客户.csv', CUSTOMERS), part('订单.csv', ORDERS)], 'purpose': '摸底'}
            status, run = call(base, '/api/ontology/build', payload)
            self.assertEqual(status, 200, run)
            self.assertEqual(sorted(s['name'] for s in run['sources']), ['客户', '订单'])
            _, again = call(base, '/api/ontology/build', payload)
            self.assertEqual(again['previous']['saved_as'], run['saved_as'])

    def test_a_document_in_the_batch_is_refused_by_name(self):
        with OntologyServerTests().server(gateway=TwoTableModel()) as (base, _):
            status, body = call(base, '/api/ontology/build', {'files': [part('客户.csv', CUSTOMERS), part('流程.md', '制度'.encode())]})
        self.assertEqual(status, 400)
        self.assertIn('流程.md', body['error'])

    def test_the_old_single_file_shape_still_works(self):
        with OntologyServerTests().server(gateway=TwoTableModel()) as (base, _):
            status, run = call(base, '/api/ontology/build', part('订单.csv', ORDERS))
        self.assertEqual(status, 200, run)
        self.assertEqual([s['name'] for s in run['sources']], ['订单'])


if __name__ == '__main__':
    unittest.main()
