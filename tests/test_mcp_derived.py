"""An agent can confirm a derived measure the way the page does, after the person agreed to it."""
import unittest

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import handle


class Session:
    def __init__(self):
        self.sent = []

    def request(self, path, payload=None):
        self.sent.append((path, payload))
        return {'saved_as': 'r.json', 'evaluation': {'derived': [{'label': '金额'}], 'asked': []}}


class DerivedToolTests(unittest.TestCase):
    def test_the_tool_sends_the_formula_to_the_service(self):
        derive = {'type': 'order_line', 'label': '金额', 'terms': [{'sign': 1, 'factors': [{'field': '单价'}]}]}
        session = Session()
        out = mcp_server.confirm_derived(session, {'saved_as': 'r.json', 'derive': derive})
        self.assertEqual(session.sent, [('/api/ontology/derived', {'saved_as': 'r.json', 'derive': derive})])
        self.assertEqual(out['derived'], [{'label': '金额'}])

    def test_it_is_listed_and_says_a_person_must_agree_first(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertEqual(tools['confirm_derived']['inputSchema']['required'], ['saved_as', 'derive'])
        self.assertIn('人', tools['confirm_derived']['description'])


if __name__ == '__main__':
    unittest.main()
