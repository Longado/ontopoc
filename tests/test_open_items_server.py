import base64
import json
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from tests.test_ontology_ask_server import call
from tests.test_ontology_server import CSV, OntologyServerTests

UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}


def fetch(base, path):
    try:
        with urlopen(base + path, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


class OpenItemsRouteTests(unittest.TestCase):
    def test_a_kept_run_lists_what_is_still_to_be_settled(self):
        with OntologyServerTests().server() as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            status, body = fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items")
            self.assertEqual(status, 200, body)
            self.assertEqual([(i['kind'], i['ask']) for i in body['items']],
                             [('unjudged', '2 个对象、1 条关系还没人判过对错。会上逐项过一遍？')])

    def test_judging_every_object_and_relation_empties_the_list(self):
        with OntologyServerTests().server() as (base, _):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            decisions = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'ok'}}, 'relations': {'order_customer': {'verdict': 'ok'}}}
            call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions})
            self.assertEqual(fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items"), (200, {'items': []}))

    def test_an_unknown_run_is_not_found(self):
        with OntologyServerTests().server() as (base, _):
            for name in ('20260101T000000Z-deadbeef.json', 'not-a-run.json'):
                with self.subTest(name=name):
                    status, body = fetch(base, f'/api/ontology/runs/{name}/open-items')
                    self.assertEqual(status, 404)
                    self.assertIn('找不到这次运行', body['error'])

    def test_an_ontology_that_did_not_pass_verification_has_an_empty_list(self):
        with OntologyServerTests().server() as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            path = out / run['saved_as']
            saved = json.loads(path.read_text(encoding='utf-8'))
            saved['ontology']['status'] = 'rejected'
            path.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(fetch(base, f"/api/ontology/runs/{run['saved_as']}/open-items"), (200, {'items': []}))


if __name__ == '__main__':
    unittest.main()
