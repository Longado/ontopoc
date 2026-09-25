"""Saving the same judgement again — an agent retrying a call, a double click — is the same confirmation, not a new
one: no second history entry and the time it was confirmed stays. A changed judgement still replaces the old one and
keeps it in the history."""
import base64
import unittest

from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests

FIRST = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'ok'}}, 'relations': {'order_customer': {'verdict': 'ok'}}}
CHANGED = {'types': {'order': {'verdict': 'ok'}, 'customer': {'verdict': 'wrong'}}, 'relations': {}}


class RepeatTests(unittest.TestCase):
    def test_the_same_judgement_twice_is_one_confirmation(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, out):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            confirm = lambda decisions: call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'decisions': decisions})
            status, first = confirm(FIRST)
            self.assertEqual(status, 200, first)
            status, again = confirm(FIRST)
            self.assertEqual(status, 200, again)
            history = out / 'references' / 'history'
            self.assertEqual(again['confirmation']['confirmed_at'], first['confirmation']['confirmed_at'])
            self.assertEqual(len(list(history.glob('*.json'))) if history.exists() else 0, 0)
            status, changed = confirm(CHANGED)
            self.assertEqual(status, 200, changed)
            self.assertEqual(len(list(history.glob('*.json'))), 1)   # the first judgement, kept


if __name__ == '__main__':
    unittest.main()
