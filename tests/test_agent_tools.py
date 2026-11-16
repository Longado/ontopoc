"""The read tools an outside agent gets, held to five rules for tools a model calls: few tools that do not overlap (each says when to use it, and numbers
go to the query tool before the model-backed one), purpose-built, cheap in tokens (no field said twice, long lists cut with a way to narrow them), errors
that say the fix, and safe to retry (each says whether calling it again changes anything)."""
import json
import unittest

from ontology_poc_generator import mcp_server
from ontology_poc_generator.agent_access import REFUSAL_RULES
from ontology_poc_generator.mcp_server import ToolError, handle
from ontology_poc_generator.ontopoc_query import QueryError, compile_query
from tests.test_agent_access import AgentCase
from tests.test_workspace_questions import AskModel, cancelled


def load_tests(loader, standard, pattern):
    suite = unittest.TestSuite()
    for cls in (RoutingTests, LeanOutputTests, DefinitionsTests, TeachingErrorTests, SizeTests):
        suite.addTests(cls(name) for name in vars(cls) if name.startswith('test_'))
    return suite


def tools():
    return {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None, only=mcp_server.READ_TOOLS)['result']['tools']}


def used(state='confirmed', **more):
    return {'id': 'objtype:order', 'kind': 'type', 'name': '订单', 'state': state, 'version': 2, 'confirmed_by': 'Bob', 'confirmed_at': '2026-11-16T06:37:23+00:00', **more}


class Session:
    def __init__(self, body):
        self.body, self.sent = body, []

    def request(self, path, payload=None):
        self.sent.append((path, payload))
        return self.body


class RoutingTests(unittest.TestCase):
    def test_numbers_go_to_the_query_tool_first_and_the_model_backed_tool_says_when_it_is_the_one(self):
        t = tools()
        self.assertIn('ontopoc_query', mcp_server.READ_INSTRUCTIONS)
        self.assertLess(mcp_server.READ_INSTRUCTIONS.index('ontopoc_query'), mcp_server.READ_INSTRUCTIONS.index('ask'))
        self.assertIn('ontopoc_query', REFUSAL_RULES[-1])   # the rule an agent reads with the definitions names the tool for numbers
        self.assertIn('ontopoc_query', t['ask']['description'])   # ask says it is for what the agent cannot write as a query
        self.assertIn('写不出', t['ask']['description'])

    def test_each_tool_says_whether_calling_it_again_changes_anything(self):
        t = tools()
        for name in ('describe_definitions', 'ontopoc_query', 'list_unconfirmed', 'read_derived_property'):
            self.assertIn('可以重试', t[name]['description'], name)
        self.assertIn('每问一次', t['ask']['description'])   # it is kept in the Q&A history and spends the asker's budget
        self.assertIn('可以重试', mcp_server.READ_INSTRUCTIONS)


class LeanOutputTests(unittest.TestCase):
    def test_a_query_result_says_each_thing_once(self):
        body = {'status': 'answered', 'answer': {'total': 3}, 'text': 'SELECT count(o) AS 数量\nFROM (o:订单)', 'query': {'start': 'order', 'where': []},
                'definitions': [used(), used('needs_review', id='enum:order:状态码', kind='meaning', name='订单.状态码')], 'datasets': {'订单': 1}}
        out = mcp_server.ontopoc_query(Session(body), {'text': 'SELECT count(o) FROM (o:订单)'})
        self.assertNotIn('query', out)   # the text compiles to it: one of the two is enough
        self.assertEqual(out['definitions'][0], {'id': 'objtype:order', 'kind': 'type', 'name': '订单', 'version': 2, 'confirmed_by': 'Bob'})
        self.assertEqual(out['definitions'][1]['state'], 'needs_review')   # a state is said only where it is not the usual one

    def test_an_answer_from_ask_is_as_lean(self):
        body = {'id': 4, 'question': 'q', 'status': 'answered', 'answer': {'total': 3}, 'definitions': [used()], 'query_text': 'SELECT count(o) AS 数量\nFROM (o:订单)'}
        out = mcp_server.ask(Session(body), {'question': 'q'})
        self.assertEqual(out['definitions'], [{'id': 'objtype:order', 'kind': 'type', 'name': '订单', 'version': 2, 'confirmed_by': 'Bob'}])
        self.assertEqual(out['query_text'], body['query_text'])   # so the agent can rerun or change it with ontopoc_query, without the model

    def test_a_derived_property_keeps_its_formula_and_a_refusal_keeps_its_states(self):
        line = used(id='derived:customer:cancelled_orders', kind='derived', name='客户.已取消订单数', type='customer', says='每个客户的已取消订单数')
        out = mcp_server.ontopoc_query(Session({'status': 'answered', 'answer': {'total': 1}, 'text': 'x', 'definitions': [line]}), {'text': 'x'})
        self.assertEqual(out['definitions'][0]['says'], '每个客户的已取消订单数')   # a number is reported with its basis (refusal rule 4): the formula is part of it
        refusal = {'status': 'refused', 'reason': 'r', 'refusal': {'kind': 'unconfirmed', 'definitions': [used('needs_review')]}, 'definitions': [used('needs_review')]}
        out = mcp_server.ask(Session(refusal), {'question': 'q'})
        self.assertEqual(out['refusal'], refusal['refusal'])
        self.assertEqual(out['definitions'][0]['state'], 'needs_review')

    def test_an_ask_answer_cut_says_to_narrow_its_query_text_with_ontopoc_query(self):
        groups = [[f'客户{i:03d}', i] for i in range(60)]
        body = {'status': 'answered', 'answer': {'groups': groups, 'total_groups': 60}, 'query_text': 'SELECT …', 'definitions': []}
        self.assertIn('query_text', mcp_server.ask(Session(body), {'question': 'q'})['answer']['groups_cut'])

    def test_a_long_list_of_groups_is_cut_with_the_count_kept_and_a_way_to_narrow_it(self):
        groups = [[f'客户{i:03d}', i] for i in range(120)]
        body = {'status': 'answered', 'answer': {'groups': groups, 'total_groups': 120, 'without_value': 0}, 'text': 'x', 'definitions': []}
        out = mcp_server.ontopoc_query(Session(body), {'text': 'x'})
        self.assertEqual(out['answer']['groups'], groups[:mcp_server.AGENT_GROUPS])
        self.assertEqual(out['answer']['total_groups'], 120)
        self.assertIn('LIMIT', out['answer']['groups_cut'])
        short = mcp_server.ontopoc_query(Session({**body, 'answer': {'groups': groups[:5], 'total_groups': 5}}), {'text': 'x'})
        self.assertNotIn('groups_cut', short['answer'])


