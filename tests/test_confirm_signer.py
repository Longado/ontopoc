import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests


class ConfirmSignerTests(unittest.TestCase):
    def test_the_confirmation_records_who_confirmed_it(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            decisions = {'types': {run['ontology']['object_types'][0]['key']: {'verdict': 'ok'}}, 'relations': {}, 'added': []}
            status, confirmed = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions, 'confirmed_by': ' 信息部 王工 '})
            self.assertEqual(status, 200, confirmed)
            self.assertEqual(confirmed['confirmation']['confirmed_by'], '信息部 王工')
            self.assertEqual(confirmed['evaluation']['reference']['confirmed_by'], '信息部 王工')
            status, body = call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions, 'confirmed_by': 'x' * 41})
            self.assertEqual(status, 400)
            self.assertIn('40', body['error'])


if __name__ == '__main__':
    unittest.main()
