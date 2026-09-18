"""An object's own page lists its rows: one per object the ontology finds, with the fields read for it from every table."""
import base64
import json
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from ontology_poc_generator.object_rows import object_rows
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, PROPOSAL, OntologyServerTests


def table(*rows):
    header, *data = rows
    return {'records': [dict(zip(header, r)) for r in data], 'requests': []}


BUNDLE = {'sources': {
    'orders': table(('订单号', '客户编号', '金额'), ('O1', 'C1', '100'), ('O2', 'C2', '50'), ('O3', 'C1', '70')),
    'customers': table(('客户编号', '客户名称'), ('C1', '甲公司'), ('C3', '丙公司')),
}}
ONTOLOGY = {
    'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'order_id': '订单号'}}],
         'attributes': [{'source': 'orders', 'path': '金额'}]},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'orders', 'identity': {'customer_id': '客户编号'}},
                                                               {'source': 'customers', 'identity': {'customer_id': '客户编号'}}],
         'attributes': [{'source': 'customers', 'path': '客户名称'}]},
    ],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': 'orders'}],
    'ignored_fields': [], 'open_questions': [],
}


class ObjectRowsTests(unittest.TestCase):
    def test_one_row_per_object_with_what_every_table_says_about_it(self):
        page = object_rows(ONTOLOGY, BUNDLE, 'customer')
        self.assertEqual((page['label'], page['total'], page['columns']), ('客户', 3, ['客户编号', '客户名称']))
        self.assertEqual(page['rows'], [{'客户编号': 'C1', '客户名称': '甲公司'}, {'客户编号': 'C2'}, {'客户编号': 'C3', '客户名称': '丙公司'}])

    def test_rows_come_a_page_at_a_time(self):
        page = object_rows(ONTOLOGY, BUNDLE, 'order', page=2, size=2)
        self.assertEqual((page['total'], page['page'], page['size']), (3, 2, 2))
        self.assertEqual(page['rows'], [{'订单号': 'O3', '金额': '70'}])

    def test_an_object_the_ontology_does_not_have_is_refused(self):
        with self.assertRaises(KeyError):
            object_rows(ONTOLOGY, BUNDLE, 'invoice')
        with self.assertRaises(ValueError):
            object_rows(ONTOLOGY, BUNDLE, 'order', page=0)


class ObjectRowsServerTests(unittest.TestCase):
    def test_a_saved_run_serves_an_objects_rows(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/objects/customer?page=1") as response:
                page = json.load(response)
            self.assertEqual((page['total'], page['rows'][0]), (2, {'客户编号': 'C1'}))
            for bad in (f"{run['saved_as']}/objects/nope", f"{run['saved_as']}/objects/customer?page=x", 'nope.json/objects/customer'):
                with self.assertRaises(HTTPError) as refused:
                    urlopen(f'{base}/api/ontology/runs/{bad}')
                self.assertIn(refused.exception.code, (400, 404))
        self.assertEqual(PROPOSAL['object_types'][1]['key'], 'customer')


if __name__ == '__main__':
    unittest.main()
