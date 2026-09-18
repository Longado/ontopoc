import unittest

from ontology_poc_generator.mcp_server import handle


class McpRuleToolTests(unittest.TestCase):
    def test_rules_can_be_read_and_adopted_through_mcp(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertIn('list_rules', tools)
        self.assertEqual(tools['set_rules']['inputSchema']['required'], ['saved_as', 'adopted'])


if __name__ == '__main__':
    unittest.main()
