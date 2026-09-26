"""MCP clients can review a proposed formula and confirm that exact proposal over the real local HTTP service."""
import base64
import unittest

from ontology_poc_generator.mcp_server import LocalService, handle
from tests import test_derived_measures as derived_fixture
from tests import test_ontology_server as server_fixture


class DerivedRoundtripTests(unittest.TestCase):
    def tool(self, service, name, arguments):
        reply = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                        'params': {'name': name, 'arguments': arguments}}, service)['result']
        self.assertFalse(reply.get('isError'), reply)
        return reply['structuredContent']

    def test_proposed_formula_can_be_reviewed_and_confirmed_from_each_question_tool(self):
        for source in ('ask_question', 'asked_history', 'model_round'):
            with self.subTest(source=source), server_fixture.OntologyServerTests().server(gateway=derived_fixture.Model()) as (base, _):
                service = LocalService(base)
                run = service.request('/api/ontology/build', {
                    'filename': 'lines.csv', 'content_base64': base64.b64encode(derived_fixture.CSV).decode()})
                args = {'saved_as': run['saved_as']}
                asked = self.tool(service, 'ask_question', {
                    **args, **({'question': '每个客户买了多少钱？'} if source != 'model_round' else {})})
                if source == 'ask_question':
                    item = asked['items'][0]
                else:
                    questions = self.tool(service, 'list_questions', args)
                    item = questions['model_round' if source == 'model_round' else 'asked'][-1]
                self.assertEqual(item['status'], 'needs_derived')
                self.assertIn('derive', item, 'A person needs the actual formula and trial results before confirming it')
                proposal = item['derive']
                self.assertEqual(proposal['formula'], '单价 × 数量 ×（1 − 折扣）')
                self.assertEqual((proposal['preview']['counted'], proposal['preview']['skipped']), (3, 0))
                self.assertEqual(sorted(e['value'] for e in proposal['preview']['examples']), [3, 10, 20])
                self.assertEqual(proposal['preview']['skipped_examples'], [])

                # After the person reviews it, submit the returned object verbatim, without reconstructing a formula.
                self.tool(service, 'confirm_derived', {**args, 'derive': proposal})
                again = self.tool(service, 'list_questions', args)
                answered = again['model_round' if source == 'model_round' else 'asked'][-1]
                self.assertEqual(answered['status'], 'answered')
                self.assertEqual(answered['answer']['groups'], [['C1', 30, 2], ['C2', 3, 1]])
                self.assertNotIn('derive', answered, 'Ordinary answered questions retain their existing response shape')
                kept = service.run(run['saved_as'])['evaluation']['derived'][0]
                self.assertEqual(kept['terms'], proposal['terms'])
                self.assertEqual((kept['type'], kept['label']), (proposal['type'], proposal['label']))


if __name__ == '__main__':
    unittest.main()
