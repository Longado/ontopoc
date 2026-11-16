"""R10 step 5: SELECT GRAPH. A query can ask for the objects themselves and how they are related, instead of a number: the start objects that match its
WHERE (at most LIMIT of them, 20 when it says none), and every object each FROM path reaches from them, with the edges between. It is read through the same
scope as any query: the asker's rows, their properties (a hidden name-like column is not shown on a node), confirmed definitions only. A viewer reads
numbers, not objects, so a graph is refused for them; a board card and the Q&A model write numbers too."""
import unittest

from ontology_poc_generator.ontopoc_query import QueryError, compile_query, is_graph, to_text
from tests.test_ontopoc_query import CATALOG, q
from tests.test_query_value import ORDERS, QueryCase, mended_customers

CANCELLED_GRAPH = "SELECT GRAPH FROM (o:订单)-[:订单属于客户]->(c:客户) WHERE o.状态码 = '已取消'"


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(cls(name) for cls in (GraphGrammarTests, GraphServiceTests) for name in vars(cls) if name.startswith('test_'))


class GraphGrammarTests(unittest.TestCase):
    def test_select_graph_compiles_to_the_start_its_conditions_and_the_paths_it_draws(self):
        text = "SELECT GRAPH FROM (o:订单)-[:订单属于客户]->(c:客户), (o)<-[:工单属于订单]-(t:售后工单) WHERE o.状态码 = '已取消' LIMIT 5"
        self.assertEqual(compile_query(text, CATALOG), {**q(start='order', where=[{'field': '状态码', 'equals': '已取消'}], top=5),
                                                        'graph': [['order_customer'], ['ticket_order']]})
        self.assertEqual(compile_query('select graph from (c:客户)', CATALOG), {**q(start='customer'), 'graph': []})
        self.assertTrue(is_graph(text))
        self.assertFalse(is_graph('SELECT count(o) FROM (o:订单)'))
        self.assertFalse(is_graph('SELECT o.GRAPH, count(o) FROM (o:订单) GROUP BY o.GRAPH'))

    def test_a_graph_query_writes_back_as_the_same_text(self):
        for text in (CANCELLED_GRAPH, "SELECT GRAPH FROM (t:售后工单)-[:工单属于订单]->(o:订单)-[:订单属于客户]->(c:客户) LIMIT 3", 'SELECT GRAPH FROM (c:客户)'):
            compiled = compile_query(text, CATALOG)
            self.assertEqual(compile_query(to_text(compiled, CATALOG), CATALOG), compiled, text)
        self.assertTrue(to_text(compile_query(CANCELLED_GRAPH, CATALOG), CATALOG).startswith('SELECT GRAPH\nFROM (o:订单)-[:订单属于客户]->(c:客户)'))

    def test_what_a_graph_cannot_say_is_refused_in_words(self):
        for text, said in (('SELECT GRAPH FROM (o:订单)-[:订单属于客户]->(c:客户) GROUP BY c.客户名称', 'GROUP BY'),
                           ('SELECT GRAPH FROM (o:订单) ORDER BY 数量 DESC', 'ORDER BY'),
                           ('SELECT GRAPH, count(o) FROM (o:订单)', 'GRAPH'),
                           ("SELECT GRAPH FROM (o:订单)-[:订单属于客户]->(c:客户) WHERE c.城市 = '苏州'", '条件只能写在'),
                           ('SELECT GRAPH FROM (o:订单) LIMIT 101', '100'),
                           ('SELECT GRAPH FROM (o:订单), (c:客户)', '连在一起')):
            with self.assertRaises(QueryError, msg=text) as caught:
                compile_query(text, CATALOG)
            self.assertIn(said, str(caught.exception), text)


