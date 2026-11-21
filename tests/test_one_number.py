"""Which rows a question's number covers: the two things code decides, and everything else as before.

1. The question names no view and the model's reply applies exactly one confirmed view on the type it counts (by name, or by writing exactly its conditions)
   or no condition: the number covers every row the asker may read, and each confirmed view on that type the asker may see has its own number beside it.
2. The question names a confirmed view and the model's reply includes it or writes conditions that go its way: the view's confirmed conditions are applied in
   place of the model's; a named view the reply says nothing about, or goes against, is refused. Code never applies a view on its name alone.
Any other condition the model writes (a value, a meaning, a range) is applied as written, as before, and these tests check that the number is then the one SQL
gives for that condition. Expected numbers are worked out here with SQL on the sample CSV files (docs/pilot/sample), never taken from the service."""
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


def where_amount(where: str) -> int:
    return sql(f'SELECT SUM(CAST(amount AS INTEGER)) FROM orders WHERE {where}')


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

    def test_a_question_that_names_no_view_answered_with_one_view_or_none_covers_every_row_with_the_view_beside_it(self):
        replies = {
            'applies the view by name': [item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': '销售额'}])],
            'applies nothing': [item()],
            'writes exactly the view\'s conditions, saying them': [item(leaving_out('New', 'Cancelled', 'Refunded'), excluded('New', 'Cancelled', 'Refunded', basis='销售额'))],
            'writes exactly the view\'s conditions, saying nothing': [item(leaving_out('New', 'Cancelled', 'Refunded'))],
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

    def test_any_other_filter_the_model_writes_is_applied_as_before_and_nothing_is_beside_it(self):
        cases = {'leaves out less than the view': (item(leaving_out('Cancelled'), excluded('Cancelled', basis='销售额')), where_amount("status_code <> '4'")),
                 'leaves out two of its three': (item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='销售额')), where_amount("status_code NOT IN ('4', '5')")),
                 'a range on the amount': (item({**SUM_AMOUNT, 'where': [{'field': 'amount', 'at_least': 1000}]}), where_amount('CAST(amount AS INTEGER) >= 1000'))}
        for case, (said, expected) in cases.items():
            with self.subTest(case=case):
                body, _ = self.ask('销售额是多少？', said)
                self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', expected), body.get('reason'))
                self.assertIsNone(body.get('beside'))
        self.assertEqual(where_amount("status_code NOT IN ('4', '5')"), 124790)
        body, _ = self.ask('销售额是多少？', item(leaving_out('Cancelled', 'Refunded')))   # as on main: a filter on confirmed meanings with no direction is refused
        self.assertEqual(body['status'], 'definition_unmet', body)

    def test_a_reply_that_is_never_usable_gives_no_number_and_the_model_is_asked_twice_at_most(self):
        body, asked = self.ask('销售额是多少？', 'not json')
        self.assertEqual((body['status'], asked), ('no_query', 2))
        self.assertNotIn('answer', body)

    def test_a_question_that_names_the_view_gets_the_views_number_when_the_model_includes_it_or_goes_its_way(self):
        replies = {
            'includes the view': [item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}])],
            'writes part of it, saying it': [item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='Valid orders'))],
            'writes part of it, saying nothing': [item(leaving_out('Cancelled', 'Refunded'))],
            'returns nothing usable once': ['not json', item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}])],
        }
        for question in ('Valid orders 的总金额是多少？', 'What is the total amount of valid orders?'):
            for case, said in replies.items():
                with self.subTest(question=question, case=case):
                    body, asked = self.ask(question, *said)
                    self.assertGreaterEqual(asked, 1)   # never answered by code alone
                    self.assertEqual(headline(body), ('answered', VALID_AMOUNT, VALID_COUNT), body.get('reason'))
                    self.assertEqual([(d['kind'], d['name'], d['confirmed_by']) for d in body['definitions'] if d['kind'] == 'view'], [('view', 'Valid orders', 'Demo builder')])
                    self.assertIsNone(body.get('beside'))
        for case, said in {'writes nothing about it': item(), 'writes the other rows': item({**SUM_AMOUNT, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}]})}.items():
            with self.subTest(case=case):   # no word on the view, or a filter that goes against it: code does not guess the direction, it refuses
                body, _ = self.ask('Valid orders 的总金额是多少？', said)
                self.assertEqual(body['status'], 'definition_unmet', body)
                self.assertNotIn('answer', body)

    def test_a_range_on_top_of_a_named_view_is_applied_as_the_model_wrote_it(self):
        said = item({**SUM_AMOUNT, 'where': [{'field': 'amount', 'at_least': 1000}]}, [{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}])
        body, _ = self.ask('Valid orders 的总金额是多少？', said)
        self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', where_amount(f'{VALID_SQL} AND CAST(amount AS INTEGER) >= 1000')))
        self.assertEqual(body['answer']['measure']['value'], 94960)

    def test_a_question_that_says_valid_orders_in_another_language_is_answered_as_before(self):
        body, _ = self.ask('有效订单的总金额是多少？', item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='有效订单')))
        self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', 124790))   # the model's own filter, said under the number as the model's
        self.assertIsNone(body.get('beside'))

    def test_a_meaning_said_in_another_language_is_counted_by_the_models_filter_as_before_never_all_orders(self):
        cancelled = sql("SELECT COUNT(*) FROM orders WHERE status_code = '4'")
        self.assertEqual(cancelled, 19)
        query = {**ALL_ORDERS, 'where': [{'field': 'status_code', 'equals': 'Cancelled'}]}
        for question, basis in (('已取消的订单有多少？', '已取消'), ('有多少订单被取消了', '被取消')):
            for used in ([{'id': 'orders.status_code=Cancelled', 'direction': 'include', 'basis': basis}], []):
                with self.subTest(question=question, basis=bool(used)):
                    body, _ = self.ask(question, item(query, used))
                    if used:
                        self.assertEqual((body['status'], body['answer']['total']), ('answered', cancelled), body.get('reason'))
                    else:   # as on main: a filter on a confirmed meaning the model gave no direction for is refused, never all orders
                        self.assertNotEqual((body.get('answer') or {}).get('total'), ALL_COUNT, body)
                        self.assertIn(body['status'], ('answered', 'definition_unmet'), body)
                        if body['status'] == 'answered':
                            self.assertEqual(body['answer']['total'], cancelled)


