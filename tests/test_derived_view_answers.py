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

    def test_a_question_that_says_the_view_the_model_did_not_list_is_refused_as_before(self):
        answer = self.ask({'query': TIER_A, 'definitions_used': []}, 'A 级客户的有效订单金额合计是多少？')
        self.assertEqual(answer['status'], 'definition_unmet')   # the model must say the view is included; code does not decide the direction for it
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


class DirectionTests(pilot.PilotFoundation):
    """Reading the derived property counts as using the view only when the model says the question includes the view. Code does not read the question for
    negation: with no direction (the question may ask for the complement) or "mention" (the question does not pick rows by it) the answer is refused, as when
    the query reads neither (review of e3cc20d, B-1 and B-2)."""
    ask = DerivedViewAnswerTests.ask

    def test_an_explicit_include_is_answered(self):
        answer = self.ask({'query': TIER_A, 'definitions_used': [VALID]}, 'A 级客户的有效订单金额合计是多少？')
        self.assertEqual((answer['status'], answer['answer']['measure']['value']), ('answered', BY_TIER['A']))

    def test_no_direction_is_refused_even_when_the_property_has_the_views_conditions(self):
        answer = self.ask({'query': TIER_A, 'definitions_used': []}, 'A 级客户里，不属于有效订单的那些订单金额合计是多少？')   # the complement: 42,380 would be wrong
        self.assertEqual(answer['status'], 'definition_unmet')
        self.assertNotIn('answer', answer)

    def test_a_view_only_mentioned_is_refused_when_the_query_reads_rows_picked_by_it(self):
        answer = self.ask({'query': TIER_A, 'definitions_used': [{**VALID, 'direction': 'mention'}]}, 'A 级客户的订单金额合计是多少？（有效订单另说）')   # every order is asked for
        self.assertEqual(answer['status'], 'definition_unmet')

    def test_every_property_read_on_the_table_must_match_whichever_comes_first(self):
        late = {**ALL_AMOUNT, 'english_name': 'z_all'}   # sorts after valid_amount, so the matching one is met first
        mixed = query('订单金额', where=[{'field': '有效订单金额', 'more_than': 0}])
        answer = self.ask({'query': mixed, 'definitions_used': [VALID]}, '有有效订单的客户，订单金额合计是多少？', derived=(pilot.VALID_AMOUNT, late))
        self.assertEqual(answer['status'], 'definition_unmet')


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


class UnlistedMeaningThroughADerivedPropertyTests(pilot.PilotFoundation):
    """The meanings side of B-1 (re-review 2026-11-20, P7): a question that says a code meaning (已取消), a model that lists nothing, and a query that reads only a
    derived property of the customers. The property picks order rows by its own conditions, so the number answers some other question (42,380 is the valid
    amount, not the cancelled one). With no direction from the model the answer is refused, as for a view."""
    ask = DerivedViewAnswerTests.ask

    def test_a_meaning_the_question_says_and_the_model_did_not_list_is_refused_when_the_query_reads_a_derived_property(self):
        answer = self.ask({'query': TIER_A, 'definitions_used': []}, 'A 级客户里已取消的订单金额合计是多少？')
        self.assertEqual(answer['status'], 'definition_unmet')
        self.assertNotIn('answer', answer)
        self.assertIn('已取消', answer['reason'])
        answer = self.ask({'query': query('订单金额', where=[{'field': 'tier', 'equals': 'A'}]), 'definitions_used': []}, 'A 级客户里已取消的订单金额合计是多少？',
                          derived=(pilot.VALID_AMOUNT, ALL_AMOUNT))
        self.assertEqual(answer['status'], 'definition_unmet')   # a property that counts every order is not "cancelled" either

    def test_a_question_that_says_no_meaning_is_answered_from_the_property_as_before(self):
        answer = self.ask({'query': query('订单金额', where=[{'field': 'tier', 'equals': 'A'}]), 'definitions_used': []}, 'A 级客户的订单金额合计是多少？',
                          derived=(pilot.VALID_AMOUNT, ALL_AMOUNT))
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))

    def test_the_meaning_listed_as_included_with_a_property_that_keeps_only_it_is_answered_as_before(self):
        answer = self.ask({'query': query('已取消订单金额', where=[{'field': 'tier', 'equals': 'A'}]), 'definitions_used': CANCELLED}, 'A 级客户里已取消的订单金额合计是多少？',
                          derived=(pilot.VALID_AMOUNT, CANCELLED_AMOUNT))
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))


