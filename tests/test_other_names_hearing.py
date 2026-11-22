"""Which names a question is heard to say, once other names exist.

The longest match wins its span: a name found in a question only inside a longer name of another definition (an object type, a property, a code meaning, a view,
a derived property; by its name or an other name) is not heard there, when either of the two is an other name. With no other names the names are heard as
before. 客户 inside 客户号 is the property's, not the waiting Customer type's; 订单 inside 有效订单 is the view's, and the type behind the view is still named
through it when it waits. A filter's value is said in the question only by the names and other names of the meanings of the column it filters.

The 30 Chinese and 20 English questions are the ones a reviewer asked of the demo with scripted replies that answer correctly; numbers are those of
docs/pilot/sample."""
import csv
import json
import unittest
from unittest import mock

from ontology_poc_generator import demo as demo_mode, other_names
from tests import test_derived_new_values as pilot
from tests.test_demo_mode import a_guest
from tests.test_demo_view_waits import Seeded, change_the_view
from tests.test_object_types import ORDER, VALID
from tests.test_one_number import SUM_AMOUNT, Planted, Scripted, excluded, item, leaving_out, setUpModule, tearDownModule  # noqa: F401  (the caps of the module)
from tests.test_other_names import DemoAsker
from tests.test_token_edit_trust import bearer
from tests.test_workspace_questions import ALL_ORDERS

A = ALL_ORDERS
STATUS = ('New', 'Paid', 'Shipped', 'Delivered', 'Cancelled', 'Refunded')
inc = lambda label, basis: [{'id': f'orders.status_code={label}', 'direction': 'include', 'basis': basis}]
eq = lambda label, q=A: {**q, 'where': [{'field': 'status_code', 'equals': label}]}
MENTION = [{'id': f'orders.status_code={label}', 'direction': 'mention', 'basis': '状态'} for label in STATUS]
VIEW = [{'id': 'Valid orders', 'direction': 'include', 'basis': 'view'}]
rng = lambda f, lo, hi, q=A: {**q, 'where': [{'field': f, **({'at_least': lo} if lo is not None else {}), **({'at_most': hi} if hi is not None else {})}]}
AVG = {**SUM_AMOUNT, 'measure': {'field': 'amount', 'op': 'average'}}
NATURAL_ZH = [
    ('订单总共有多少笔？', item(A)), ('所有订单的总金额是多少？', item()), ('订单的平均金额是多少？', item(AVG)),
    ('各状态的订单数', item({**A, 'group_by': ['status_code']}, MENTION)), ('按状态统计订单金额', item({**SUM_AMOUNT, 'group_by': ['status_code']}, MENTION)),
    ('已取消的订单有多少？', item(eq('Cancelled'), inc('Cancelled', '已取消'))), ('已退款的订单总金额', item(eq('Refunded', SUM_AMOUNT), inc('Refunded', '已退款'))),
    ('不算已取消的订单金额', item(leaving_out('Cancelled'), excluded('Cancelled', basis='不算已取消'))),
    ('除了已取消和已退款以外的订单金额', item(leaving_out('Cancelled', 'Refunded'), excluded('Cancelled', 'Refunded', basis='除了'))),
    ('有效订单的总金额是多少？', item(used=VIEW)), ('有效订单有多少笔？', item(A, VIEW)),
    ('2026年6月的订单金额', item(rng('order_date', '2026-06-01', '2026-06-30', SUM_AMOUNT))), ('6月份下了多少订单？', item(rng('order_date', '2026-06-01', '2026-06-30'))),
    ('每个客户号的订单数', item({**A, 'group_by': ['customer_id']})), ('客户号C015的订单有几笔？', item({**A, 'where': [{'field': 'customer_id', 'equals': 'C015'}]})),
    ('订单号O0001的金额是多少？', item({**SUM_AMOUNT, 'where': [{'field': 'order_id', 'equals': 'O0001'}]})), ('金额超过1000的订单有多少？', item(rng('amount', 1001, None))),
    ('状态如何分布？', item({**A, 'group_by': ['status_code']}, MENTION)), ('已送达的订单金额合计', item(eq('Delivered', SUM_AMOUNT), inc('Delivered', '已送达'))),
    ('已发货但还没送达的订单有多少？', item(eq('Shipped'), inc('Shipped', '已发货'))), ('已付款的订单有几笔？', item(eq('Paid'), inc('Paid', '已付款'))),
    ('新建状态的订单有多少？', item(eq('New'), inc('New', '新建'))), ('订单金额的总和', item()), ('最近一周的订单数？', item(rng('order_date', '2026-06-24', '2026-06-30'))),
    ('每天的订单数', item({**A, 'group_by': ['order_date']})), ('下单日期在5月的订单金额', item(rng('order_date', '2026-05-01', '2026-05-31', SUM_AMOUNT))),
    ('平均每笔订单多少钱？', item(AVG)), ('无效的订单有多少？', item(leaving_out('Paid', 'Shipped', 'Delivered', query=A), excluded('Paid', 'Shipped', 'Delivered', basis='无效'))),
    ('金额在500到1000之间的订单数', item(rng('amount', 500, 1000))), ('客户号为空的订单有几笔？', item({**A, 'where': [{'field': 'customer_id', 'equals': ''}]})),
]
NATURAL_EN = [
    ('How many orders are there?', item(A)), ('What is the total order amount?', item()), ('Average order amount?', item(AVG)),
    ('Orders by status', item({**A, 'group_by': ['status_code']}, MENTION)), ('Amount by status', item({**SUM_AMOUNT, 'group_by': ['status_code']}, MENTION)),
    ('How many cancelled orders?', item(eq('Cancelled'), inc('Cancelled', 'cancelled'))), ('Total amount of refunded orders', item(eq('Refunded', SUM_AMOUNT), inc('Refunded', 'refunded'))),
    ('Total amount excluding cancelled orders', item(leaving_out('Cancelled'), excluded('Cancelled', basis='excluding'))),
    ('What is the total amount of valid orders?', item(used=VIEW)), ('How many valid orders?', item(A, VIEW)),
    ('Order amount in June 2026', item(rng('order_date', '2026-06-01', '2026-06-30', SUM_AMOUNT))), ('Orders per customer id', item({**A, 'group_by': ['customer_id']})),
    ('Amount of order O0001', item({**SUM_AMOUNT, 'where': [{'field': 'order_id', 'equals': 'O0001'}]})), ('Orders above 1000', item(rng('amount', 1001, None))),
    ('How many delivered orders?', item(eq('Delivered'), inc('Delivered', 'delivered'))), ('How many paid orders?', item(eq('Paid'), inc('Paid', 'paid'))),
    ('Orders per day', item({**A, 'group_by': ['order_date']})), ('Average amount per order in May', item(rng('order_date', '2026-05-01', '2026-05-31', AVG))),
    ('How many orders were placed in order to test?', item(A)), ('Orders with amount between 500 and 1000', item(rng('amount', 500, 1000))),
]
HELD_BACK = ('refused', 'definition_unmet')


