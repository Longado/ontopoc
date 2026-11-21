"""One question gives one number: code, not the model, decides which rows the headline covers.

A confirmed view is applied only when the question says its name. When the question names no view, the headline covers every row the asker may read, and each
confirmed view on the measured type that the asker may see has its own number beside it (up to 5; a grouped or top-N answer lists the names only). A condition
the model wrote that the question does not say in its own words (a value, or a confirmed meaning by its name) is not applied; when the model quotes words of the
question for a confirmed meaning written in another language than the question, the answer is refused, saying the confirmed name to use. A plain question
(the names of one type, one number property and views, and nothing else) is read by code with no model at all.

Expected numbers are worked out here with SQL on the sample CSV files (docs/pilot/sample), never taken from the service."""
import csv
import json
import sqlite3
import unittest
from pathlib import Path

from ontology_poc_generator import ask_budget, demo as demo_mode
from ontology_poc_generator.recognition import ModelCompletion
from tests import test_derived_new_values as pilot
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded, change_the_view
from tests.test_derived_view_exact import with_orphan
from tests.test_object_types import ORDER, VALID
from tests.test_two_person import SigningTestCase
from tests import test_workspace_questions as planted_questions
from tests.test_workspace_questions import ALL_ORDERS, AskModel

_KEPT = (demo_mode.GUEST_PER_ADDRESS, ask_budget.GUEST_LIMIT, ask_budget.PERSON_LIMIT, ask_budget.demo_daily_asks)


def setUpModule():   # the same question is asked many times here, by guests from 127.0.0.1: the hourly caps are not what these tests are about
    demo_mode.GUEST_PER_ADDRESS, ask_budget.GUEST_LIMIT, ask_budget.PERSON_LIMIT, ask_budget.demo_daily_asks = 100, 1000, 1000, lambda: 10000


def tearDownModule():
    demo_mode.GUEST_PER_ADDRESS, ask_budget.GUEST_LIMIT, ask_budget.PERSON_LIMIT, ask_budget.demo_daily_asks = _KEPT


class Planted(SigningTestCase):
    """The helpers of the planted-table Q&A tests, without their tests."""
    _helpers = planted_questions.QuestionTests
    team, confirm, confirmed_orders, ask, confirm_view = _helpers.team, _helpers.confirm, _helpers.confirmed_orders, _helpers.ask, _helpers.confirm_view


SAMPLE = Path(__file__).resolve().parents[1] / 'docs' / 'pilot' / 'sample'


def sql(statement: str, orders: str | None = None):
    """One value from SQL over the sample's orders and customers (orders: another orders file's text)."""
    db = sqlite3.connect(':memory:')
    for name, text in (('orders', orders or (SAMPLE / 'orders.csv').read_text(encoding='utf-8')), ('customers', (SAMPLE / 'customers.csv').read_text(encoding='utf-8'))):
        rows = list(csv.DictReader(text.splitlines()))
        db.execute(f'CREATE TABLE {name} ({", ".join(rows[0])})')
        db.executemany(f'INSERT INTO {name} VALUES ({", ".join("?" * len(rows[0]))})', [list(r.values()) for r in rows])
    return db.execute(statement).fetchone()[0]


ALL_AMOUNT = sql('SELECT SUM(CAST(amount AS INTEGER)) FROM orders')
ALL_COUNT = sql('SELECT COUNT(*) FROM orders')
VALID_SQL = "status_code NOT IN ('0', '4', '5')"   # Valid orders / 有效订单: not New (新建), Cancelled (已取消) or Refunded (已退款)
VALID_AMOUNT = sql(f'SELECT SUM(CAST(amount AS INTEGER)) FROM orders WHERE {VALID_SQL}')
VALID_COUNT = sql(f'SELECT COUNT(*) FROM orders WHERE {VALID_SQL}')
SUM_AMOUNT = {'start': 'order', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': 'amount', 'op': 'sum'}}


class Scripted(AskModel):
    """Replies in turn with what it is given: a dict is the item for the question asked, a str is sent as it is (text that is not JSON, or JSON of another shape)."""

    def __init__(self, *replies):
        super().__init__(None)
        self.replies = list(replies)

    def complete_json(self, *, system_prompt, user_prompt, timeout_seconds=None):
        request = json.loads(user_prompt)
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, str):
            return ModelCompletion('test', 'test-model', reply)
        return ModelCompletion('test', 'test-model', json.dumps({'questions': [{'question': request['asked'], **reply}]}, ensure_ascii=False))