class CommonWordViewTests(unittest.TestCase):
    """Views named with common words (All keeps Paid, Big keeps Delivered, Now keeps Shipped): the word in an ordinary question is not the model applying the view."""

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

    def test_a_view_named_by_a_common_word_is_never_applied_by_code_alone(self):
        count = {**ALL_ORDERS}
        wrong = {'What is the total amount of all orders?': (item(), where_amount("status_code = '1'")), 'How big is the total amount?': (item(), where_amount("status_code = '3'")),
                 'How many orders are there now?': (item(count), sql("SELECT COUNT(*) FROM orders WHERE status_code = '2'"))}
        self.demo.model.__class__ = Scripted
        for question, (said, by_the_view) in wrong.items():
            with self.subTest(question=question):
                self.demo.model.replies = [said]
                before = len(self.demo.model.requests)
                status, body = self.guest.call('POST', '/api/workspace/ask', {'question': question})
                self.assertEqual((status, len(self.demo.model.requests) - before), (200, 1))
                self.assertEqual(body['status'], 'definition_unmet', body)   # as on main: the question says the view's name and the model said nothing of it
                self.assertNotEqual(((body.get('answer') or {}).get('measure') or {}).get('value', (body.get('answer') or {}).get('total')), by_the_view)
        self.assertEqual([where_amount("status_code = '1'"), where_amount("status_code = '3'")], [10770, 72240])


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
            model.item = item()
            status, body = who.call('POST', '/api/workspace/ask', {'question': 'What is the total amount?'})
            self.assertEqual(headline(body), ('answered', ALL_AMOUNT, ALL_COUNT))
            self.assertIsNone(body.get('beside'))
            model.item = item(used=[{'id': 'Valid orders', 'direction': 'include', 'basis': 'Valid orders'}])