def answer_of(body):
    return json.dumps({k: body.get(k) for k in ('status', 'answer', 'evidence')}, ensure_ascii=False, sort_keys=True)


class NaturalQuestionsTests(unittest.TestCase, DemoAsker):
    """The seeded demo, Customer waiting for a second look: every natural question with a correct reply is answered, with the number it has when other names are
    not heard."""

    @classmethod
    def setUpClass(cls):
        cls.demo = Seeded().__enter__()
        cls.guest = a_guest(cls.demo.base)

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def test_none_of_the_thirty_chinese_questions_is_refused_and_the_fifty_end_as_without_other_names(self):
        for who in (self.guest, self.demo.admin()):
            for question, reply in [*NATURAL_ZH, *NATURAL_EN]:
                with self.subTest(question=question):
                    on = self.ask(self.demo, who, question, reply)[1]
                    off = self.ask(self.demo, who, question, reply, heard=False)[1]
                    if (question, reply) in NATURAL_ZH:
                        self.assertNotIn(on['status'], HELD_BACK, on.get('reason'))
                    self.assertEqual((on['status'], json.loads(answer_of(on))['answer']), (off['status'], json.loads(answer_of(off))['answer']))   # "Orders per customer id" says Customer's English name: refused, as without other names
        self.assertEqual((len(NATURAL_ZH), len(NATURAL_EN)), (30, 20))

    def test_a_short_name_inside_a_longer_one_of_another_definition_is_not_heard_and_on_its_own_it_is(self):
        for question in ('客户号C015的订单有几笔？', '每个客户号的订单数', '客户名称是什么？'):   # 客户 inside the properties' 客户号 and 客户名称
            status, body, _, requests = self.ask(self.demo, self.guest, question, item(A))
            self.assertNotEqual(body['status'], 'refused', question)
            self.assertNotEqual(requests, '[]', question)
        for question in ('客户号C015的客户在哪个城市？', '客户有多少个？'):   # 客户 on its own as well: Customer is heard, and it waits
            status, body, _, requests = self.ask(self.demo, self.guest, question, item(A))
            self.assertEqual((body['status'], requests), ('refused', '[]'), question)

    def test_a_short_name_inside_a_longer_one_of_another_definition_is_heard_when_other_names_are_not(self):
        status, body, _, _ = self.ask(self.demo, self.guest, '客户号C015的订单有几笔？', item({**A, 'where': [{'field': 'customer_id', 'equals': 'C015'}]}), heard=False)
        self.assertEqual((body['status'], body['answer']['total']), ('answered', 2))   # as on main: 客户 is no name of anything when other names are not heard

    def test_the_demos_own_names_sit_inside_one_another_only_where_the_longer_one_is_heard_instead(self):
        from ontology_poc_generator.demo import OTHER_NAMES
        names = {('type', k, n) for k, ns in OTHER_NAMES['types'].items() for n in ns} | {('view', k, n) for k, ns in OTHER_NAMES['views'].items() for n in ns}
        names |= {('meaning', k, n) for k, ns in OTHER_NAMES['meanings'].items() for n in ns}
        names |= {('property', f'{t}.{c}', n) for t, cols in OTHER_NAMES['properties'].items() for c, ns in cols.items() for n in ns}
        inside = sorted({(a[2], b[2]) for a in names for b in names if a[2] != b[2] and a[2] in b[2]})
        self.assertEqual(inside, [('客户', '客户号'), ('客户', '客户名称'), ('订单', '有效订单'), ('订单', '订单号')])
        for question, reply in (('订单号O0001的金额是多少？', item({**SUM_AMOUNT, 'where': [{'field': 'order_id', 'equals': 'O0001'}]})), ('有效订单的总金额是多少？', item(used=VIEW))):
            self.assertEqual(self.ask(self.demo, self.guest, question, reply)[1]['status'], 'answered', question)


