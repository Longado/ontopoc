import base64
import unittest

from tests.test_acceptance_server import UPLOAD
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import OntologyServerTests


class ClearAcceptanceTests(unittest.TestCase):
    def test_removing_the_last_question_clears_it_for_this_file(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            item = call(base, '/api/ontology/ask', {'saved_as': run['saved_as'], 'question': '每个客户有多少订单？'})[1]['evaluation']['asked'][-1]['items'][0]
            call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': [{'question': item['question'], 'query': item['query']}]})
            status, cleared = call(base, '/api/ontology/acceptance', {'saved_as': run['saved_as'], 'items': []})
            self.assertEqual(status, 200, cleared)
            self.assertNotIn('acceptance', cleared['evaluation'])
            self.assertFalse((out / 'acceptance' / f"{run['file']['sha256']}.json").exists())
            _, again = call(base, '/api/ontology/build', UPLOAD)
            self.assertNotIn('acceptance', again['evaluation'])


if __name__ == '__main__':
    unittest.main()
