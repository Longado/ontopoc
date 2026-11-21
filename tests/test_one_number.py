"""The same question worked out on other rows, shown beside an answer. Which rows the answer itself covers is decided as before; this only adds `beside`:
A. an answer on every row of one type (no condition, no grouping or top-N, no walk, no derived property) also shows each confirmed view on that type the asker
   may see, with its own number and who confirmed it;
B. an answer on exactly one confirmed view on that type and nothing else also shows every row, and the other confirmed views;
C. nothing beside any other answer.
The differential test asks the same questions with the same scripted replies with ADD_BESIDE on and off and requires the answers, `beside` left out, to be the
same; off, the code is the earlier code. Expected numbers are worked out here with SQL on the sample CSV files (docs/pilot/sample)."""
import csv
import json
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from ontology_poc_generator import ask_budget, demo as demo_mode, workspace_questions
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


def where_amount(where: str) -> int:
    return sql(f'SELECT SUM(CAST(amount AS INTEGER)) FROM orders WHERE {where}')


def stripped(body: dict) -> str:
    return json.dumps({k: v for k, v in body.items() if k not in ('id', 'asked_at', 'beside')}, ensure_ascii=False, sort_keys=True)


VALID_INCLUDE = [{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}]
RANGE = {**SUM_AMOUNT, 'where': [{'field': 'amount', 'at_least': 1000}]}
DEMO_PAIRS = [   # (question, the model's reply): the reviewer's groups, B1–B4 on the demo, the 已取消 cases and the D15 question in every reading
    ('销售额是多少？', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': '销售额'}])), ('销售额是多少？', item()),
    ('销售额是多少？', item(leaving_out('New', 'Cancelled', 'Refunded'), excluded('New', 'Cancelled', 'Refunded', basis='销售额'))),
    ('销售额是多少？', item(leaving_out('New', 'Cancelled', 'Refunded'))), ('销售额是多少？', '销售额要按哪个口径？'),
    ('销售额是多少？', json.dumps({'clarify': ['全部订单', '有效订单']}, ensure_ascii=False)),
    ('销售额是多少？', item(leaving_out('Cancelled'), excluded('Cancelled', basis='销售额'))), ('销售额是多少？', item(leaving_out('Cancelled', 'Refunded'))),
    ('销售额是多少？', item(RANGE)), ('销售额是多少？', item({**SUM_AMOUNT, 'where': [{'field': 'order_date', 'at_least': '2026-06-01', 'at_most': '2026-06-30'}]})),
    ('销售额是多少？', item({**SUM_AMOUNT, 'where': [{'field': 'status_code', 'at_least': 4, 'at_most': 4}]})),
    ('销售额是多少？', item({**SUM_AMOUNT, 'measure': {'field': 'amount', 'op': 'average'}})),
    ('Valid orders 的总金额是多少？', item(used=VALID_INCLUDE)), ('Valid orders 的总金额是多少？', item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='Valid orders'))),
    ('Valid orders 的总金额是多少？', item(leaving_out('Cancelled', 'Refunded'))), ('Valid orders 的总金额是多少？', item()),
    ('Valid orders 的总金额是多少？', item({**SUM_AMOUNT, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}]})), ('Valid orders 的总金额是多少？', item(RANGE, VALID_INCLUDE)),
    ('What is the total amount of valid orders?', item(used=VALID_INCLUDE)), ('What is the total amount of valid orders?', 'not json'),
    ('有效订单的总金额是多少？', item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='有效订单'))),
    ('有效订单的总金额是多少？', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': '有效订单'}])),
    ('有效订单的总金额是多少？', item(leaving_out('New', 'Cancelled', 'Refunded'), excluded('New', 'Cancelled', 'Refunded', basis='有效订单'))),
    ('不算新建、取消和退款的订单金额合计？', item(leaving_out('New', 'Cancelled', 'Refunded'), excluded('New', 'Cancelled', 'Refunded', basis='不算新建、取消和退款'))),
    ('只算付了款、发了货或送达的订单，金额合计？', item(leaving_out('New', 'Cancelled', 'Refunded'), excluded('New', 'Cancelled', 'Refunded', basis='付了款、发了货或送达'))),
    *((q, item(used=VALID_INCLUDE)) for q in ('valid-orders 的总金额是多少？', 'ValidOrders 的总金额是多少？', 'ｖａｌｉｄ　ｏｒｄｅｒｓ 的总金额是多少？')),
    *((q, item({**ALL_ORDERS, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}]}, used)) for q in ('已取消的订单有多少？', '有多少订单被取消了')
      for used in ([{'id': 'orders.status_code=Cancelled', 'direction': 'include', 'basis': '已取消'}], [])),
    ('已取消的订单有多少？', item(ALL_ORDERS)), ('有多少订单被取消了', item(ALL_ORDERS)),
    ('What is the total amount?', item()), ('How many orders are there?', item(ALL_ORDERS)), ('What is the amount of an order?', 'not json'),
    ('各状态的订单金额', item({**SUM_AMOUNT, 'group_by': ['status_code']}, [{'id': f'orders.status_code={l}', 'direction': 'mention', 'basis': '状态'} for l in ('New', 'Paid', 'Shipped', 'Delivered', 'Cancelled', 'Refunded')])),
]


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
        status, body = (who or self.guest).call('POST', '/api/workspace/ask', {'question': question})
        self.assertEqual(status, 200, body)
        return body

    def test_the_numbers_here_are_those_of_the_sample(self):
        self.assertEqual((ALL_AMOUNT, ALL_COUNT, VALID_AMOUNT, VALID_COUNT), (162960, 150, 119810, 107))

    def test_with_beside_left_out_every_answer_is_the_one_given_without_it(self):
        for who in (self.guest, self.demo.admin('en')):
            for question, reply in DEMO_PAIRS:
                with self.subTest(question=question, reply=str(reply)[:80]):
                    on = self.ask(question, reply, who=who)
                    with mock.patch.object(workspace_questions, 'ADD_BESIDE', False):
                        off = self.ask(question, reply, who=who)
                    self.assertNotIn('beside', off)
                    self.assertEqual(stripped(on), stripped(off))
        self.assertGreaterEqual(len(DEMO_PAIRS), 36)

    def test_the_plain_question_shows_both_numbers_whichever_reading_the_model_takes(self):
        a = self.ask('销售额是多少？', item())   # A: every row, the view beside it
        self.assertEqual(headline(a), ('answered', ALL_AMOUNT, ALL_COUNT))
        self.assertEqual(beside(a), [('Valid orders', VALID_AMOUNT, VALID_COUNT, 'Demo builder')])
        b = self.ask('销售额是多少？', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': '销售额'}]))   # B: the view, every row beside it
        self.assertEqual(headline(b), ('answered', VALID_AMOUNT, VALID_COUNT))
        self.assertEqual([(v.get('all_rows'), v['name'], v['answer']['measure']['value'], v['answer']['total']) for v in b['beside']['views']], [(True, 'Order', ALL_AMOUNT, ALL_COUNT)])
        self.assertEqual([(d['kind'], d['name']) for d in b['definitions'] if d['kind'] == 'view'], [('view', 'Valid orders')])

    def test_nothing_is_beside_an_answer_with_any_other_condition(self):
        for case, reply in {'the view conditions written out': item(leaving_out('New', 'Cancelled', 'Refunded'), excluded('New', 'Cancelled', 'Refunded', basis='销售额')),
                            'a meaning left out': item(leaving_out('Cancelled'), excluded('Cancelled', basis='销售额')), 'a range': item(RANGE),
                            'the view and a range': item(RANGE, [{'id': 'Valid orders', 'direction': 'include', 'basis': '销售额'}]),
                            'grouped': item({**SUM_AMOUNT, 'group_by': ['status_code']}, [{'id': f'orders.status_code={l}', 'direction': 'mention', 'basis': '状态'} for l in ('New', 'Paid', 'Shipped', 'Delivered', 'Cancelled', 'Refunded')]),
                            'a refusal': item(leaving_out('Cancelled', 'Refunded'))}.items():
            with self.subTest(case=case):
                body = self.ask('销售额是多少？', reply)
                self.assertNotIn('beside', body)
        body = self.ask('销售额是多少？', item(RANGE, [{'id': 'Valid orders', 'direction': 'include', 'basis': '销售额'}]))
        self.assertEqual(body['answer']['measure']['value'], where_amount(f'{VALID_SQL} AND CAST(amount AS INTEGER) >= 1000'))   # the answer itself as before


class CommonWordViewTests(unittest.TestCase):
    """Views named with common words (All keeps Paid, Big keeps Delivered, Now keeps Shipped): answers as before, beside left out."""

    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        admin, builder = cls.demo.admin(), cls.demo.builder()
        for name, label in (('All', 'Paid'), ('Big', 'Delivered'), ('Now', 'Shipped')):
            assert admin.call('POST', '/api/workspace/types/views', {'name': name, 'type': 'order', 'filters': [{'column': 'status_code', 'op': 'is', 'label': label}]})[0] == 200
            view = next(v for v in builder.call('GET', '/api/workspace/types/order/views')[1]['views'] if v['name'] == name)
            assert builder.call('POST', '/api/workspace/types/views/confirm', {'id': name, 'version': view['version'], 'seen': view['seen']})[0] == 200
        cls.guest = a_guest(cls.demo.base, 'en')

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_with_beside_left_out_the_answers_are_the_same(self):
        self.demo.model.__class__ = Scripted
        pairs = [('What is the total amount of all orders?', item()), ('How big is the total amount?', item()), ('How many orders are there now?', item(ALL_ORDERS)),
                 ('What is the total amount of all orders?', item(used=[{'id': 'All', 'direction': 'include', 'basis': 'all'}]))]
        for question, reply in pairs:
            with self.subTest(question=question):
                got = []
                for flag in (True, False):
                    self.demo.model.replies = [reply]
                    with mock.patch.object(workspace_questions, 'ADD_BESIDE', flag):
                        got.append(self.guest.call('POST', '/api/workspace/ask', {'question': question})[1])
                self.assertEqual(stripped(got[0]), stripped(got[1]))


class PilotTests(pilot.PilotFoundation):
    """The pilot sample with the view 有效订单 named in Chinese, and the derived property 有效订单金额 on Customer."""

    PAIRS = [
        ('成都的客户有多少个？', item({'start': 'customer', 'where': [{'field': 'city', 'equals': 'Chengdu'}], 'via': [], 'group_by': None, 'share': None, 'measure': None})),
        ('成都 A 级客户有多少个？', item({'start': 'customer', 'where': [{'field': 'city', 'equals': 'Chengdu'}, {'field': 'tier', 'equals': 'A'}], 'via': [], 'group_by': None, 'share': None, 'measure': None})),
        ('How many A customers?', item({'start': 'customer', 'where': [{'field': 'tier', 'equals': 'A'}], 'via': [], 'group_by': None, 'share': None, 'measure': None})),
        ('客户有多少？', item({'start': 'customer', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': None})),
        ('What is the amount of an order?', 'not json'),
        ('有效订单加上新建订单的金额合计？', item(leaving_out('4', '5'), [{'id': f'orders.status_code={l}', 'direction': 'exclude', 'basis': '有效订单加上新建订单'} for l in ('已取消', '已退款')])),
        ('有效订单的总金额是多少？', item(used=[{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}])),
        ('有效订单的总金额是多少？', item(leaving_out('新建', '已取消', '已退款'), [])), ('有效订单的总金额是多少？', item(leaving_out('已取消'), [])),
        ('有效订单的总金额是多少？', item({'start': 'customer', 'where': [{'field': 'customer_id', 'not_equals': ['C009']}], 'via': [], 'group_by': None, 'share': None,
                                        'measure': {'field': '有效订单金额', 'op': 'sum'}}, [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}])),
        ('有效订单的总金额是多少？', item({'start': 'customer', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': '有效订单金额', 'op': 'sum'}},
                                     [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}])),
    ]

    def test_with_beside_left_out_every_answer_is_the_one_given_without_it_and_a_derived_property_has_nothing_beside(self):
        for orders in (None, with_orphan()):
            model = Scripted(item())
            with self.service(gateway=model) as (base, out):
                ann = self.foundation(base, orders=orders)['ann']
                for question, reply in self.PAIRS:
                    with self.subTest(question=question, reply=str(reply)[:80], orphan=orders is not None):
                        got = []
                        for flag in (True, False):
                            model.replies = [reply]
                            with mock.patch.object(workspace_questions, 'ADD_BESIDE', flag):
                                got.append(ann.post('/api/workspace/ask', {'question': question})[1])
                        self.assertEqual(stripped(got[0]), stripped(got[1]))
                        if '有效订单金额' in json.dumps(reply, ensure_ascii=False) or (got[0].get('query') or {}).get('where'):
                            self.assertNotIn('beside', got[0])   # a derived property's route, or a condition: nothing beside
        self.assertEqual(sql(f'SELECT SUM(CAST(amount AS INTEGER)) FROM orders WHERE {VALID_SQL}', with_orphan()), 169810)


class PlantedTests(Planted):
    """The seven planted tables: 订单 with 状态码 0 = 已交付, 1 = 生产中, 2 = 已取消, and the view 有效订单 (not 已取消)."""

    def with_valid(self, team, orders=ORDER):
        self.assertEqual(team['ann'].post('/api/workspace/types', orders)[0], 200)
        self.confirm(team['bob'], 'order', '状态码')
        self.confirm(team['bob'], 'order')
        self.assertEqual(team['ann'].post('/api/workspace/types/views', VALID)[0], 200)
        self.confirm_view(team['bob'], 'order', '有效订单')

    def test_a_viewer_limited_by_a_row_rule_gets_both_readings_on_their_own_rows(self):
        from tests.test_workspace_questions import ORDERS
        mine = [r for r in ORDERS if r['客户编号'] == 'KH001']
        model = Scripted(item(ALL_ORDERS))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.with_valid(team, {**ORDER, 'properties': [*ORDER['properties'], {'column': '客户编号'}]})
            vera_id = next(u['id'] for u in team['admin'].get('/api/users')[1]['users'] if u['username'] == 'vera')
            self.assertEqual(team['admin'].post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '客户编号', 'value': 'KH001', 'user_ids': [vera_id]}]})[0], 200)
            body = self.ask(team['vera'], '订单有多少？')[1]
            self.assertEqual((body['status'], body['answer']['total']), ('answered', len(mine)), body)
            self.assertEqual([(v['name'], v['answer']['total']) for v in body['beside']['views']], [('有效订单', sum(r['状态码'] != '2' for r in mine))])
            model.replies = [item(ALL_ORDERS, [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}])]
            body = self.ask(team['vera'], '有效订单有多少？')[1]
            self.assertEqual(body['answer']['total'], sum(r['状态码'] != '2' for r in mine))
            self.assertEqual([(v.get('all_rows'), v['answer']['total']) for v in body['beside']['views']], [(True, len(mine))])
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

    def test_more_than_five_views_are_capped_and_one_view_shows_every_row_and_the_others(self):
        kinds = [[('is', '已交付')], [('is', '生产中')], [('is', '已取消')], [('is_not', '已交付')], [('is_not', '生产中')], [('is_not', '已交付'), ('is_not', '生产中')]]
        views = [{'name': f'视图{i}', 'type': 'order', 'filters': [{'column': '状态码', 'op': op, 'label': label} for op, label in k]} for i, k in enumerate(kinds, 1)]
        model = Scripted(item(ALL_ORDERS))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            for v in views:
                self.assertEqual(team['ann'].post('/api/workspace/types/views', v)[0], 200)
                self.confirm_view(team['bob'], 'order', v['name'])
            names = sorted(['有效订单', *(v['name'] for v in views)])
            body = self.ask(team['ann'], '订单有多少？')[1]
            self.assertEqual([v['name'] for v in body['beside']['views']], names[:5])
            self.assertEqual(body['beside']['more'], names[5:])
            model.replies = [item(ALL_ORDERS, [{'id': '视图1', 'direction': 'include', 'basis': '视图1'}])]
            body = self.ask(team['ann'], '视图1有多少？')[1]
            self.assertEqual([v['name'] for v in body['beside']['views']][:1], ['订单'])
            self.assertEqual([(v.get('all_rows'), v['answer']['total']) for v in body['beside']['views']][0], (True, 160))
            self.assertNotIn('视图1', [v['name'] for v in body['beside']['views']])

    def test_a_saved_answer_says_when_a_view_beside_it_was_confirmed_again_since(self):
        with self.service(gateway=Scripted(item(ALL_ORDERS))) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            ann = team['ann']
            saved = self.ask(ann, '订单有多少？')[1]
            self.assertEqual([v['name'] for v in saved['beside']['views']], ['有效订单'])
            view = next(v for v in ann.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == '有效订单')
            status, body = ann.post('/api/workspace/types/views/update', {'id': '有效订单', 'version': view['version'], 'type': 'order',
                                                                         'filters': [*VALID['filters'], {'column': '状态码', 'op': 'is_not', 'label': '生产中'}]})
            self.assertEqual(status, 200, body)
            self.confirm_view(team['bob'], 'order', '有效订单')
            reopened = ann.get(f'/api/workspace/ask/{saved["id"]}')[1]
            self.assertEqual(reopened['beside_changed'], ['有效订单'])
            self.assertEqual(reopened['changed'], [])   # the answer itself stood on nothing that changed

    def test_a_reopened_answer_names_no_view_beside_it_that_now_waits_for_a_builder_or_a_viewer(self):
        kinds = [[('is', '已交付')], [('is', '生产中')], [('is', '已取消')], [('is_not', '已交付')], [('is_not', '生产中')], [('is_not', '已交付'), ('is_not', '生产中')]]
        views = [{'name': f'视图{i}', 'type': 'order', 'filters': [{'column': '状态码', 'op': op, 'label': label} for op, label in k]} for i, k in enumerate(kinds, 1)]
        with self.service(gateway=Scripted(item(ALL_ORDERS))) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            ann = team['ann']
            for v in views:
                self.assertEqual(ann.post('/api/workspace/types/views', v)[0], 200)
                self.confirm_view(team['bob'], 'order', v['name'])
            saved = {who: self.ask(team[who], '订单有多少？')[1] for who in ('ann', 'vera')}
            for body in saved.values():
                self.assertEqual(([v['name'] for v in body['beside']['views']], body['beside']['more']), (['有效订单', '视图1', '视图2', '视图3', '视图4'], ['视图5', '视图6']))
            for name in ('视图1', '视图6'):   # one with a number beside, one named in `more`: both are changed and wait for confirming
                view = next(v for v in ann.get('/api/workspace/types/order/views')[1]['views'] if v['name'] == name)
                status, body = ann.post('/api/workspace/types/views/update', {'id': name, 'version': view['version'], 'type': 'order', 'filters': [*view['filters'], {'column': '状态码', 'op': 'is_not', 'label': '已取消'}]})
                self.assertEqual((status, body['state']), (200, 'checked'), body)
            for who in ('ann', 'vera'):
                reopened = team[who].get(f'/api/workspace/ask/{saved[who]["id"]}')[1]
                self.assertEqual(([v['name'] for v in reopened['beside']['views']], reopened['beside']['more']), (['有效订单', '视图2', '视图3', '视图4'], ['视图5']), who)
                said = json.dumps({k: reopened.get(k) for k in ('beside', 'beside_changed')}, ensure_ascii=False)
                for name in ('视图1', '视图6'):
                    self.assertNotIn(name, said, who)