def tier_a_cancelled() -> int:
    tiers = {r['customer_id']: r['tier'] for r in csv.DictReader((pilot.SAMPLE / 'customers.csv').open(encoding='utf-8'))}
    return sum(int(r['amount']) for r in csv.DictReader((pilot.SAMPLE / 'orders.csv').open(encoding='utf-8')) if r['status_code'] == '4' and tiers[r['customer_id']] == 'A')


CANCELLED_A = query('已取消订单金额', where=[{'field': 'tier', 'equals': 'A'}])
MISNAMED = {**CANCELLED_AMOUNT, 'english_name': 'misnamed', 'conditions': [{'column': 'status_code', 'op': 'is_not', 'label': '已取消'}]}   # named 已取消订单金额, counts every order but the cancelled
CITY_TIER = {'type': 'customer', 'english_name': 'city_tier', 'name': '城市等级', 'kind': 'function', 'expression': 'concat(city, tier)'}   # read from the customers' own rows, counts no order


class PropertyNamedForTheMeaningTests(pilot.PilotFoundation):
    """The name exception of the meanings side (review of nl-gate2 @ 860b79d): a meaning said only inside the name of the derived property the query reads is
    that property asked for by its name. Only when the property counts exactly that meaning, and only when the question puts no negation or "other than" around
    it: 非已取消订单金额 asks for the opposite of what the property counts (B1), and a property named 已取消订单金额 that leaves the cancelled out answers 49,145 (B2)."""
    ask = DerivedViewAnswerTests.ask

    def test_the_property_asked_for_by_its_name_with_nothing_listed_is_refused_saying_how_to_ask(self):
        answer = self.ask({'query': CANCELLED_A, 'definitions_used': []}, 'A 级客户的已取消订单金额合计是多少？', derived=(pilot.VALID_AMOUNT, CANCELLED_AMOUNT))
        self.assertEqual(answer['status'], 'definition_unmet')   # no name exception (review of f21041e, B1): the model must say the meaning is included
        self.assertIn('已取消订单金额', answer['reason'])
        self.assertIn('换个问法', answer['reason'])   # name the meaning or the property outright
        self.assertEqual(tier_a_cancelled(), 6415)

    def test_a_negation_around_the_name_is_refused(self):
        for question in ('A 级客户的非已取消订单金额合计是多少？', 'A 级客户除了已取消订单金额以外，其他订单金额合计是多少？', 'A 级客户不算已取消订单金额的话订单金额合计是多少？',
                         'A 级客户的订单金额合计是多少，已取消订单金额除外？', 'What is the order amount of tier A customers, not counting 已取消订单金额?'):
            with self.subTest(question=question):
                answer = self.ask({'query': CANCELLED_A, 'definitions_used': []}, question, derived=(pilot.VALID_AMOUNT, CANCELLED_AMOUNT))
                self.assertEqual(answer['status'], 'definition_unmet', question)   # 6,415 is the cancelled amount, the opposite of what was asked
                self.assertNotIn('answer', answer)

    def test_a_property_whose_conditions_are_not_the_meaning_in_its_name_is_refused(self):
        answer = self.ask({'query': CANCELLED_A, 'definitions_used': []}, 'A 级客户的已取消订单金额合计是多少？', derived=(pilot.VALID_AMOUNT, MISNAMED))
        self.assertEqual(answer['status'], 'definition_unmet')   # it would answer 49,145, every order but the cancelled
        self.assertNotIn('answer', answer)

    def test_a_query_that_reads_neither_the_table_nor_a_property_counting_it_is_answered_as_by_design(self):
        count_a = {'start': 'customer', 'where': [{'field': 'tier', 'equals': 'A'}], 'via': [], 'group_by': None, 'share': None, 'measure': None}
        answer = self.ask({'query': count_a, 'definitions_used': []}, 'A 级客户里有已取消订单的客户有几个？')
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))   # the meaning's table is not read at all: not this rule's business (answer_checks, as designed)

    def test_a_property_that_counts_another_table_is_not_held_against_the_meaning(self):
        by_city_tier = {'start': 'customer', 'where': [{'field': 'tier', 'equals': 'A'}], 'via': [], 'group_by': ['城市等级'], 'share': None, 'measure': None}
        answer = self.ask({'query': by_city_tier, 'definitions_used': []}, 'A 级客户里有已取消订单的客户按城市等级各有几个？', derived=(pilot.VALID_AMOUNT, CITY_TIER))
        self.assertEqual(answer['status'], 'answered', answer.get('reason'))   # the property reads the customers' rows, not the orders'


