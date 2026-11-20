"""A question about 有效订单 answered from a confirmed derived property whose conditions are the view's: the query reads the property, not the orders, so the view's
table is not read, and the check used to refuse it (the product audit of 2026-11-20: 3 of 10 questions, "它是「orders」表上的定义，这条查询没有读这张表" or "模型
没有说明它是怎么用的"). A derived property that leaves out exactly what the view leaves out, on the type the view is about, now counts as using the view; one
that leaves out less (or nothing), or a query that also reads such a property, is refused as before. The same holds when the model names the meanings it
leaves out instead of the view. On the pilot sample; expected numbers are counted from the CSV files here."""
import csv
from collections import defaultdict

from tests import test_derived_new_values as pilot
from tests.test_workspace_questions import AskModel

ALL_AMOUNT = {'type': 'customer', 'english_name': 'all_amount', 'name': '订单金额', 'kind': 'statistic', 'path': ['order_customer'], 'measure': {'column': 'amount'}, 'fn': 'sum'}
NOT_CANCELLED = {**ALL_AMOUNT, 'english_name': 'not_cancelled', 'name': '未取消订单金额', 'conditions': [{'column': 'status_code', 'op': 'is_not', 'label': '已取消'}]}
VALID = {'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}
LEFT_OUT = [{'id': f'orders.status_code={label}', 'direction': 'exclude', 'basis': '有效'} for label in pilot.LEFT_OUT]


def counted():
    customers = {r['customer_id']: r for r in csv.DictReader((pilot.SAMPLE / 'customers.csv').open(encoding='utf-8'))}
    by_city, by_tier, by_customer = defaultdict(int), defaultdict(int), defaultdict(int)
    for r in csv.DictReader((pilot.SAMPLE / 'orders.csv').open(encoding='utf-8')):
        if r['status_code'] in ('0', '4', '5'):
            continue
        c = customers[r['customer_id']]
        by_city[c['city']] += int(r['amount'])
        by_tier[c['tier']] += int(r['amount'])
        by_customer[r['customer_id']] += int(r['amount'])
    return by_city, by_tier, by_customer


BY_CITY, BY_TIER, BY_CUSTOMER = counted()


def query(measure='有效订单金额', **more):
    return {'start': 'customer', 'where': [], 'via': [], 'group_by': None, 'share': None, 'measure': {'field': measure, 'op': 'sum'}, **more}


CITY = query(group_by=['city'], top=1)
TIER_A = query(where=[{'field': 'tier', 'equals': 'A'}])
CUSTOMER_TOP = query(group_by=['customer_id'], top=1)


class DerivedViewAnswerTests(pilot.PilotFoundation):
    def ask(self, item, question, derived=(pilot.VALID_AMOUNT,)):
        model = AskModel({'reasoning': '用已确认的派生属性', **item})
        with self.service(gateway=model) as (base, out):
            ann = self.foundation(base, derived)['ann']
            status, answer = ann.post('/api/workspace/ask', {'question': question})
            self.assertEqual(status, 200, answer)
            return answer

    def test_the_city_ranking_reads_the_derived_property_with_the_views_conditions_and_is_answered(self):
        answer = self.ask({'query': CITY, 'definitions_used': [VALID]}, '哪个城市的有效订单收入最高？')
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))
        top = max(BY_CITY, key=BY_CITY.get)
        self.assertEqual((top, BY_CITY[top]), ('Chengdu', 31040))
        self.assertEqual(answer['answer']['groups'][0][:2], [top, BY_CITY[top]])   # [group, amount, objects]
        self.assertIn('有效订单金额', ''.join(u['how'] for u in answer['understood'] if u['definition'] == '有效订单'))   # how it was used: through the property
        self.assertIn('derived', [d['kind'] for d in answer['definitions']])
        self.assertEqual([(d['dataset'], d['version'], bool(d['imported_at'])) for d in answer['data_as_of']], [('customers', 1, True), ('orders', 1, True)])   # the data it read, by version and when it came

    def test_a_question_that_says_the_view_the_model_did_not_list_is_answered_the_same_way(self):
        answer = self.ask({'query': TIER_A, 'definitions_used': []}, 'A 级客户的有效订单金额合计是多少？')
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))
        self.assertEqual(answer['answer']['measure']['value'], BY_TIER['A'])
        self.assertEqual(BY_TIER['A'], 42380)

    def test_the_customer_ranking_is_answered(self):
        answer = self.ask({'query': CUSTOMER_TOP, 'definitions_used': [VALID]}, '哪个客户的有效订单金额最高？')
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))
        top = max(BY_CUSTOMER, key=BY_CUSTOMER.get)
        self.assertEqual((top, BY_CUSTOMER[top]), ('C001', 7140))
        self.assertEqual(answer['answer']['groups'][0][:2], [top, BY_CUSTOMER[top]])

    def test_the_meanings_the_view_leaves_out_named_one_by_one_are_left_out_by_the_property(self):
        answer = self.ask({'query': TIER_A, 'definitions_used': LEFT_OUT}, 'A 级客户的订单金额合计是多少，不算新建、已取消和已退款的？')
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))
        self.assertEqual(answer['answer']['measure']['value'], BY_TIER['A'])

    def test_a_property_that_counts_every_order_is_not_the_view_and_is_refused(self):
        answer = self.ask({'query': query('订单金额', where=[{'field': 'tier', 'equals': 'A'}]), 'definitions_used': [VALID]}, 'A 级客户的有效订单金额合计是多少？',
                          derived=(pilot.VALID_AMOUNT, ALL_AMOUNT))
        self.assertEqual(answer['status'], 'definition_unmet')

    def test_a_property_that_leaves_out_less_than_the_view_is_refused(self):
        answer = self.ask({'query': query('未取消订单金额', where=[{'field': 'tier', 'equals': 'A'}]), 'definitions_used': [VALID]}, 'A 级客户的有效订单金额合计是多少？',
                          derived=(pilot.VALID_AMOUNT, NOT_CANCELLED))
        self.assertEqual(answer['status'], 'definition_unmet')
        answer = self.ask({'query': query('未取消订单金额', where=[{'field': 'tier', 'equals': 'A'}]), 'definitions_used': LEFT_OUT}, 'A 级客户的订单金额合计是多少，不算新建、已取消和已退款的？',
                          derived=(pilot.VALID_AMOUNT, NOT_CANCELLED))
        self.assertEqual(answer['status'], 'definition_unmet')   # 新建 and 已退款 would be counted

    def test_a_query_that_also_reads_a_property_counting_every_order_is_refused(self):
        mixed = query('订单金额', where=[{'field': '有效订单金额', 'more_than': 0}])
        answer = self.ask({'query': mixed, 'definitions_used': [VALID]}, '有有效订单的客户，订单金额合计是多少？', derived=(pilot.VALID_AMOUNT, ALL_AMOUNT))
        self.assertEqual(answer['status'], 'definition_unmet')


