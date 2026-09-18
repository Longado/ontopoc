"""Every OntoPoc feature as a standard MCP tool: JSON-RPC over stdio, calling the same local service the page calls."""
import json
from pathlib import Path
import tempfile
import unittest

from ontology_poc_generator.mcp_server import LocalService, handle
from tests.test_ontology_ask_server import QuestionModel
from tests.test_ontology_server import CSV, OntologyServerTests


def rpc(method, params=None, id=1):
    return {'jsonrpc': '2.0', 'id': id, 'method': method, **({'params': params} if params is not None else {})}


def call(service, name, arguments):
    reply = handle(rpc('tools/call', {'name': name, 'arguments': arguments}), service)
    result = reply['result']
    return result, (json.loads(result['content'][0]['text']) if not result.get('isError') else result['content'][0]['text'])


class ProtocolTests(unittest.TestCase):
    def test_the_handshake_says_it_serves_tools(self):
        reply = handle(rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '0'}}), None)
        self.assertEqual(reply['result']['protocolVersion'], '2025-06-18')
        self.assertIn('tools', reply['result']['capabilities'])
        self.assertEqual(reply['result']['serverInfo']['name'], 'ontopoc')
        self.assertIsNone(handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, None))   # a notification gets no reply
        self.assertEqual(handle(rpc('ping'), None)['result'], {})

    def test_every_feature_is_listed_as_a_tool_with_an_object_schema(self):
        tools = handle(rpc('tools/list'), None)['result']['tools']
        names = {t['name'] for t in tools}
        for feature in ('health', 'list_runs', 'preview_upload', 'build_ontology', 'run_overview', 'list_objects', 'object_fields',
                        'object_rows', 'list_relations', 'data_layout', 'data_check', 'ask_question', 'list_questions',
                        'fix_question', 'confirm_ontology', 'compare_reference', 'find_name_variants'):
            self.assertIn(feature, names)
        for t in tools:
            self.assertEqual(t['inputSchema']['type'], 'object', t['name'])
            self.assertTrue(t['description'], t['name'])

    def test_unknown_methods_and_tools_are_refused_the_standard_way(self):
        self.assertEqual(handle(rpc('resources/list'), None)['error']['code'], -32601)
        self.assertEqual(handle(rpc('tools/call', {'name': 'nope', 'arguments': {}}), None)['error']['code'], -32602)


class EndToEndTests(unittest.TestCase):
    def test_a_client_builds_reads_asks_and_fixes_a_question_through_the_tools(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _), tempfile.TemporaryDirectory() as tmp:
            service = LocalService(base, poll_seconds=0.05)
            path = Path(tmp) / 'orders.csv'
            path.write_bytes(CSV)
            _, health = call(service, 'health', {})
            self.assertTrue(health['model_ready'])
            _, built = call(service, 'build_ontology', {'files': [str(path)], 'purpose': '看清客户和订单'})
            self.assertEqual(built['status'], 'auto_built_verified')
            run = built['saved_as']
            _, objects = call(service, 'list_objects', {'saved_as': run})
            self.assertEqual({o['key'] for o in objects['objects']}, {'order', 'customer'})
            _, rows = call(service, 'object_rows', {'saved_as': run, 'type': 'customer'})
            self.assertEqual(rows['total'], 2)
            _, asked = call(service, 'ask_question', {'saved_as': run, 'question': '哪个客户订单最多？'})
            self.assertEqual(asked['items'][0]['status'], 'answered')
            _, fixed = call(service, 'fix_question', {'saved_as': run, 'question': '哪个客户订单最多？', 'note': '按订单号数'})
            self.assertEqual([i['question'] for i in fixed['acceptance']['items']], ['哪个客户订单最多？'])
            _, runs = call(service, 'list_runs', {})
            self.assertIn(run, [r['saved_as'] for r in runs['runs']])
            result, error = call(service, 'object_rows', {'saved_as': run, 'type': 'invoice'})
            self.assertTrue(result['isError'])   # the service's own refusal comes back as a tool error, not a crash
            self.assertIn('invoice', error)


if __name__ == '__main__':
    unittest.main()