class PilotTests(pilot.PilotFoundation):
    """The pilot sample with the view 有效订单 named in Chinese, as the questions are, and the derived property 有效订单金额 on Customer."""

    def ask(self, question, *replies, orders=None):
        model = Scripted(*replies)
        with self.service(gateway=model) as (base, out):
            ann = self.foundation(base, orders=orders)['ann']
            status, body = ann.post('/api/workspace/ask', {'question': question})
            self.assertEqual(status, 200, body)
            return body, len(model.requests)

    def test_with_an_order_whose_customer_is_missing_the_named_view_gives_the_rows_total_or_is_refused_never_the_customers_sum(self):
        orders = with_orphan()
        rows = sql(f'SELECT SUM(CAST(amount AS INTEGER)) FROM orders WHERE {VALID_SQL}', orders)
        self.assertEqual(rows, 169810)
        view = [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}]
        every_customer = {'start': 'customer', 'where': [{'field': 'tier', 'equals': ['A', 'B', 'C']}], 'via': [], 'group_by': None, 'share': None,
                          'measure': {'field': '有效订单金额', 'op': 'sum'}}   # a filter every customer matches
        for case, said in {'reads the orders through the view': item(used=view), 'reads the orders and writes the filter itself': item(leaving_out('新建', '已取消', '已退款'), []),
                           'reads the orders and leaves out less than the view': item(leaving_out('已取消'), [])}.items():
            with self.subTest(case=case):
                body, _ = self.ask('有效订单的总金额是多少？', said, orders=orders)
                self.assertEqual((body['status'], body['answer']['measure']['value']), ('answered', rows), body.get('reason'))
        body, _ = self.ask('有效订单的总金额是多少？', item(every_customer, view), orders=orders)
        self.assertNotEqual((body.get('answer') or {}).get('measure', {}).get('value'), 119810)
        self.assertNotEqual(body['status'], 'answered', body)

    def test_a_condition_said_in_another_language_than_its_value_is_applied_as_the_model_wrote_it(self):
        chengdu = {'start': 'customer', 'where': [{'field': 'city', 'equals': 'Chengdu'}], 'via': [], 'group_by': None, 'share': None, 'measure': None}
        both = {**chengdu, 'where': [*chengdu['where'], {'field': 'tier', 'equals': 'A'}]}
        tier_a = {**chengdu, 'where': [{'field': 'tier', 'equals': 'A'}]}
        for question, query, expected in (('成都的客户有多少个？', chengdu, "city = 'Chengdu'"), ('成都 A 级客户有多少个？', both, "city = 'Chengdu' AND tier = 'A'"),
                                          ('How many A customers?', tier_a, "tier = 'A'")):
            with self.subTest(question=question):
                body, asked = self.ask(question, item(query))
                self.assertEqual((body['status'], body['answer']['total'], asked), ('answered', sql(f'SELECT COUNT(*) FROM customers WHERE {expected}'), 1), body.get('reason'))
        self.assertEqual([sql(f"SELECT COUNT(*) FROM customers WHERE {w}") for w in ("city = 'Chengdu'", "city = 'Chengdu' AND tier = 'A'", "tier = 'A'")], [9, 5, 13])

    def test_no_question_is_answered_without_the_model(self):
        for question in ('What is the amount of an order?', '客户有多少？'):
            with self.subTest(question=question):
                body, asked = self.ask(question, 'not json')
                self.assertEqual((body['status'], asked), ('no_query', 2))


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
        with self.service(gateway=Scripted(item(ALL_ORDERS))) as (base, out):
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
            self.assertTrue(all('answer' in v for v in body['beside']['views']))
            model.replies = [item(grouped, [{'id': f'订单.状态码={l}', 'direction': 'mention', 'basis': '状态'} for l in labels])]
            body = self.ask(team['ann'], '各状态码的订单各有多少？')[1]
            self.assertEqual(body['status'], 'answered', body)
            self.assertEqual([v['name'] for v in body['beside']['views']], names[:5])
            self.assertFalse(any('answer' in v for v in body['beside']['views']))

    def test_a_view_the_question_asks_for_by_its_meaning_is_applied_and_one_it_does_not_is_beside(self):
        model = Scripted(item(ALL_ORDERS, [{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '不算已取消'}]))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            for said in (item(ALL_ORDERS, [{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '不算已取消'}]),
                         item({**ALL_ORDERS, 'where': [{'field': '状态码', 'not_equals': ['2']}]}, [{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '不算已取消'}])):
                model.replies = [said]
                body = self.ask(team['ann'], '不算已取消的订单有多少？')[1]   # the question says 已取消: the view's conditions are what it asks for
                self.assertEqual((body['status'], body['answer']['total']), ('answered', 144), body.get('reason'))
                self.assertIsNone(body.get('beside'))
            model.replies = [item({**ALL_ORDERS, 'where': [{'field': '状态码', 'not_equals': ['2']}]}, [{'id': '订单.状态码=已取消', 'direction': 'exclude', 'basis': '销售总额'}])]
            body = self.ask(team['ann'], '订单的销售总额是多少？')[1]   # exactly 有效订单's conditions, which the question does not say: every row, the view beside it
            self.assertEqual((body['status'], body['answer']['total']), ('answered', 160))
            self.assertEqual([(v['name'], v['answer']['total']) for v in body['beside']['views']], [('有效订单', 144)])

    def test_a_named_view_on_a_column_whose_values_are_kept_from_the_model_is_applied_by_code_or_refused_never_all_rows(self):
        """状态码 is marked "don't send values": the model is never told its codes or meanings, nor what 有效订单 keeps. A question that names 有效订单 gets the
        view's own number (code applies its stored conditions, as a board does), for a builder and a viewer, or a refusal that says why; never all 160 orders."""
        include = [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}]
        model = Scripted(item(ALL_ORDERS, include))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.with_valid(team)
            self.assertEqual(team['ann'].post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)
            for who in ('ann', 'vera'):
                model.replies = [item(ALL_ORDERS, include)]
                status, body = self.ask(team[who], '有效订单一共下了几单？')
                self.assertEqual((status, body['status'], body['answer']['total']), (200, 'answered', 144), (who, body))
                self.assertEqual([d['name'] for d in body['definitions'] if d['kind'] == 'view'], ['有效订单'])
                self.assertIsNone(body.get('beside'))
                told = json.dumps(model.requests[-1], ensure_ascii=False)
                self.assertIn('有效订单', told)   # by its name, so the model can say how the question uses it
                for secret in ('已取消', '已交付', '生产中'):
                    self.assertNotIn(secret, told)
                for said in (item(ALL_ORDERS, []), item(ALL_ORDERS, [{'id': '有效订单', 'direction': 'exclude', 'basis': '不属于有效订单'}])):
                    model.replies = [said]
                    status, body = self.ask(team[who], '有效订单一共下了几单？')
                    self.assertEqual((status, body['status']), (200, 'definition_unmet'), (who, body))
                    self.assertNotIn('answer', body)
                    self.assertIn('有效订单', body['reason'])

    def test_a_saved_answer_says_when_a_view_beside_it_has_changed(self):
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
            reopened = ann.get(f'/api/workspace/ask/{saved["id"]}')[1]
            self.assertIn('有效订单', [c['name'] for c in reopened['changed']])


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
        body = {'status': 'answered', 'answer': {'total': 160}, 'beside': {'views': [{'id': 'objview:有效订单', 'version': 1, 'name': '有效订单', 'answer': {'total': 144}, 'confirmed_by': 'Bob'}], 'more': []},
                'definitions': [], 'query_text': 'SELECT count(o) FROM (o:订单)'}
        lean = {'views': [{'name': '有效订单', 'confirmed_by': 'Bob', 'answer': {'total': 144}}]}   # no id or version for an agent
        self.assertEqual(mcp_server.ask(Session(body), {'question': 'q'})['beside'], lean)
        self.assertEqual(mcp_server.ontopoc_query(Session(body), {'text': 'SELECT count(o) FROM (o:订单)'})['beside'], lean)


if __name__ == '__main__':
    unittest.main()