def item(query=SUM_AMOUNT, used=(), reasoning='test'):
    return {'reasoning': reasoning, 'query': query, 'definitions_used': list(used)}


def leaving_out(*labels, query=SUM_AMOUNT):
    return {**query, 'where': [{'field': 'status_code', 'not_equals': list(labels)}]}


def excluded(*labels, basis):
    return [{'id': f'orders.status_code={label}', 'direction': 'exclude', 'basis': basis} for label in labels]


def headline(body):
    return (body['status'], body['answer']['measure']['value'], body['answer']['total'])


def beside(body):
    return [(v['name'], (v.get('answer') or {}).get('measure', {}).get('value', (v.get('answer') or {}).get('total')), (v.get('answer') or {}).get('total'), v['confirmed_by'])
            for v in (body.get('beside') or {}).get('views', [])]


class DemoTests(unittest.TestCase):
    """The demo workspace (Order with English names and meanings, the confirmed view Valid orders), asked by a guest (a viewer) and by demo-admin."""

    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        cls.guest = a_guest(cls.demo.base)

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def ask(self, question, *replies, who=None):
        self.demo.model.__class__ = Scripted
        self.demo.model.replies = list(replies) or [item()]
        before = len(self.demo.model.requests)
        status, body = (who or self.guest).call('POST', '/api/workspace/ask', {'question': question})
        self.assertEqual(status, 200, body)
        return body, len(self.demo.model.requests) - before

    def test_the_numbers_here_are_those_of_the_sample(self):
        self.assertEqual((ALL_AMOUNT, ALL_COUNT, VALID_AMOUNT, VALID_COUNT), (162960, 150, 119810, 107))

    def test_the_plain_question_gives_the_same_headline_and_the_same_view_number_beside_it_however_the_model_replies(self):
        replies = {
            'applies the view': [item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': '销售额'}])],
            'applies nothing': [item()],
            'adds an unasked filter, saying it': [item(leaving_out('Cancelled'), excluded('Cancelled', basis='销售额'))],
            'adds an unasked filter, saying nothing': [item(leaving_out('Cancelled', 'Refunded'))],
            'writes the view as its own filter': [item(leaving_out('New', 'Cancelled', 'Refunded'), excluded('New', 'Cancelled', 'Refunded', basis='销售额'))],
            'returns nothing usable once': ['销售额要按哪个口径？', item()],
            'asks back once': [json.dumps({'clarify': ['全部订单', '有效订单']}, ensure_ascii=False), item()],
        }
        for admin in (False, True):
            for case, said in replies.items():
                with self.subTest(case=case, admin=admin):
                    body, _ = self.ask('销售额是多少？', *said, who=self.demo.admin() if admin else None)
                    self.assertEqual(headline(body), ('answered', ALL_AMOUNT, ALL_COUNT), body.get('reason'))
                    self.assertEqual(beside(body), [('Valid orders', VALID_AMOUNT, VALID_COUNT, 'Demo builder')])
                    self.assertNotIn('view', [d['kind'] for d in body['definitions']])
                    self.assertNotIn('WHERE', body.get('query_text', ''))

    def test_a_reply_that_is_never_usable_still_gives_no_number_and_the_model_is_asked_twice_at_most(self):
        body, asked = self.ask('销售额是多少？', 'not json')
        self.assertEqual((body['status'], asked), ('no_query', 2))
        self.assertNotIn('answer', body)

    def test_the_model_is_not_told_a_view_the_question_does_not_name(self):
        self.ask('销售额是多少？', item())
        told = self.demo.model.requests[-1].get('definitions', [])
        self.assertNotIn('Valid orders', [d['id'] for d in told])
        self.assertTrue(any(d['kind'] == 'meaning' for d in told))   # the meanings still are: they are how a question that says them is written

    def test_a_plain_question_in_the_names_is_read_by_code_and_the_model_is_not_asked(self):
        for question, expected in (('What is the total amount?', ('answered', ALL_AMOUNT, ALL_COUNT)), ('How many orders are there?', None)):
            body, asked = self.ask(question, 'not json')
            self.assertEqual(asked, 0, question)
            if expected:
                self.assertEqual(headline(body), expected)
                self.assertEqual(beside(body), [('Valid orders', VALID_AMOUNT, VALID_COUNT, 'Demo builder')])
            else:
                self.assertEqual((body['status'], body['answer']['total']), ('answered', ALL_COUNT))
                self.assertEqual([(v['name'], v['answer']['total']) for v in body['beside']['views']], [('Valid orders', VALID_COUNT)])
            self.assertIsNone(body['model'])

    def test_a_question_that_names_the_view_gets_the_views_number_whatever_filter_the_model_writes_in_its_place(self):
        replies = {
            'applies the view': [item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}])],
            'writes its own filter instead, saying it': [item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='Valid orders'))],
            'writes its own filter instead, saying nothing': [item(leaving_out('Cancelled', 'Refunded'))],
            'returns nothing usable once': ['not json', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}])],
        }
        for case, said in replies.items():
            with self.subTest(case=case):
                body, _ = self.ask('Valid orders 的总金额是多少？', *said)
                self.assertEqual(headline(body), ('answered', VALID_AMOUNT, VALID_COUNT), body.get('reason'))
                self.assertEqual([(d['kind'], d['name'], d['confirmed_by']) for d in body['definitions'] if d['kind'] == 'view'], [('view', 'Valid orders', 'Demo builder')])
                self.assertIsNone(body.get('beside'))   # the question named a view: nothing beside it
        body, asked = self.ask('What is the total amount of Valid orders?', 'not json')   # in the names only: code reads it
        self.assertEqual((headline(body), asked), (('answered', VALID_AMOUNT, VALID_COUNT), 0))
        for case, said in {'writes nothing about it': item(), 'writes the other rows': item({**SUM_AMOUNT, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}]})}.items():
            with self.subTest(case=case):   # no word on the view, or a filter that goes against it: code does not guess the direction, it refuses
                body, _ = self.ask('Valid orders 的总金额是多少？', said)
                self.assertEqual(body['status'], 'definition_unmet', body)
                self.assertNotIn('answer', body)

    def test_a_view_said_in_another_language_than_its_name_never_gives_the_models_own_filter_as_the_headline(self):
        """有效订单 is not the name of Valid orders, and code cannot tell that it means it. The model's own filter is never the headline: when it quotes the question's
        words for it the answer is refused, saying the confirmed names to use; otherwise the filter is dropped and the headline covers every row."""
        refused = {'quotes the words for its own filter': [item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='有效订单'))]}
        dropped = {'gives words that are not the question\'s': [item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='valid'))],
                   'says nothing of its filter': [item(leaving_out('Cancelled', 'Refunded'))], 'writes no filter': [item()]}
        for case, said in refused.items():
            with self.subTest(case=case):
                body, _ = self.ask('有效订单的总金额是多少？', *said)
                self.assertEqual(body['status'], 'definition_unmet', body)
                self.assertNotIn('answer', body)
                self.assertIn('Cancelled', body['reason'])
                self.assertIn('Valid orders', body['reason'])   # the confirmed view on Order, named so it can be asked for by its name
        for case, said in dropped.items():
            with self.subTest(case=case):
                body, _ = self.ask('有效订单的总金额是多少？', *said)
                self.assertEqual(headline(body), ('answered', ALL_AMOUNT, ALL_COUNT))
                self.assertEqual(beside(body), [('Valid orders', VALID_AMOUNT, VALID_COUNT, 'Demo builder')])

    def test_a_meaning_said_in_the_questions_own_words_is_applied_and_one_said_in_another_language_is_refused_not_dropped(self):
        cancelled = sql("SELECT COUNT(*) FROM orders WHERE status_code = '4'")
        query = {**ALL_ORDERS, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}]}
        body, _ = self.ask('How many Cancelled orders?', item(query, [{'id': 'orders.status_code=Cancelled', 'direction': 'include', 'basis': 'Cancelled'}]))
        self.assertEqual((body['status'], body['answer']['total']), ('answered', cancelled))
        body, _ = self.ask('已取消的订单有多少？', item(query, [{'id': 'orders.status_code=Cancelled', 'direction': 'include', 'basis': '已取消'}]))
        self.assertEqual(body['status'], 'definition_unmet', body)   # never all 150 orders for a question that asks for the cancelled ones
        self.assertIn('Cancelled', body['reason'])


