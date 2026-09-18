import base64
import json
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests


def get(base, path):
    try:
        with urlopen(base + path, timeout=30) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


class RunLibraryTests(unittest.TestCase):
    def test_every_saved_run_is_listed_newest_first_and_can_be_opened_again(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            upload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
            _, first = call(base, '/api/ontology/build', {**upload, 'purpose': '看清订单'})
            _, second = call(base, '/api/ontology/build', {**upload, 'purpose': '看清客户'})
            (out / 'references').mkdir(exist_ok=True)   # other files the service keeps beside the runs are not runs
            status, listed = get(base, '/api/ontology/runs')
            self.assertEqual(status, 200)
            self.assertEqual([r['saved_as'] for r in listed['runs']], [second['saved_as'], first['saved_as']])
            entry = listed['runs'][0]
            self.assertEqual((entry['file'], entry['purpose'], entry['status']), ('orders.csv', '看清客户', second['ontology']['status']))
            self.assertEqual((entry['types'], entry['relations']), (len(second['ontology']['object_types']), len(second['ontology']['relations'])))
            self.assertFalse(entry['confirmed'])
            status, opened = get(base, f'/api/ontology/runs/{first["saved_as"]}')
            self.assertEqual((status, opened['saved_as'], opened['purpose']), (200, first['saved_as'], '看清订单'))

    def test_a_name_the_service_did_not_save_is_refused(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            for name in ('../secret.json', 'orders.csv', '20260918T000000000Z-deadbeef.json'):
                with self.subTest(name=name):
                    status, body = get(base, f'/api/ontology/runs/{name}')
                    self.assertEqual(status, 404)
                    self.assertIn('error', body)


if __name__ == '__main__':
    unittest.main()
