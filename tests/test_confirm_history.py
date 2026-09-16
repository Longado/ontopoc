import base64
import unittest

from tests.test_acceptance_server import UPLOAD
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import OntologyServerTests


class ConfirmHistoryTests(unittest.TestCase):
    def test_changing_a_confirmation_keeps_the_one_it_replaces(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', UPLOAD)
            keys = [t['key'] for t in run['ontology']['object_types']]
            for key in keys:   # two confirmations of the same file, the second judging a different object
                call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': {'types': {key: {'verdict': 'ok'}}, 'relations': {}, 'added': []}})
            kept = sorted((out / 'references' / 'history').glob('*.json'))
        self.assertEqual(len(kept), 1)
        self.assertTrue(kept[0].name.startswith(run['file']['sha256'][:8]))


if __name__ == '__main__':
    unittest.main()
