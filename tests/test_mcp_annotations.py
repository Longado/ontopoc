"""MCP tool annotations (spec 2025-03-26 and later: title, readOnlyHint, destructiveHint, idempotentHint, openWorldHint), and that no tool needs a route a token is refused."""
import re
import unittest
from pathlib import Path

from ontology_poc_generator import mcp_server
from ontology_poc_generator.access import PERSON_ONLY_POSTS
from ontology_poc_generator.mcp_server import READ_TOOLS, TOOLS, handle

HINTS = ('readOnlyHint', 'destructiveHint', 'idempotentHint', 'openWorldHint')
# what only reads: the team's read tools but `ask`, which keeps the question in the history and counts against the ask budget, and the early screen's readers
READ_ONLY = {'describe_definitions', 'ontopoc_query', 'list_unconfirmed', 'read_derived_property', 'definition_standing',
             'health', 'list_runs', 'preview_upload', 'run_overview', 'list_objects', 'object_fields', 'object_rows', 'list_relations', 'suggest_relations',
             'find_instances', 'instance_neighbourhood', 'list_rules', 'data_layout', 'data_check', 'list_questions', 'get_card', 'list_proposed_views'}


def listed(only=None):
    return {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None, only=only)['result']['tools']}


class AnnotationTests(unittest.TestCase):
    def test_every_tool_carries_a_title_and_all_four_hints(self):
        tools = listed()
        self.assertEqual(len(tools), len(TOOLS))
        for name, t in tools.items():
            a = t.get('annotations')
            self.assertIsInstance(a, dict, name)
            self.assertIsInstance(a.get('title'), str, name)
            self.assertTrue(a['title'].strip(), name)
            for hint in HINTS:
                self.assertIsInstance(a.get(hint), bool, (name, hint))
        titles = [t['annotations']['title'] for t in tools.values()]
        self.assertEqual(len(set(titles)), len(titles))

    def test_the_read_set_is_the_read_tools_but_ask_and_the_early_screens_readers(self):
        tools = listed()
        read = {name for name, t in tools.items() if t['annotations']['readOnlyHint']}
        self.assertEqual(read, READ_ONLY)
        self.assertEqual(set(READ_TOOLS) - read, {'ask'})
        ask = tools['ask']['annotations']
        self.assertEqual((ask['readOnlyHint'], ask['destructiveHint'], ask['idempotentHint']), (False, False, False))   # it adds a question to the history, removes nothing
        for name in read:
            self.assertFalse(tools[name]['annotations']['destructiveHint'], name)
        for name in READ_TOOLS:   # what an outside agent is given: nothing in it can take anything away
            self.assertFalse(tools[name]['annotations']['destructiveHint'], name)

    def test_writers_that_replace_or_delete_say_so(self):
        tools = listed()
        for name in ('set_rules', 'save_form', 'save_card', 'confirm_ontology', 'fix_question', 'confirm_derived', 'compare_reference',
                     'export_forms', 'export_ttl', 'export_mermaid', 'export_pipeline_spec'):
            a = tools[name]['annotations']
            self.assertEqual((a['readOnlyHint'], a['destructiveHint']), (False, True), name)
        for name in ('build_ontology', 'ask_question', 'drop_filter', 'confirm_proposed_view'):
            a = tools[name]['annotations']
            self.assertEqual((a['readOnlyHint'], a['destructiveHint']), (False, False), name)

    def test_the_read_toolset_lists_annotations_too(self):
        for t in listed(READ_TOOLS).values():
            self.assertIn('annotations', t)

    def test_the_protocol_version_offered_first_has_annotations(self):
        self.assertGreaterEqual(mcp_server.PROTOCOL_VERSIONS[0], '2025-03-26')
        reply = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-03-26'}}, None)
        self.assertEqual(reply['result']['protocolVersion'], '2025-03-26')


class NoToolNeedsAPersonOnlyRouteTests(unittest.TestCase):
    def test_no_tool_calls_a_route_a_token_is_refused(self):
        """The three confirming tools work on one run of the early screen (/api/ontology/...), which D17 leaves as it was."""
        source = Path(mcp_server.__file__).read_text(encoding='utf-8')
        paths = set(re.findall(r"""['"](/api/[A-Za-z0-9_/-]*)""", source))
        self.assertTrue(paths)
        self.assertEqual(paths & set(PERSON_ONLY_POSTS), set())

        class Recorder:
            token, poll_seconds = 'otp_x', 0

            def __init__(self):
                self.calls = []

            def request(self, path, payload=None):
                self.calls.append(path)
                raise mcp_server.ToolError('refused', 403)

        for name, arguments in (('confirm_ontology', {'saved_as': 'a.json', 'decisions': {}}), ('confirm_derived', {'saved_as': 'a.json', 'derive': {}}),
                                ('confirm_proposed_view', {'saved_as': 'a.json', 'name': 'v', 'version': 1})):
            service = Recorder()
            reply = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}, service)
            self.assertTrue(reply['result']['isError'], name)
            self.assertEqual(reply['result']['content'][0]['text'], 'refused')   # a refusal comes back as the service's sentence, no trace
            self.assertTrue(all(p.startswith('/api/ontology/') for p in service.calls), (name, service.calls))


if __name__ == '__main__':
    unittest.main()
