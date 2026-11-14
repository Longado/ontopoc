"""The relation graph and the lineage graph, read through the real service on the planted tables: types as nodes, relations as edges with the rows they connect,
the lineage from a dataset version to the types, views and saved answers that stand on it, the stale causes in words, and what a limited person or a viewer does
not get. Expected numbers are the planted ones (160 orders, 157 of them naming a customer the customer table has) counted from the records in the tests that
set them up, not from the service."""
import json

from ontology_poc_generator.ontology_graph import _own_cause
from tests.test_object_relations import CUSTOMER, RELATION, customers_mended
from tests.test_object_types import MEANINGS, ORDER, TABLES, VALID, shifted_orders_csv
from tests.test_two_person import SigningTestCase
from tests.test_workspace_questions import AskModel, cancelled

RELATIONS = '/api/workspace/graph/relations'
LINEAGE = '/api/workspace/graph/lineage'


def numbers_in(value) -> list:
    """Every number anywhere in a JSON value."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [value]
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in(v)]
    if isinstance(value, list):
        return [n for v in value for n in numbers_in(v)]
    return []


class GraphTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def confirm_type(self, client, name, column=None):
        shown = client.get(f'/api/workspace/types/{name}')[1]
        shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
        status, body = client.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})
        self.assertEqual(status, 200, body)

    def everything_confirmed(self, team):
        """订单 and 客户 as types, 订单 → 客户 as a relation (the customer table with KH012 once), and the view 有效订单: put forward by Ann, confirmed by Bob."""
        ann, bob = team['ann'], team['bob']
        for payload in (ORDER, CUSTOMER):
            self.assertEqual(ann.post('/api/workspace/types', payload)[0], 200)
        self.assertEqual(ann.post('/api/workspace/relations', RELATION)[0], 200)
        self.confirm_type(bob, 'order', '状态码')
        self.confirm_type(bob, 'order')
        self.confirm_type(bob, 'customer')
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
        detail = bob.get('/api/workspace/relations/order_customer')[1]
        status, body = bob.post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': detail['version'], 'seen': detail['check']['signature']})
        self.assertEqual(status, 200, body)
        self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
        view = next(v for v in bob.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '有效订单')
        self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': view['version'], 'seen': view['seen']})[0], 200)

    def graph(self, client, path):
        status, body = client.get(path)
        self.assertEqual(status, 200, body)
        return body

    @staticmethod
    def node(graph, element_id):
        return next(n for n in graph['nodes'] if n['id'] == element_id)

    def test_the_relation_graph_has_the_types_as_nodes_and_the_edge_says_157_of_160_rows_connect_and_the_arrow_points_to_the_one_side(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            for payload in (ORDER, CUSTOMER):
                self.assertEqual(ann.post('/api/workspace/types', payload)[0], 200)
            self.assertEqual(ann.post('/api/workspace/relations', RELATION)[0], 200)
            # the customer table has KH012 twice: many-to-one does not hold, and the edge says so (dashed on the page) with the counts and no key
            graph = self.graph(ann, RELATIONS)
            self.assertEqual([(n['id'], n['name'], n['objects'], n['state']) for n in graph['nodes']], [('objtype:customer', '客户', 31, 'checked'), ('objtype:order', '订单', 160, 'checked')])
            (edge,) = graph['edges']
            self.assertEqual((edge['key'], edge['from'], edge['to'], edge['arrow_to'], edge['cardinality']), ('order_customer', 'objtype:order', 'objtype:customer', 'objtype:customer', 'many_to_one'))
            self.assertEqual((edge['connected'], edge['of'], edge['unmatched'], edge['cardinality_ok']), (157, 160, 3, False))
            self.assertIn('客户编号', edge['cardinality_text'])
            self.assertNotIn('KH012', json.dumps(edge, ensure_ascii=False))
            # mended: the same rows connect, the cardinality holds
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
            (edge,) = self.graph(ann, RELATIONS)['edges']
            self.assertEqual((edge['connected'], edge['of'], edge['cardinality_ok'], edge['cardinality_text']), (157, 160, True, None))

    def test_the_lineage_shows_the_shifted_upload_as_the_data_cause_on_the_meaning_and_as_the_step_before_on_what_reads_it(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.everything_confirmed(team)
            self.assertEqual(ann.post('/api/workspace/ask', {'question': '取消的订单有多少？'})[1]['status'], 'answered')
            graph = self.graph(ann, LINEAGE)
            kinds = {n['id']: n['kind'] for n in graph['nodes']}
            self.assertEqual(kinds['dataset:订单'], 'dataset')
            self.assertEqual({k for k in kinds.values()}, {'dataset', 'type', 'relation', 'view', 'answer'})
            dataset = self.node(graph, 'dataset:订单')
            self.assertEqual((dataset['version'], dataset['used_for'], dataset['stale']), (1, ['订单'], None))
            self.assertTrue(dataset['uploaded_at'])
            edges = {(e['from'], e['to']) for e in graph['edges']}
            self.assertLessEqual({('dataset:订单', 'objtype:order'), ('dataset:客户', 'objtype:customer'), ('objtype:order', 'objview:有效订单'), ('objtype:order', 'relation:order_customer'),
                                  ('objtype:customer', 'relation:order_customer')}, edges)
            answer = next(n for n in graph['nodes'] if n['kind'] == 'answer')
            self.assertIn(('objtype:order', answer['id']), edges)
            self.assertTrue(all(n['state'] in ('confirmed', None) for n in graph['nodes']))
            self.assertIsNone(answer['state'])   # nobody confirmed the answer: it has no state to be drawn green
            # the codes shift by one in a new version of 订单
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            graph = self.graph(ann, LINEAGE)
            self.assertEqual(self.node(graph, 'dataset:订单')['version'], 2)
            order, view = self.node(graph, 'objtype:order'), self.node(graph, 'objview:有效订单')
            # the type's own dataset moved and its own meanings changed under it: the cause is the data's, in short words on the node, never "the step before"
            self.assertEqual(order['state'], 'needs_look')
            self.assertEqual((order['stale']['cause'], order['stale']['label'], order['stale']['root_cause']), ('data', '数据变了', 'data'))
            self.assertEqual(order['stale']['short'], '订单 第 2 版 状态码 取值变了')
            self.assertEqual(order['stale']['root'], '“状态码”的含义')
            self.assertIn('订单 第 2 版', order['stale']['text'])
            self.assertIn('“状态码”的取值变了', order['stale']['text'])
            # what reads the type or the meaning, and whose own inputs did not change, is one step behind it, with the same words
            for node in (view, self.node(graph, 'relation:order_customer')):
                self.assertEqual((node['state'], node['stale']['cause'], node['stale']['label'], node['stale']['root_cause']), ('needs_look', 'upstream', '上一步过时', 'data'))
                self.assertEqual(node['stale']['root'], '“状态码”的含义')
                self.assertIn('“状态码”的取值变了', node['stale']['text'])
            answer = next(n for n in graph['nodes'] if n['kind'] == 'answer')
            self.assertEqual((answer['state'], answer['stale']['cause']), ('needs_look', 'upstream'))
            customer = self.node(graph, 'objtype:customer')
            self.assertEqual((customer['state'], customer['stale']), ('confirmed', None))
            # the drawer of the type: who confirmed it on which version, and what stands on it
            self.assertEqual((order['confirmed_by'], order['confirmed_on']), ('Bob', {'订单': 1}))
            self.assertEqual([v['name'] for v in order['views']], ['有效订单'])
            self.assertEqual(order['answers'], 1)
            # the relation graph carries the same state and cause on the node and the edge
            drawn = self.graph(ann, RELATIONS)
            self.assertEqual(self.node(drawn, 'objtype:order')['stale']['label'], '数据变了')
            (edge,) = drawn['edges']
            self.assertEqual((edge['connected'], edge['of'], edge['stale']['label']), (157, 160, '上一步过时'))

    def test_a_changed_meaning_is_a_definition_cause_on_the_type_and_the_step_before_on_the_view(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.everything_confirmed(team)
            changed = ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '1', 'label': '制造中'}]})
            self.assertEqual(changed[0], 200, changed)
            graph = self.graph(ann, LINEAGE)
            order, view = self.node(graph, 'objtype:order'), self.node(graph, 'objview:有效订单')
            self.assertEqual((order['state'], order['stale']['cause'], order['stale']['label'], order['stale']['root_cause']), ('needs_look', 'definition', '定义改了', 'definition'))
            self.assertIn('含义改了', order['stale']['text'])
            self.assertEqual((view['stale']['cause'], view['stale']['root']), ('upstream', '“订单”类型'))
            self.assertEqual(self.node(graph, 'relation:order_customer')['stale']['cause'], 'upstream')   # the type is the root here, one step before it

    def test_the_type_page_lists_what_uses_it_with_counts_and_the_dataset_version_it_stands_on(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, vera = team['ann'], team['vera']
            self.everything_confirmed(team)
            self.assertEqual(ann.post('/api/workspace/ask', {'question': '取消的订单有多少？'})[1]['status'], 'answered')
            status, uses = ann.get('/api/workspace/types/order/uses')
            self.assertEqual(status, 200, uses)
            self.assertEqual((uses['data']['dataset'], uses['data']['version'], uses['data']['link']), ('订单', 1, True))
            self.assertTrue(uses['data']['uploaded_at'])
            self.assertEqual([(u['kind'], u['count']) for u in uses['used_by']], [('views', 1), ('relations', 1), ('answers', 1)])
            self.assertEqual(uses['used_by'][0]['items'], [{'id': '有效订单', 'name': '有效订单', 'state': 'confirmed'}])
            # a viewer reads the views and relations they may see, none of the builders' actions, and none of Ann's answers
            status, theirs = vera.get('/api/workspace/types/order/uses')
            self.assertEqual((status, [u['kind'] for u in theirs['used_by']]), (200, ['views', 'relations']))
            self.assertEqual(ann.get('/api/workspace/types/nothing/uses')[0], 404)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            self.assertEqual(ann.get('/api/workspace/types/order/uses')[1]['data']['version'], 2)

    def test_a_person_a_row_rule_limits_gets_the_graph_without_whole_data_counts_and_no_words_that_quote_them(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.everything_confirmed(team)
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            rule = [{'column': '状态码', 'value': '2', 'user_ids': [ids['vera'], ids['bob']]}]
            status, body = admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rule})
            self.assertEqual(status, 200, body)
            mine = vera.get('/api/workspace/types/order/objects')[1]['total']
            self.assertEqual(mine, 16)   # the cancelled orders (code 2) of the planted 160
            for path in (RELATIONS, LINEAGE):
                graph = self.graph(vera, path)
                order = self.node(graph, 'objtype:order')
                self.assertEqual((order['objects'], order['rows_limited']), (16, True))
                self.assertTrue(graph['rows_limited'])
                self.assertEqual(self.node(graph, 'objtype:customer')['objects'], 30)   # nothing limits the customer rows (KH012 once, since the table was mended)
                self.assertTrue({160, 157}.isdisjoint(numbers_in(graph)))   # 160 orders and 157 connected are the whole data's
            (edge,) = self.graph(vera, RELATIONS)['edges']
            self.assertEqual((edge['of'], edge['rows_limited']), (16, True))
            self.assertLessEqual(edge['connected'], 16)
            self.assertIsNone(edge['cardinality_ok'])   # a slice of the rows says nothing about whether the cardinality holds on all of them
            self.assertIsNone(edge['cardinality_text'])
            self.assertTrue(self.graph(admin, RELATIONS)['edges'][0]['cardinality_ok'])
            # the dataset of a row-ruled type is not found to her: who uploaded it and when are not sent, on the lineage or the type page
            dataset = self.node(self.graph(vera, LINEAGE), 'dataset:订单')
            self.assertEqual((dataset['link'], dataset['uploaded_at'], dataset['who']), (False, None, None))
            uses = vera.get('/api/workspace/types/order/uses')[1]['data']
            self.assertEqual((uses['link'], uses['uploaded_at'], uses['who']), (False, None, None))
            self.assertTrue(self.node(self.graph(admin, LINEAGE), 'dataset:订单')['uploaded_at'])
            # the codes shift: Bob, limited too, is told which cause it is and not the words of it (they quote counts of every row)
            self.assertEqual(admin.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)   # a row-ruled type's dataset is the admin's
            order = self.node(self.graph(bob, LINEAGE), 'objtype:order')
            self.assertEqual((order['state'], order['stale']['label'], order['stale']['text'], order['stale']['short']), ('needs_look', '数据变了', None, None))
            self.assertIn('行规则', order['stale']['text_hidden'])
            self.assertTrue(self.node(self.graph(admin, LINEAGE), 'objtype:order')['stale']['text'].startswith('订单 第 2 版'))   # an admin, whom no rule limits, reads it (a builder no rule names is limited too)
            self.assertNotIn('objtype:order', {n['id'] for n in self.graph(vera, LINEAGE)['nodes']})   # a viewer sees only what is confirmed: nothing that needs a look

    def test_a_limited_builder_reads_no_whole_data_words_on_any_node_view_action_relation_or_answer_after_the_shift(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.everything_confirmed(team)
            action = {'name': '改订单金额', 'type': 'order', 'properties': ['金额']}
            self.assertEqual(ann.post('/api/workspace/actions', action)[0], 200)
            shown = bob.get('/api/workspace/actions/%E6%94%B9%E8%AE%A2%E5%8D%95%E9%87%91%E9%A2%9D')[1]
            self.assertEqual(bob.post('/api/workspace/actions/confirm', {'id': action['name'], 'version': shown['version']})[0], 200)
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            rule = [{'column': '状态码', 'value': '2', 'user_ids': [ids['bob']]}]
            status, body = admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rule})
            self.assertEqual(status, 200, body)
            self.assertEqual(bob.post('/api/workspace/ask', {'question': '取消的订单有多少？'})[1]['status'], 'answered')   # asked under the rule: the rows it read are his
            self.assertEqual(admin.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            for path in (LINEAGE, RELATIONS):
                graph = self.graph(bob, path)
                causes = [n['stale'] for n in graph['nodes'] if n.get('stale')] + [e['stale'] for e in graph.get('edges', []) if e.get('stale')]
                causes += [s['stale'] for n in graph['nodes'] if n['kind'] == 'type' for s in n['views'] + n['actions'] if s['stale']]
                self.assertGreaterEqual(len(causes), 4, path)   # the type, its view and action, the relation (and in the lineage the answer) all need a look
                for cause in causes:
                    self.assertIsNone(cause['text'], path)
                    self.assertIsNone(cause['short'], path)
                    self.assertIn('行规则', cause['text_hidden'])
                self.assertNotIn('第 2 版', json.dumps([c for c in causes], ensure_ascii=False))
            kinds = {n['kind'] for n in self.graph(bob, LINEAGE)['nodes'] if n.get('stale')}
            self.assertEqual(kinds, {'type', 'view', 'action', 'relation', 'answer'})

    def test_the_three_reason_sentences_the_cause_classifier_reads_are_the_ones_the_store_writes(self):
        """The causes are read from the sentences object_types writes as the reason of a needs_look: a change in their wording must fail here, not turn every cause into 数据变了."""
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.everything_confirmed(team)
            self.assertEqual(ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '1', 'label': '制造中'}]})[0], 200)
            definition = ann.get('/api/workspace/types/order')[1]['reason']
            view = next(v for v in ann.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '有效订单')['reason']
            self.assertEqual(definition, '“状态码”的含义改了，要重新确认')
            self.assertEqual(_own_cause(definition), 'definition')
            self.assertEqual((view.startswith('它用的“订单”类型需要再看'), _own_cause(view)), (True, 'cascade'))
        with self.service() as (base, out):
            team = self.team(base)
            self.everything_confirmed(team)
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            meaning = next(p for p in team['ann'].get('/api/workspace/types/order')[1]['properties'] if p['column'] == '状态码')['meanings']['reason']
            type_reason = team['ann'].get('/api/workspace/types/order')[1]['reason']
            self.assertTrue(meaning.startswith('订单 第 2 版（') and '“状态码”的取值变了' in meaning)
            self.assertEqual(_own_cause(meaning), 'data')
            self.assertEqual((type_reason.startswith('它用的“状态码”的含义需要再看'), _own_cause(type_reason)), (True, 'cascade'))

    def test_the_lineage_works_out_the_types_once_and_the_edges_without_example_rows(self):
        from unittest import mock
        from ontology_poc_generator import ontology_graph
        with self.service() as (base, out):
            team = self.team(base)
            self.everything_confirmed(team)
            with mock.patch.object(ontology_graph, '_type_nodes', wraps=ontology_graph._type_nodes) as nodes, \
                    mock.patch.object(ontology_graph, 'check_relation', wraps=ontology_graph.check_relation) as check:
                self.graph(team['ann'], LINEAGE)
            self.assertEqual(nodes.call_count, 1)
            self.assertEqual([c.kwargs['examples'] for c in check.call_args_list], [False])   # one relation, one check, counts only

    def test_a_relation_from_a_type_to_itself_is_listed_once(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            same = {'english_name': 'same_order', 'name': '同一张订单', 'from': 'order', 'to': 'order', 'cardinality': 'one_to_one', 'from_column': '订单号', 'to_column': '订单号'}
            status, body = ann.post('/api/workspace/relations', same)
            self.assertEqual(status, 200, body)
            order = self.node(self.graph(ann, RELATIONS), 'objtype:order')
            self.assertEqual([r['key'] for r in order['relations']], ['same_order'])
            self.assertEqual([(u['kind'], u['count']) for u in ann.get('/api/workspace/types/order/uses')[1]['used_by']], [('relations', 1)])
            edges = {(e['from'], e['to']) for e in self.graph(ann, LINEAGE)['edges']}
            self.assertEqual({e for e in edges if 'relation:same_order' in e}, {('objtype:order', 'relation:same_order')})

    def test_a_type_a_person_may_not_see_is_not_a_node_and_its_relation_is_not_an_edge_and_a_viewer_sees_only_what_is_confirmed(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, vera, admin = team['ann'], team['vera'], team['admin']
            self.everything_confirmed(team)
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['ann']]})[0], 200)
            for path in (RELATIONS, LINEAGE):
                graph = self.graph(vera, path)
                shown = {n['id'] for n in graph['nodes']}
                self.assertNotIn('objtype:customer', shown)
                self.assertNotIn('relation:order_customer', shown)
                self.assertIn('objtype:order', shown)
                self.assertTrue(all(e['from'] in shown and e['to'] in shown for e in graph['edges']))
            self.assertEqual(self.graph(vera, RELATIONS)['edges'], [])
            lineage = self.graph(vera, LINEAGE)
            self.assertNotIn('dataset:客户', {n['id'] for n in lineage['nodes']})   # nothing she may see reads it
            self.assertFalse([n for n in lineage['nodes'] if n['kind'] == 'action' or n['kind'] == 'answer'])
            self.assertIn('objtype:customer', {n['id'] for n in self.graph(ann, RELATIONS)['nodes']})