class QueryTextTests(Planted):
    """POST /api/workspace/query and the MCP answers carry the same `beside` as a question."""

    def test_a_written_query_with_no_condition_lists_the_views_beside_it_and_one_with_a_condition_does_not(self):
        with self.service(gateway=Scripted('not json')) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            self.assertEqual(team['ann'].post('/api/workspace/types/views', VALID)[0], 200)
            self.confirm_view(team['bob'], 'order', '有效订单')
            status, body = team['ann'].post('/api/workspace/query', {'text': 'SELECT count(o) FROM (o:订单)'})
            self.assertEqual((status, body['answer']['total']), (200, 160), body)
            self.assertEqual([(v['name'], v['answer']['total'], v['confirmed_by']) for v in body['beside']['views']], [('有效订单', 144, 'Bob')])
            status, body = team['ann'].post('/api/workspace/query', {'text': "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已交付'"})
            self.assertEqual(status, 200, body)
            self.assertNotIn('beside', body)

    def test_the_mcp_answers_pass_beside_through(self):
        from ontology_poc_generator import mcp_server

        class Session:
            def __init__(self, body):
                self.body = body

            def request(self, path, payload=None):
                return self.body
        body = {'status': 'answered', 'answer': {'total': 144}, 'beside': {'views': [{'all_rows': True, 'name': '订单', 'answer': {'total': 160}},
                                                                                     {'id': 'objview:x', 'version': 1, 'name': 'x', 'answer': {'total': 3}, 'confirmed_by': 'Bob'}], 'more': []},
                'definitions': [], 'query_text': 'SELECT count(o) FROM (o:订单)'}
        lean = {'views': [{'all_rows': True, 'name': '订单', 'answer': {'total': 160}}, {'name': 'x', 'confirmed_by': 'Bob', 'answer': {'total': 3}}]}   # no id or version for an agent
        self.assertEqual(mcp_server.ask(Session(body), {'question': 'q'})['beside'], lean)
        self.assertEqual(mcp_server.ontopoc_query(Session(body), {'text': 'SELECT count(o) FROM (o:订单)'})['beside'], lean)


if __name__ == '__main__':
    unittest.main()