class ChangedViewTests(unittest.TestCase):
    """The demo after demo-admin changes Valid orders: it waits for Demo builder."""

    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        change_the_view(cls.demo.admin())

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_a_named_view_that_waits_is_refused_for_a_builder_and_a_viewer_and_one_not_named_is_neither_applied_nor_beside(self):
        model = self.demo.model
        model.item = item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}])
        for who, viewer in ((self.demo.admin('en'), False), (a_guest(self.demo.base, 'en'), True)):
            asked = len(model.requests)
            status, body = who.call('POST', '/api/workspace/ask', {'question': 'What is the total amount of Valid orders?'})
            self.assertEqual((status, body['status'], len(model.requests)), (200, 'refused', asked), body)
            if viewer:
                self.assertTrue(all(set(d) <= {'kind', 'state', 'waiting', 'text'} for d in body['refusal']['definitions']))   # told only that it waits
            else:
                self.assertIn('Valid orders', [d['name'] for d in body['refusal']['definitions']])
            status, body = who.call('POST', '/api/workspace/ask', {'question': 'What is the total amount?'})
            self.assertEqual(headline(body), ('answered', ALL_AMOUNT, ALL_COUNT))
            self.assertIsNone(body.get('beside'))


class PilotTests(pilot.PilotFoundation):
    """The pilot sample with the view 有效订单 named in Chinese, as the questions are, and the derived property 有效订单金额 on Customer."""

    def ask(self, question, *replies, orders=None):
        model = Scripted(*replies)
        with self.service(gateway=model) as (base, out):
            ann = self.foundation(base, orders=orders)['ann']
            status, body = ann.post('/api/workspace/ask', {'question': question})
            self.assertEqual(status, 200, body)
            return body

    def test_with_an_order_whose_customer_is_missing_the_named_view_gives_the_rows_total_or_is_refused_never_the_customers_sum(self):
        orders = with_orphan()
        rows = sql(f'SELECT SUM(CAST(amount AS INTEGER)) FROM orders WHERE {VALID_SQL}', orders)
        self.assertEqual(rows, 169810)
        view = [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}]
        every_customer = {'start': 'customer', 'where': [{'field': 'tier', 'equals': ['A', 'B', 'C']}], 'via': [], 'group_by': None, 'share': None,
                          'measure': {'field': '有效订单金额', 'op': 'sum'}}   # a filter every customer matches, which the question never says
        for case, said in {'reads the orders through the view': item(used=view), 'reads the orders and writes the filter itself': item(leaving_out('新建', '已取消', '已退款'), []),
                           'reads the orders and leaves out less than the view': item(leaving_out('已取消'), [])}.items():
            with self.subTest(case=case):
                body = self.ask('有效订单的总金额是多少？', said, orders=orders)
                self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', rows), body.get('reason'))
        body = self.ask('有效订单的总金额是多少？', item(every_customer, view), orders=orders)
        self.assertNotEqual((body.get('answer') or {}).get('measure', {}).get('value'), 119810)
        self.assertEqual(body['status'], 'definition_unmet', body)

    def test_a_value_the_question_says_is_kept_and_one_the_model_adds_is_dropped(self):
        city = {'start': 'customer', 'where': [{'field': 'city', 'equals': 'Shenzhen'}], 'via': [], 'group_by': None, 'share': None, 'measure': None}
        body = self.ask('Shenzhen 的客户有多少？', item(city))
        self.assertEqual((body['status'], body['answer']['total']), ('answered', sql("SELECT COUNT(*) FROM customers WHERE city = 'Shenzhen'")))
        body = self.ask('客户总数是多少？', item(city))
        self.assertEqual((body['status'], body['answer']['total']), ('answered', sql('SELECT COUNT(*) FROM customers')))
        self.assertEqual([d['name'] for d in body['not_applied']], ['city'])
        self.assertNotIn('WHERE', body.get('query_text', ''))


