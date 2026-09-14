import base64
import json
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests

UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
REFERENCE = {'object_types': [{'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'id': '订单号'}}]},
                              {'label': '发票'}],
             'relations': [{'from': '订单', 'to': '发票'}]}


class CompareServerTests(unittest.TestCase):
    def test_a_second_upload_of_the_same_file_shows_what_changed_since_the_first(self):
        helper = OntologyServerTests()
        with helper.server(gateway=QuestionModel()) as (base, _):
            _, first = call(base, '/api/ontology/build', UPLOAD)
            self.assertNotIn('previous', first)
            _, second = call(base, '/api/ontology/build', UPLOAD)
            self.assertEqual(second['previous']['saved_as'], first['saved_as'])
            diff = second['previous']['diff']
            self.assertEqual((diff['types']['only_reference'], diff['types']['only_ours']), ([], []))

    def test_a_reference_ontology_is_compared_and_saved_with_the_run(self):
        helper = OntologyServerTests()
        with helper.server(gateway=QuestionModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            status, updated = call(base, '/api/ontology/compare', {'saved_as': run['saved_as'], 'reference': REFERENCE, 'reference_name': 'ref.json'})
            self.assertEqual(status, 200, updated)
            ref = updated['evaluation']['reference']
            self.assertEqual(ref['name'], 'ref.json')
            self.assertEqual(ref['diff']['types']['matched'], [['订单', '订单']])
            self.assertEqual(ref['diff']['types']['only_reference'], ['发票'])
            self.assertIn('reference', json.loads((out / run['saved_as']).read_text(encoding='utf-8'))['evaluation'])
            status, body = call(base, '/api/ontology/compare', {'saved_as': run['saved_as'], 'reference': {'object_types': []}})
            self.assertEqual(status, 400)
            self.assertIn('object_types', body['error'])


if __name__ == '__main__':
    unittest.main()
