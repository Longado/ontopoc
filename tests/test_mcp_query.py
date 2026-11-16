"""OntoPoc Query where people and agents meet it: the `ontopoc_query` MCP tool an outside agent gets with a read token, and the query text every Q&A answer carries,
so a question asked in words can be read, checked and edited as a query. The agent is the token's person: their rows, their properties, no model."""
import json
import unittest

from ontology_poc_generator import mcp_server
from ontology_poc_generator.mcp_server import handle
from ontology_poc_generator.ontopoc_query import compile_query
from tests.test_agent_access import AgentCase
from tests.test_explorer import ORDERS
from tests.test_workspace_questions import AskModel, QUESTION, cancelled

TOP3 = 'SELECT p.品类, count(o) AS 数量 FROM (o:订单)-[:订单买的产品]->(p:产品) GROUP BY p.品类 ORDER BY 数量 DESC LIMIT 3'


def load_tests(loader, standard, pattern):
    """Only the tests written here (the agent case brings the signing tests' own)."""
    suite = unittest.TestSuite(QueryToolTests(name) for name in vars(QueryToolTests) if name.startswith('test_'))
    for cls in (QueryAgentTests, GrammarIsStandaloneTests):
        suite.addTests(cls(name) for name in vars(cls) if name.startswith('test_'))
    return suite


class Session:
    def __init__(self):
        self.sent = []

    def request(self, path, payload=None):
        self.sent.append((path, payload))
        return {'status': 'answered', 'answer': {'total': 3}, 'query': {'start': 'order'}, 'text': 'SELECT count(o) FROM (o:订单)', 'definitions': [], 'steps': [], 'datasets': {}, 'types': []}


class QueryToolTests(unittest.TestCase):
    def test_the_tool_is_a_read_tool_that_teaches_the_grammar_in_its_description(self):
        self.assertIn('ontopoc_query', mcp_server.READ_TOOLS)
        tool = {t['name']: t for t in handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}, None, only=mcp_server.READ_TOOLS)['result']['tools']}['ontopoc_query']
        self.assertEqual(tool['inputSchema']['required'], ['text'])
        for word in ('SELECT', '-[:', 'GROUP BY', '$', 'describe_definitions', '不调用模型'):
            self.assertIn(word, tool['description'])

    def test_the_tool_sends_the_text_and_the_parameters_and_returns_what_the_answer_stood_on(self):
        session = Session()
        out = mcp_server.ontopoc_query(session, {'text': 'SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who', 'params': {'who': 'KH001'}})
        self.assertEqual(session.sent, [('/api/workspace/query', {'text': 'SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who', 'params': {'who': 'KH001'}})])
        self.assertEqual((out['status'], out['answer'], out['text']), ('answered', {'total': 3}, 'SELECT count(o) FROM (o:订单)'))
        self.assertNotIn('steps', out)


class QueryAgentTests(AgentCase):
    def test_an_outside_agent_queries_as_the_token_s_person_and_a_mistake_says_what_is_there(self):
        kh = 'KH026'
        mine = [r for r in ORDERS if r['客户编号'] == kh]
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            admin = team['admin']
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': kh, 'user_ids': [ids['vera']]}]})[0], 200)
            replies = self.mcp(base, self.token_for(admin, 'vera')['token'], [
                ('ontopoc_query', {'text': 'SELECT count(o) FROM (o:订单)'}),
                ('ontopoc_query', {'text': TOP3.rsplit(' ORDER BY', 1)[0]}),   # every category: the groups add up to her orders
                ('ontopoc_query', {'text': 'SELECT count(o) FROM (o:订单)-[:下单]->(p:产品)'}),
                ('ontopoc_query', {'text': 'SELECT count(o) FROM (o:订单) WHERE o.状态码 = $state', 'params': {'state': '已取消'}})])
            self.assertIn('ontopoc_query', [t['name'] for t in replies[2]['result']['tools']])
            counted = self.payload(replies[10])
            self.assertEqual((counted['status'], counted['answer']['total']), ('answered', len(mine)))
            self.assertEqual([l['rule'] for l in counted['limited_by_rule']], [f'客户编号 = {kh}'])
            grouped = self.payload(replies[11])
            self.assertEqual(sum(g[1] for g in grouped['answer']['groups']), len(mine))
            self.assertIn('订单买的产品', [d['name'] for d in grouped['definitions']])
            wrong = replies[12]['result']
            self.assertTrue(wrong['isError'])
            self.assertIn('订单买的产品（订单→产品）', wrong['content'][0]['text'])
            cancelled_mine = self.payload(replies[13])
            self.assertEqual(cancelled_mine['answer']['total'], sum(r['状态码'] == '2' for r in mine))
            self.assertNotIn('examples', json.dumps(cancelled_mine, ensure_ascii=False))   # a viewer's token reads counts, not the objects behind them

    def test_a_q_and_a_answer_carries_its_query_as_text_that_compiles_back_to_the_same_query(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.world(team)
            status, body = team['ann'].post('/api/workspace/ask', {'question': QUESTION})
            self.assertEqual((status, body['status']), (200, 'answered'), body)
            self.assertEqual(body['query_text'], "SELECT count(o) AS 数量\nFROM (o:订单)\nWHERE o.状态码 = '2'")
            status, ran = team['ann'].post('/api/workspace/query', {'text': body['query_text']})
            self.assertEqual((status, ran['answer']['total']), (200, body['answer']['total']))
            self.assertEqual(team['ann'].get(f'/api/workspace/ask/{body["id"]}')[1]['query_text'], body['query_text'])   # kept with the answer
            # a query the text cannot say the same way (a field written as table.column by the model) is still shown, in the type's own names
            model.item = cancelled(query={'start': 'order', 'where': [{'field': '订单.状态码', 'equals': '2'}], 'via': [], 'group_by': None, 'share': None, 'measure': None})
            body = team['ann'].post('/api/workspace/ask', {'question': QUESTION})[1]
            self.assertEqual(body['query_text'], "SELECT count(o) AS 数量\nFROM (o:订单)\nWHERE o.状态码 = '2'")

    def test_an_answer_whose_query_cannot_be_written_back_has_no_query_text_rather_than_a_wrong_one(self):
        model = AskModel(cancelled(query={'start': 'order', 'where': [{'field': '不存在的列', 'equals': '2'}], 'via': [], 'group_by': None, 'share': None, 'measure': None}))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.world(team)
            body = team['ann'].post('/api/workspace/ask', {'question': QUESTION})[1]
            self.assertNotEqual(body['status'], 'answered')
            self.assertNotIn('query_text', body)


class GrammarIsStandaloneTests(unittest.TestCase):
    def test_the_language_module_imports_nothing_from_ontopoc(self):
        """It takes a catalog and gives a query: kept so that lifting it out later is copying one file (see docs/QUERY.md)."""
        import ast
        from pathlib import Path
        from ontology_poc_generator import ontopoc_query
        tree = ast.parse(Path(ontopoc_query.__file__).read_text(encoding='utf-8'))
        imported = {n.module if isinstance(n, ast.ImportFrom) else a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in getattr(n, 'names', [])}
        self.assertEqual(imported - {'__future__', 're'}, set())
        self.assertEqual(compile_query('SELECT count(x) FROM (x:t)', {'types': {'t': {'name': 'T', 'properties': []}}, 'relations': {}})['start'], 't')


if __name__ == '__main__':
    unittest.main()