class WaitingTests(unittest.TestCase, DemoAsker):
    """订单 inside 有效订单: "有效订单…" is heard as the view; it is refused when the view waits and when the type under it waits (named through the view), and "订单…"
    alone never names the view."""

    def test_the_view_waits(self):
        demo = Seeded().__enter__()
        try:
            change_the_view(demo.admin('en'))
            for who in (demo.builder('en'), a_guest(demo.base, 'en')):
                body = self.ask(demo, who, '有效订单的总金额是多少？', item())[1]
                self.assertEqual(body['status'], 'refused')
                self.assertEqual(self.ask(demo, who, '订单号O0001的金额是多少？', item({**SUM_AMOUNT, 'where': [{'field': 'order_id', 'equals': 'O0001'}]}))[1]['status'], 'answered')
        finally:
            demo.__exit__(None, None, None)

    def test_the_type_under_the_view_waits(self):
        demo = Seeded().__enter__()
        try:
            admin = demo.admin('en')
            now = admin.call('GET', '/api/workspace/types/order')[1]
            payload = {'id': 'order', 'version': now['version'], 'name': now['name'], 'description': '', 'dataset': 'orders', 'key': now['key'],
                       'properties': [{'column': p['column'], 'type': 'text' if p['column'] == 'amount' else p['type'], 'enum': p['enum']} for p in now['properties']]}
            self.assertEqual(admin.call('POST', '/api/workspace/types/update', payload)[1]['state'], 'checked')
            body = self.ask(demo, demo.builder('en'), '有效订单的总金额是多少？', item())[1]
            self.assertEqual(body['status'], 'refused')
            self.assertTrue({('type', 'Order'), ('view', 'Valid orders')} <= {(d['kind'], d['name']) for d in body['refusal']['definitions']}, body['refusal'])
        finally:
            demo.__exit__(None, None, None)