class GraphServiceTests(QueryCase):
    def graph(self, client, text=CANCELLED_GRAPH):
        status, body = self.query(client, text)
        self.assertEqual(status, 200, body)
        return body

    def test_the_cancelled_orders_are_drawn_with_the_customers_they_belong_to(self):
        cancelled = [r for r in ORDERS if r['状态码'] == '2']
        names = {r['客户编号']: r['客户名称'] for r in mended_customers()}
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            body = self.graph(team['ann'])
            self.assertEqual(body['status'], 'answered', body)
            g = body['answer']['graph']
            self.assertEqual((g['starts'], g['shown'], g['cut']), (len(cancelled), len(cancelled), False))   # 16 cancelled orders, under the 20 drawn by default
            orders = [n for n in g['nodes'] if n['type'] == 'order']
            customers = {n['id']: n for n in g['nodes'] if n['type'] == 'customer'}
            self.assertEqual(sorted(n['key'] for n in orders), sorted(r['订单号'] for r in cancelled))
            self.assertTrue(all(n['start'] for n in orders) and not any(n['start'] for n in customers.values()))
            known = [r for r in cancelled if r['客户编号'] in names]   # an order naming a customer the customer table lacks (KH099) reaches no customer
            self.assertLess(len(known), len(cancelled))
            self.assertEqual({n['name'] for n in customers.values()}, {names[r['客户编号']] for r in known})
            self.assertEqual(len(g['edges']), len(known))   # each order belongs to one customer
            by_id = {n['id']: n for n in g['nodes']}
            for e in g['edges']:
                self.assertEqual((by_id[e['from']]['type'], by_id[e['to']]['type'], e['name']), ('order', 'customer', '订单属于客户'))
            self.assertEqual(sorted((d['kind'], d['name']) for d in body['definitions']),
                             [('meaning', '订单.状态码'), ('relation', '订单属于客户'), ('type', '客户'), ('type', '订单')])
            self.assertTrue(body['text'].startswith('SELECT GRAPH'))
            self.assertIn(f'画出全部 {len(cancelled)} 个', body['path'])   # found in the review of PR #88: every one drawn is not "the first 16"
            # LIMIT keeps the first start objects and says how many there were
            few = self.graph(team['ann'], CANCELLED_GRAPH + ' LIMIT 3')['answer']['graph']
            self.assertEqual((few['starts'], few['shown'], sum(n['start'] for n in few['nodes'])), (len(cancelled), 3, 3))
            self.assertIn('画出前 3 个', self.graph(team['ann'], CANCELLED_GRAPH + ' LIMIT 3')['path'])

    def test_a_viewer_is_told_a_graph_is_for_builders_and_sees_no_object(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            status, body = self.query(team['vera'], CANCELLED_GRAPH)
            self.assertEqual(status, 403, body)
            self.assertNotIn('nodes', str(body))

    def test_a_row_rule_and_a_hidden_column_hold_on_the_graph(self):
        mine = [r for r in ORDERS if r['客户编号'] == 'KH001']
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            admin, carl = team['admin'], team['carl']
            carl_id = self.user_id(admin, 'carl')
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [carl_id]}]})[0], 200)
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'customer', 'column': '客户名称', 'visible_to': [self.user_id(admin, 'ann')]})[0], 200)
            body = self.graph(carl, 'SELECT GRAPH FROM (o:订单)-[:订单属于客户]->(c:客户)')
            g = body['answer']['graph']
            self.assertEqual(sorted(n['key'] for n in g['nodes'] if n['type'] == 'order'), sorted(r['订单号'] for r in mine))
            self.assertEqual([n['key'] for n in g['nodes'] if n['type'] == 'customer'], ['KH001'])
            name = next(r['客户名称'] for r in mended_customers() if r['客户编号'] == 'KH001')
            self.assertNotIn(name, str(body))   # 客户名称 is kept from Carl: the node shows the key only
            self.assertEqual(body['limited_by_rule'], [{'type': 'order', 'name': '订单', 'rule': '客户编号 = KH001'}])

    def test_no_object_matching_is_no_data_not_an_empty_answer(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            body = self.graph(team['ann'], "SELECT GRAPH FROM (o:订单) WHERE o.订单号 = 'NOPE'")
            self.assertEqual(body['status'], 'no_data', body)

    def test_a_board_card_cannot_hold_a_graph(self):
        with self.service(gateway=None) as (base, out):
            team = self.team(base)
            status, body = team['ann'].post('/api/workspace/dashboards', {'name': '图', 'spec': {'components': [{'id': 'c1', 'title': '已取消', 'text': CANCELLED_GRAPH, 'chart': {'kind': 'query'}}], 'filters': [], 'params': []}})
            self.assertEqual(status, 400, body)
            self.assertIn('SELECT GRAPH', body['error'])