REST = ('A 级客户的订单总金额减去已取消订单金额是多少？', 'A 级客户的订单总金额减掉已取消订单金额后是多少？', '抛开已取消订单金额，A 级客户的订单金额合计是多少？',
        '撇开已取消订单金额，A 级客户的订单金额合计是多少？', '刨去已取消订单金额，A 级客户的订单金额合计是多少？', 'A 级客户已取消订单金额外的订单金额合计是多少？',
        'A 级客户的订单金额合计是多少（已取消订单金额要剔掉）？', 'A 级客户的订单总金额和已取消订单金额的差是多少？', 'A 级客户跟已取消订单金额相反的那部分订单金额是多少？',
        'Order amount of tier A customers apart from 已取消订单金额?', 'Order amount of tier A customers aside from 已取消订单金额?', 'Order amount of tier A customers excl. 已取消订单金额?',
        'Order amount of tier A customers with 已取消订单金额 excluded?', 'Order amount of tier A customers excepting 已取消订单金额?', 'Order amount of tier A customers net of 已取消订单金额?',
        'Order amount of tier A customers leaving out 已取消订单金额?', 'Order amount of tier A customers omitting 已取消订单金额?', 'Order amount of tier A customers ignoring 已取消订单金额?',
        'Order amount of tier A customers after removing 已取消订单金额?')


class NoNameExceptionTests(pilot.PilotFoundation):
    """Review of nl-walkfix @ f21041e, B1: no list of words can hold every way of asking for the rest (减去, 刨去, …外的, apart from, net of, …). A meaning the question
    says and the model did not list, with the query reading a derived property that counts its table, is refused whatever the words around it; the model has to say
    the meaning is included for the property's number to be the answer."""
    ask = DerivedViewAnswerTests.ask

    def test_asking_for_the_rest_in_any_words_is_refused(self):
        for question in REST:
            with self.subTest(question=question):
                answer = self.ask({'query': CANCELLED_A, 'definitions_used': []}, question, derived=(pilot.VALID_AMOUNT, CANCELLED_AMOUNT))
                self.assertEqual(answer['status'], 'definition_unmet', question)   # 6,415 is the cancelled amount, not the rest
                self.assertNotIn('answer', answer)

    def test_the_property_is_answered_when_the_model_says_the_question_includes_its_meaning(self):
        answer = self.ask({'query': CANCELLED_A, 'definitions_used': CANCELLED}, 'A 级客户的已取消订单金额合计是多少？', derived=(pilot.VALID_AMOUNT, CANCELLED_AMOUNT))
        self.assertEqual((answer['status'], answer['answer']['measure']['value']), ('answered', 6415), answer.get('reason'))
