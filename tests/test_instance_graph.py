"""The instance graph: one object from the data, and the objects the data connects it to."""
import base64
import json
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from ontology_poc_generator.object_rows import find_instances, neighbourhood
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests


def table(*rows):
    header, *data = rows
    return {'records': [dict(zip(header, r)) for r in data], 'requests': []}


BUNDLE = {'sources': {
    'orders': table(('订单号', '客户编号'), ('O1', 'c1'), ('O2', 'c1'), ('O3', 'c2')),
    'customers': table(('客户编号', '客户名称'), ('c1', '甲公司'), ('c2', '乙公司')),
}}
ONTOLOGY = {
    'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'id': '订单号'}}], 'attributes': []},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'orders', 'identity': {'id': '客户编号'}}, {'source': 'customers', 'identity': {'id': '客户编号'}}],
         'attributes': [{'source': 'customers', 'path': '客户名称'}]},
    ],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'label': '属于', 'source': 'orders'}],
    'ignored_fields': [], 'open_questions': [],
}


class NeighbourhoodTests(unittest.TestCase):
    def test_an_object_comes_with_its_fields_and_the_objects_it_connects_to(self):
        [c1] = [i for i in find_instances(ONTOLOGY, BUNDLE, 'customer', '甲')['items']]
        self.assertEqual(c1['label'], '甲公司')   # a name-like field is shown, as a platform's display field
        g = neighbourhood(ONTOLOGY, BUNDLE, c1['id'])
        self.assertEqual(g['center']['fields'], {'客户编号': 'c1', '客户名称': '甲公司'})   # as written, not as matched
        self.assertEqual(sorted(n['label'] for n in g['nodes'] if n['type'] == 'order'), ['O1', 'O2'])
        self.assertEqual({(e['from'], e['to'], e['relation']) for e in g['edges']},
                         {(n['id'], c1['id'], 'order_customer') for n in g['nodes'] if n['type'] == 'order'})
        self.assertEqual(g['more'], [])

    def test_a_crowded_neighbourhood_shows_a_page_and_says_how_many_are_left(self):
        [c1] = find_instances(ONTOLOGY, BUNDLE, 'customer', 'c1')['items']
        g = neighbourhood(ONTOLOGY, BUNDLE, c1['id'], size=1)
        self.assertEqual(len([n for n in g['nodes'] if n['type'] == 'order']), 1)
        self.assertEqual(g['more'], [{'relation': 'order_customer', 'type': 'order', 'hidden': 1}])

    def test_search_finds_by_number_or_name_and_counts_all_matches(self):
        found = find_instances(ONTOLOGY, BUNDLE, 'order', '', size=2)
        self.assertEqual((found['total'], len(found['items'])), (3, 2))
        self.assertEqual(find_instances(ONTOLOGY, BUNDLE, 'customer', '乙')['total'], 1)
        with self.assertRaises(KeyError):
            neighbourhood(ONTOLOGY, BUNDLE, 'customer:NOPE')


class InstanceGraphServerTests(unittest.TestCase):
    def test_a_kept_run_serves_search_and_neighbourhoods(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/instances/customer?q=C1") as r:
                found = json.load(r)
            node = found['items'][0]['id']
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/graph?node={quote(node)}") as r:
                g = json.load(r)
            self.assertEqual(g['center']['id'], node)
            self.assertEqual([n['type'] for n in g['nodes'] if n['id'] != node], ['order'])
            with self.assertRaises(HTTPError) as missing:
                urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/graph?node=customer%3ANOPE")
            self.assertEqual(missing.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
