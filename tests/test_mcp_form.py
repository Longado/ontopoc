import unittest

from ontology_poc_generator.mcp_server import handle


class McpFormToolTests(unittest.TestCase):
    def test_the_object_form_can_be_drafted_and_saved_and_exported_through_mcp(self):
        tools = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None)['result']['tools']}
        self.assertEqual(tools['draft_form']['inputSchema']['required'], ['saved_as'])
        self.assertEqual(tools['save_form']['inputSchema']['required'], ['saved_as', 'form'])
        self.assertIn('export_forms', tools)
        self.assertFalse(any('dip' in name.lower() or 'DIP' in t['description'] for name, t in tools.items()))


if __name__ == '__main__':
    unittest.main()
