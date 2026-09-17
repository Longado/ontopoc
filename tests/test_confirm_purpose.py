import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests


class ConfirmedPurposeTests(unittest.TestCase):
    def test_a_confirmation_remembers_what_it_was_made_for(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            upload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
            _, first = call(base, '/api/ontology/build', {**upload, 'purpose': '看清哪些客户经常延期'})
            key = first['ontology']['object_types'][0]['key']
            _, confirmed = call(base, '/api/ontology/confirm', {'saved_as': first['saved_as'], 'decisions': {'types': {key: {'verdict': 'ok'}}, 'relations': {}, 'added': []}})
            _, again = call(base, '/api/ontology/build', {**upload, 'purpose': '盘点产品线'})
        self.assertEqual(confirmed['evaluation']['reference']['purpose'], '看清哪些客户经常延期')
        self.assertEqual(again['purpose'], '盘点产品线')
        self.assertEqual(again['evaluation']['reference']['purpose'], '看清哪些客户经常延期')   # the judgement was made for another purpose


if __name__ == '__main__':
    unittest.main()
