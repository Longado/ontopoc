import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests


class PrefillServerTests(unittest.TestCase):
    def test_the_next_upload_of_a_confirmed_file_carries_suggested_decisions(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            upload = {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()}
            _, first = call(base, '/api/ontology/build', upload)
            key = first['ontology']['object_types'][0]['key']
            call(base, '/api/ontology/confirm', {'saved_as': first['saved_as'], 'decisions': {'types': {key: {'verdict': 'ok'}}, 'relations': {}, 'added': []}})
            _, again = call(base, '/api/ontology/build', upload)
        self.assertEqual(again['evaluation']['reference']['suggested']['types'], {key: {'verdict': 'ok'}})


if __name__ == '__main__':
    unittest.main()