class EnglishOtherNamesTests(unittest.TestCase, DemoAsker):
    """An other name in letters is heard as a whole word, as a name is (an English one also in its plural), never inside another word; in full width too."""

    @classmethod
    def setUpClass(cls):
        names = demo_mode.OTHER_NAMES
        with mock.patch.object(demo_mode, 'OTHER_NAMES', {**names, 'types': {**names['types'], 'customer': ['客户', 'buyer']}, 'views': {'Valid orders': ['有效订单', 'good orders']}}):
            cls.demo = Seeded().__enter__()
        change_the_view(cls.demo.admin('en'))
        cls.guest = a_guest(cls.demo.base, 'en')

    @classmethod
    def tearDownClass(cls):
        cls.demo.__exit__(None, None, None)

    def refused(self, question):
        return self.ask(self.demo, self.guest, question, item(A))[1]['status'] == 'refused'

    def test_whole_words_only(self):
        self.assertTrue(self.refused('How many buyers are there by city?'))
        self.assertTrue(self.refused('Total of the good orders'))
        self.assertTrue(self.refused('Total of the ｇｏｏｄ　ｏｒｄｅｒｓ'))   # full width
        self.assertFalse(self.refused('How many rebuyers placed orders?'))
        self.assertFalse(self.refused('Total of the goodorders'))



class EnglishMeaningTests(Planted):
    def test_a_meanings_other_name_in_letters_is_a_whole_word(self):
        from tests.test_object_types import MEANINGS
        model = Scripted(item(A))
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            order = {**ORDER, 'enums': {'状态码': [{**m, **({'other_names': ['voided']} if m['label'] == '已取消' else {})} for m in MEANINGS]}}
            self.assertEqual(team['ann'].post('/api/workspace/types', order)[0], 200)
            self.confirm(team['bob'], 'order', '状态码')
            self.confirm(team['bob'], 'order')
            self.assertEqual(self.ask(team['ann'], 'How many orders were voided?')[1]['status'], 'definition_unmet')   # said, and the model did not say how it used it
            self.assertEqual(self.ask(team['ann'], 'How many orders were unvoidedly placed?')[1]['status'], 'answered')


PAY = {'0': '未付', '1': '已付款'}


def orders_with_pay() -> tuple[str, int, int]:
    """The sample's orders with a pay_code column (the first 33 rows paid), and how many rows have pay_code 1 and status_code 1."""
    rows = list(csv.DictReader((pilot.SAMPLE / 'orders.csv').open(encoding='utf-8')))
    out = [','.join([*rows[0].keys(), 'pay_code'])] + [','.join([*r.values(), '1' if i < 33 else '0']) for i, r in enumerate(rows)]
    return '\n'.join(out) + '\n', 33, sum(r['status_code'] == '1' for r in rows)


class ColumnTests(Planted):
    """A filter's value is said in the question only by the meanings of the column it filters: pay_code 1 = 已付款 (also 已付清), status_code 1 = 已付款."""

    def world(self, base, status_other=()):
        team = self.people(base, 'ann', 'bob')
        text, _, _ = orders_with_pay()
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [pilot.part('orders.csv', text)]})[0], 200)
        order = {**pilot.ORDER, 'properties': [*pilot.ORDER['properties'], {'column': 'pay_code', 'enum': True}],
                 'enums': {'status_code': [{**e, **({'other_names': list(status_other)} if e['label'] == '已付款' and status_other else {})} for e in pilot.ORDER['enums']['status_code']],
                           'pay_code': [{'value': v, 'label': label, **({'other_names': ['已付清']} if v == '1' else {})} for v, label in PAY.items()]}}
        status, body = team['ann'].post('/api/workspace/types', order)
        self.assertEqual(status, 200, body)
        for column in ('status_code', 'pay_code'):
            self.confirm(team['bob'], 'order', column)
        self.confirm(team['bob'], 'order')
        return team

    def filters(self, client, model, question, column):
        model.replies = [item({**A, 'where': [{'field': column, 'equals': '已付款'}]}, [{'id': f'orders.{column}=已付款', 'direction': 'include', 'basis': '已付清'}])]
        status, body = client.post('/api/workspace/ask', {'question': question})
        self.assertEqual(status, 200, body)
        return body['answer']['total'], [f.get('not_in_question') for f in body['evidence']['filters']]

    def test_the_other_column_never_removes_the_mark_and_its_own_does(self):
        _, paid, status_paid = orders_with_pay()
        model = Scripted(item(A))
        with self.service(gateway=model) as (base, out):
            ann = self.world(base)['ann']
            self.assertEqual(self.filters(ann, model, '已付清的订单有几笔？', 'status_code'), (status_paid, [True]))   # answered from the other column: still marked as the model's
            self.assertEqual(self.filters(ann, model, '已付清的订单有几笔？', 'pay_code'), (paid, [None]))   # its own column's other name: said
        self.assertEqual((paid, status_paid), (33, 12))

    def test_the_mirror_a_status_other_name_does_not_cover_a_pay_filter(self):
        model = Scripted(item(A))
        with self.service(gateway=model) as (base, out):
            ann = self.world(base, status_other=['付过钱'])['ann']
            self.assertEqual(self.filters(ann, model, '付过钱的订单有几笔？', 'pay_code')[1], [True])
            self.assertEqual(self.filters(ann, model, '付过钱的订单有几笔？', 'status_code')[1], [None])


