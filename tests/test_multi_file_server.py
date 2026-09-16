import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import OntologyServerTests

CUSTOMERS = '客户编号,名称\nC1,甲\nC2,乙\n'.encode('utf-8')
ORDERS = '订单号,客户编号,金额\nO1,C1,100\nO2,C2,50\n'.encode('utf-8')
def part(name, data):
    return {'filename': name, 'content_base64': base64.b64encode(data).decode()}


class MultiFileServerTests(unittest.TestCase):
    def test_a_batch_of_tables_is_built_as_one_and_found_again_next_time(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            payload = {'files': [part('客户.csv', CUSTOMERS), part('订单.csv', ORDERS)], 'purpose': '摸底'}
            status, run = call(base, '/api/ontology/build', payload)
            self.assertEqual(status, 200, run)
            self.assertEqual(sorted(s['name'] for s in run['sources']), ['客户', '订单'])
            _, again = call(base, '/api/ontology/build', payload)
            self.assertEqual(again['previous']['saved_as'], run['saved_as'])

    def test_a_document_in_the_batch_is_refused_by_name(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            status, body = call(base, '/api/ontology/build', {'files': [part('客户.csv', CUSTOMERS), part('流程.md', '制度'.encode())]})
        self.assertEqual(status, 400)
        self.assertIn('流程.md', body['error'])

    def test_the_old_single_file_shape_still_works(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            status, run = call(base, '/api/ontology/build', part('订单.csv', ORDERS))
        self.assertEqual(status, 200, run)
        self.assertEqual([s['name'] for s in run['sources']], ['订单'])


if __name__ == '__main__':
    unittest.main()