CANCELLED_AMOUNT = {**ALL_AMOUNT, 'english_name': 'cancelled_amount', 'name': '已取消订单金额', 'conditions': [{'column': 'status_code', 'op': 'is', 'label': '已取消'}]}
CANCELLED = [{'id': 'orders.status_code=已取消', 'direction': 'include', 'basis': '已取消'}]


class IncludedMeaningOnATableNotReadTests(pilot.PilotFoundation):
    """The same gap the other way round: a question that wants only 已取消 orders, answered by a query that reads no order (only a property of the customers),
    used to pass the check unread and give the amount of every order. It is refused unless the property it reads keeps exactly that meaning."""
    ask = DerivedViewAnswerTests.ask

    def test_a_property_that_counts_every_order_does_not_answer_a_question_about_cancelled_ones(self):
        answer = self.ask({'query': query('订单金额', group_by=['customer_id'], top=1), 'definitions_used': CANCELLED}, '哪个客户的已取消订单金额最高？',
                          derived=(pilot.VALID_AMOUNT, ALL_AMOUNT))
        self.assertEqual(answer['status'], 'definition_unmet')
        self.assertIn('已取消', answer['reason'])

    def test_a_property_that_keeps_only_cancelled_orders_answers_it(self):
        cancelled = defaultdict(int)
        for r in csv.DictReader((pilot.SAMPLE / 'orders.csv').open(encoding='utf-8')):
            if r['status_code'] == '4':
                cancelled[r['customer_id']] += int(r['amount'])
        answer = self.ask({'query': query('已取消订单金额', group_by=['customer_id'], top=1), 'definitions_used': CANCELLED}, '哪个客户的已取消订单金额最高？',
                          derived=(pilot.VALID_AMOUNT, CANCELLED_AMOUNT))
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))
        top = max(cancelled, key=cancelled.get)
        self.assertEqual(answer['answer']['groups'][0][:2], [top, cancelled[top]])