class MainNameInsideAnOtherNameTests(pilot.PilotFoundation):
    """The pilot's type 客户 (its name, not an other name) inside the other name 客户号 of 订单's customer_id: a name is never muted, so it is heard there as main
    hears it inside a longer name, and the question is refused while Customer waits."""

    def test_the_customer_type_waits(self):
        model = Scripted(item(A))
        with self.service(gateway=model) as (base, out):
            ann = self.foundation(base)['ann']
            now = ann.get('/api/workspace/types/order')[1]
            props = [{'column': p['column'], **({'other_names': ['客户号']} if p['column'] == 'customer_id' else {})} for p in now['properties'] if p['column'] != 'order_id']
            props = [{**p, **({'enum': True} if p['column'] == 'status_code' else {})} for p in props]
            status, body = ann.post('/api/workspace/types/update', {**pilot.ORDER, 'id': 'order', 'version': now['version'], 'properties': props})
            self.assertEqual(status, 200, body)
            now = ann.get('/api/workspace/types/customer')[1]
            token = ann.post('/api/auth/tokens', {'label': 'agent'})[1]['token']   # an edit made with a token puts the confirmed Customer forward again
            status, body = ann.post('/api/workspace/types/update', {**pilot.CUSTOMER, 'id': 'customer', 'version': now['version'], 'description': 'changed'}, **bearer(token))
            self.assertEqual((status, body.get('state')), (200, 'checked'), body)
            model.replies = [item({'start': 'order', 'where': [{'field': 'customer_id', 'equals': 'C015'}], 'via': [], 'group_by': None, 'share': None, 'measure': None})]
            self.assertEqual(ann.post('/api/workspace/ask', {'question': '客户号C015的订单有几笔？'})[1]['status'], 'refused')   # 客户 is the type's name: heard, as on main
            self.assertEqual(ann.post('/api/workspace/ask', {'question': '客户号C015的客户在哪个城市？'})[1]['status'], 'refused')
            with mock.patch.object(other_names, 'HEARD', False):
                self.assertEqual(ann.post('/api/workspace/ask', {'question': '客户号C015的订单有几笔？'})[1]['status'], 'refused')


class SaveTests(Planted):
    """What is refused when saved, beyond one scope: an other name may not equal a name or other name of a definition of another kind (a type, a view, a derived
    property, a meaning, a property), nor a meaning's another column's; a property's may equal another type's property's. Nothing invisible is kept in a name."""

    def world(self, base):
        team = self.team(base)
        self.confirmed_orders(team)
        self.assertEqual(team['ann'].post('/api/workspace/types/views', VALID)[0], 200)
        self.confirm_view(team['bob'], 'order', '有效订单')
        return team

    def update_type(self, client, **change):
        now = client.get('/api/workspace/types/order')[1]
        return client.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': now['version'], **change})

    def test_equal_names_across_kinds_are_refused(self):
        with self.service(gateway=Scripted(item(A))) as (base, out):
            ann = self.world(base)['ann']
            meaning = lambda names: ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '2', 'label': '已取消', 'other_names': names}]})
            self.assertEqual(meaning(['订单'])[0], 409)   # the type's name
            self.assertEqual(meaning(['有效订单'])[0], 409)   # the view's name
            props = lambda names: [{'column': '订单号'}, {'column': '金额', 'other_names': names}, {'column': '状态码', 'enum': True}]
            self.assertEqual(self.update_type(ann, properties=props(['有效订单']))[0], 409)
            self.assertEqual(self.update_type(ann, properties=props(['已取消']))[0], 409)   # a meaning's label
            self.assertEqual(self.update_type(ann, other_names=['金额'])[0], 409)   # its own property's name
            self.assertEqual(self.update_type(ann, properties=props(['货款']))[0], 200)

    def test_invisible_characters_are_refused(self):
        with self.service(gateway=Scripted(item(A))) as (base, out):
            ann = self.world(base)['ann']
            for name in ('销​售单', '销售­单', '销售单‮'):
                self.assertEqual(self.update_type(ann, other_names=[name])[0], 400, repr(name))


if __name__ == '__main__':
    unittest.main()