class DefinitionsTests(unittest.TestCase):
    BODY = {'types': [{'id': 'order', 'name': '订单', 'properties': [{'column': '订单号', 'name': '订单号', 'type': 'text', 'code': False},
                                                                   {'column': 'status', 'name': '状态码', 'type': 'integer', 'code': True}], 'meanings': {}},
                      {'id': 'customer', 'name': '客户', 'properties': [], 'meanings': {}},
                      {'id': 'stock', 'name': '库存', 'properties': [], 'meanings': {}}],
            'relations': [{'id': 'order_customer', 'name': '订单属于客户', 'from': 'order', 'to': 'customer'}, {'id': 'stock_x', 'name': '库存', 'from': 'stock', 'to': 'stock'}],
            'views': [{'id': '有效订单', 'type': 'order'}, {'id': '安全库存', 'type': 'stock'}],
            'derived': [{'id': 'cancelled_orders', 'type': 'customer'}, {'id': 'x', 'type': 'stock'}], 'rules': ['r']}

    def test_a_property_says_only_what_is_not_already_said(self):
        out = mcp_server.describe_definitions(Session(json.loads(json.dumps(self.BODY))), {})
        self.assertEqual(out['types'][0]['properties'], [{'column': '订单号', 'type': 'text'}, {'column': 'status', 'name': '状态码', 'type': 'integer', 'code': True}])

    def test_some_types_by_id_or_name_bring_their_relations_views_and_derived_and_always_the_rules(self):
        session = Session(json.loads(json.dumps(self.BODY)))
        out = mcp_server.describe_definitions(session, {'types': ['order', '客户']})
        self.assertEqual([t['id'] for t in out['types']], ['order', 'customer'])
        self.assertEqual([r['id'] for r in out['relations']], ['order_customer'])
        self.assertEqual([v['id'] for v in out['views']], ['有效订单'])
        self.assertEqual([d['id'] for d in out['derived']], ['cancelled_orders'])
        self.assertEqual(out['rules'], ['r'])
        self.assertIn('types', tools()['describe_definitions']['inputSchema']['properties'])

    def test_an_empty_or_odd_types_filter_is_an_error_not_an_empty_answer(self):
        for odd in ([], {'order': 1}, [1]):
            with self.assertRaises(ToolError, msg=odd):
                mcp_server.describe_definitions(Session(json.loads(json.dumps(self.BODY))), {'types': odd})
        one = mcp_server.describe_definitions(Session(json.loads(json.dumps(self.BODY))), {'types': '订单'})   # one name on its own is read as a list of one
        self.assertEqual([t['id'] for t in one['types']], ['order'])

    def test_a_type_that_is_not_there_is_named_with_the_ones_that_are(self):
        with self.assertRaises(ToolError) as caught:
            mcp_server.describe_definitions(Session(json.loads(json.dumps(self.BODY))), {'types': ['发票']})
        self.assertIn('发票', str(caught.exception))
        self.assertIn('订单（order）', str(caught.exception))


class TeachingErrorTests(unittest.TestCase):
    def test_a_missing_parameter_says_how_to_pass_it(self):
        catalog = {'types': {'order': {'name': '订单', 'properties': ['客户编号']}}, 'relations': {}}
        with self.assertRaises(QueryError) as caught:
            compile_query('SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who', catalog)
        self.assertIn('"params": {"who":', str(caught.exception))


class SizeTests(AgentCase):
    def test_what_an_agent_reads_for_a_count_and_for_the_definitions_stays_small(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            replies = self.mcp(base, self.token_for(team['admin'], 'ann')['token'], [('ontopoc_query', {'text': 'SELECT count(o) FROM (o:订单)'}), ('describe_definitions', {}),
                                                                                     ('describe_definitions', {'types': ['订单']})])
            size = lambda r: len(json.dumps(self.payload(r), ensure_ascii=False))
            self.assertLess(size(replies[10]), 250)   # was 424: the compiled query and the confirmation times are gone
            self.assertLess(size(replies[11]), 3900)   # was 4,620 on this world; the rest is who confirmed what and the refusal rules, which stay
            self.assertLess(size(replies[12]), size(replies[11]) * 2 // 3)


if __name__ == '__main__':
    unittest.main()