class PlantedTests(Planted):
    """The seven planted tables: 订单 with 状态码 0 = 已交付, 1 = 生产中, 2 = 已取消, and the view 有效订单 (not 已取消)."""

    def with_valid(self, team, orders=ORDER):
        self.assertEqual(team['ann'].post('/api/workspace/types', orders)[0], 200)
        self.confirm(team['bob'], 'order', '状态码')
        self.confirm(team['bob'], 'order')
        self.assertEqual(team['ann'].post('/api/workspace/types/views', VALID)[0], 200)
        self.confirm_view(team['bob'], 'order', '有效订单')

    def test_a_viewer_limited_by_a_row_rule_gets_the_headline_and_the_view_number_on_their_own_rows(self):
        from tests.test_workspace_questions import ORDERS
        mine = [r for r in ORDERS if r['客户编号'] == 'KH001']
        with self.service(gateway=Scripted('not json')) as (base, out):
            team = self.team(base)
            self.with_valid(team, {**ORDER, 'properties': [*ORDER['properties'], {'column': '客户编号'}]})
            vera_id = next(u['id'] for u in team['admin'].get('/api/users')[1]['users'] if u['username'] == 'vera')
            self.assertEqual(team['admin'].post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [vera_id]}]})[0], 200)
            status, body = self.ask(team['vera'], '订单有多少？')
            self.assertEqual((status, body['status'], body['answer']['total']), (200, 'answered', len(mine)), body)
            self.assertEqual([(v['name'], v['answer']['total']) for v in body['beside']['views']], [('有效订单', sum(r['状态码'] != '2' for r in mine))])
            self.assertLess(len(mine), 160)

    def test_a_view_the_asker_may_not_see_changes_nothing_in_the_answer(self):
        def asked(client, question, model):
            model.replies = [item({**ALL_ORDERS}, [])]
            body = self.ask(client, question)[1]
            return json.dumps({k: v for k, v in body.items() if k not in ('id', 'asked_at')}, ensure_ascii=False, sort_keys=True)
        model = Scripted(item(ALL_ORDERS))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            vera, ann = team['vera'], team['ann']
            before = [asked(vera, q, model) for q in ('订单有多少？', '一共下了多少单？')]
            self.assertEqual(ann.post('/api/workspace/types/views', {'name': '在产订单', 'type': 'order', 'filters': [{'column': '状态码', 'op': 'is', 'label': '生产中'}]})[0], 200)   # proposed: not a viewer's
            after = [asked(vera, q, model) for q in ('订单有多少？', '一共下了多少单？')]
            self.assertEqual(before, after)
            self.assertNotIn('在产订单', ''.join(after))
            self.assertNotIn('在产订单', json.dumps(model.requests, ensure_ascii=False))

    def test_more_than_five_views_are_capped_and_a_grouped_answer_lists_names_only(self):
        labels = ('已交付', '生产中', '已取消')
        kinds = [[('is', '已交付')], [('is', '生产中')], [('is', '已取消')], [('is_not', '已交付')], [('is_not', '生产中')], [('is_not', '已交付'), ('is_not', '生产中')]]
        views = [{'name': f'视图{i}', 'type': 'order', 'filters': [{'column': '状态码', 'op': op, 'label': label} for op, label in k]} for i, k in enumerate(kinds, 1)]
        grouped = {**ALL_ORDERS, 'group_by': ['状态码']}
        with self.service(gateway=Scripted(item(grouped, [{'id': f'订单.状态码={l}', 'direction': 'mention', 'basis': '状态'} for l in labels]))) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            for v in views:
                self.assertEqual(team['ann'].post('/api/workspace/types/views', v)[0], 200)
                self.confirm_view(team['bob'], 'order', v['name'])
            names = sorted(['有效订单', *(v['name'] for v in views)])
            body = self.ask(team['ann'], '订单有多少？')[1]
            self.assertEqual([v['name'] for v in body['beside']['views']], names[:5])
            self.assertEqual(body['beside']['more'], names[5:])
            self.assertTrue(all('answer' in v for v in body['beside']['views']))
            body = self.ask(team['ann'], '各状态码的订单各有多少？')[1]
            self.assertEqual(body['status'], 'answered', body)
            self.assertEqual([v['name'] for v in body['beside']['views']], names[:5])
            self.assertFalse(any('answer' in v for v in body['beside']['views']))

    def test_a_question_that_leaves_a_meaning_out_by_its_name_is_answered_so_and_the_view_it_reads_is_not_beside_it(self):
        model = Scripted(item(ALL_ORDERS, [{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '不算已取消'}]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            body = self.ask(team['ann'], '不算已取消的订单有多少？')[1]
            self.assertEqual((body['status'], body['answer']['total']), ('answered', 144))
            self.assertIsNone(body.get('beside'))
            model.replies = [item({**ALL_ORDERS, 'where': [{'field': '状态码', 'equals': '2'}]}, [{'id': '订单.状态码=已取消', 'direction': 'include', 'basis': '取消的'}])]
            body = self.ask(team['ann'], '取消的订单有多少？')[1]   # 已取消 said without its 已
            self.assertEqual((body['status'], body['answer']['total']), ('answered', 16))
            model.replies = [item({**ALL_ORDERS, 'where': [{'field': '状态码', 'not_equals': ['2']}]}, [{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '销售总额'}])]
            body = self.ask(team['ann'], '订单的销售总额是多少？')[1]   # the model reads 销售 as leaving out 已取消: not said, so not applied
            self.assertEqual((body['status'], body['answer']['total']), ('answered', 160))
            self.assertEqual([(v['name'], v['answer']['total']) for v in body['beside']['views']], [('有效订单', 144)])

    def test_a_saved_answer_says_when_a_view_beside_it_has_changed(self):
        with self.service(gateway=Scripted('not json')) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            ann = team['ann']
            saved = self.ask(ann, '订单有多少？')[1]
            self.assertEqual([v['name'] for v in saved['beside']['views']], ['有效订单'])
            view = next(v for v in ann.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '有效订单')
            status, body = ann.post('/api/workspace/types/views/update', {'id': '有效订单', 'version': view['version'], 'type': 'order',
                                                                         'filters': [*VALID['filters'], {'column': '状态码', 'op': 'is_not', 'label': '生产中'}]})
            self.assertEqual(status, 200, body)
            reopened = ann.get(f'/api/workspace/ask/{saved["id"]}')[1]
            self.assertIn('有效订单', [c['name'] for c in reopened['changed']])


class QueryTextTests(Planted):
    """POST /api/workspace/query and the MCP answers carry the same `beside` as a question."""

    def test_a_written_query_lists_the_views_beside_it(self):
        with self.service(gateway=Scripted('not json')) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            self.assertEqual(team['ann'].post('/api/workspace/types/views', VALID)[0], 200)
            self.confirm_view(team['bob'], 'order', '有效订单')
            status, body = team['ann'].post('/api/workspace/query', {'text': 'SELECT count(o) FROM (o:订单)'})
            self.assertEqual((status, body['answer']['total']), (200, 160), body)
            self.assertEqual([(v['name'], v['answer']['total'], v['confirmed_by']) for v in body['beside']['views']], [('有效订单', 144, 'Bob')])

    def test_the_mcp_answers_pass_beside_through(self):
        from ontology_poc_generator import mcp_server

        class Session:
            def __init__(self, body):
                self.body = body

            def request(self, path, payload=None):
                return self.body
        body = {'status': 'answered', 'answer': {'total': 160}, 'beside': {'views': [{'name': '有效订单', 'answer': {'total': 144}, 'confirmed_by': 'Bob'}], 'more': []},
                'not_applied': [{'kind': 'condition', 'name': 'city', 'why': 'x'}], 'definitions': [], 'query_text': 'SELECT count(o) FROM (o:订单)'}
        lean = {'views': [{'name': '有效订单', 'confirmed_by': 'Bob', 'answer': {'total': 144}}]}   # no id or version for an agent
        self.assertEqual(mcp_server.ask(Session(body), {'question': 'q'})['beside'], lean)
        self.assertEqual(mcp_server.ask(Session(body), {'question': 'q'})['not_applied'], body['not_applied'])
        self.assertEqual(mcp_server.ontopoc_query(Session(body), {'text': 'SELECT count(o) FROM (o:订单)'})['beside'], lean)


if __name__ == '__main__':
    unittest.main()
