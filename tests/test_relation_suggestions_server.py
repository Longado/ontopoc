import base64
import json
import unittest
from urllib.request import urlopen

from ontology_poc_generator.mcp_server import handle
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests


class SuggestionServerTests(unittest.TestCase):
    def test_a_kept_run_serves_its_relation_suggestions_and_mcp_lists_the_tool(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/suggestions") as r:
                self.assertEqual(json.load(r), {'suggestions': []})   # the one relation there is already in the ontology
        tools = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']
        self.assertIn('suggest_relations', [t['name'] for t in tools])


if __name__ == '__main__':
    unittest.main()
