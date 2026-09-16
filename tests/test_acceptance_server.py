import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests

UPLOAD = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}


class AcceptanceServerTests(unittest.TestCase):
    def test_saved_questions_are_rerun_on_the_next_upload_of_the_same_file(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, first = call(base, '/api/ontology/build', UPLOAD)
            asked = call(base, '/api/ontology/ask', {'saved_as': first['saved_as'], 'question': '每个客户有多少订单？'})[1]
            item = asked['evaluation']['asked'][-1]['items'][0]
            status, saved = call(base, '/api/ontology/acceptance', {'saved_as': first['saved_as'],
                                                                    'items': [{'question': item['question'], 'query': item['query'], 'note': '按订单号计数'}]})
            self.assertEqual(status, 200, saved)
            self.assertEqual(saved['evaluation']['acceptance']['items'][0]['note'], '按订单号计数')
            self.assertEqual(saved['evaluation']['acceptance']['answered'], 1)
            self.assertTrue((out / 'acceptance').is_dir())
            _, again = call(base, '/api/ontology/build', UPLOAD)
            rerun = again['evaluation']['acceptance']
            self.assertEqual(rerun['total'], 1)
            self.assertIs(rerun['items'][0]['changed'], False)
            status, body = call(base, '/api/ontology/acceptance', {'saved_as': first['saved_as'], 'items': [{'question': 'x'}]})
            self.assertEqual(status, 400)
            self.assertIn('查询', body['error'])


if __name__ == '__main__':
    unittest.main()
