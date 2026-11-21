"""A derived property stands for a view's rows only when each of those rows reaches exactly one object through its path. 有效订单金额 adds up each customer's
valid orders; an order whose customer_id names no customer (O9999, C999, 50,000, status 1 = 已付款) is in the view but in no customer's sum, so the total over the
property is 119,810 where the view gives 169,810. Answered from the property it is a wrong number: refused, as before the derived route existed. And a property
whose conditions are those of a view that has since been changed and waits for confirming does not stand in for it either. On the pilot sample; expected numbers
are counted from the CSV files here."""
import csv

from tests import test_derived_new_values as pilot
from tests.test_derived_view_answers import LEFT_OUT as EXCLUDED, TIER_A, VALID, query   # EXCLUDED: the three meanings listed as exclude
from tests.test_workspace_questions import AskModel

ORPHAN = {'order_id': 'O9999', 'customer_id': 'C999', 'order_date': '2026-06-05', 'amount': '50000', 'status_code': '1'}


def with_orphan() -> str:
    text = (pilot.SAMPLE / 'orders.csv').read_text(encoding='utf-8').rstrip('\n')
    header = text.split('\n')[0].split(',')
    return text + '\n' + ','.join(ORPHAN[c] for c in header) + '\n'


VIEW_TOTAL = sum(int(r['amount']) for r in csv.DictReader((pilot.SAMPLE / 'orders.csv').open(encoding='utf-8')) if r['status_code'] not in ('0', '4', '5')) + int(ORPHAN['amount'])
ALL = query()   # every customer's 有效订单金额 added up


class OrphanRowTests(pilot.PilotFoundation):
    def ask(self, item, question, orders=None):
        model = AskModel({'reasoning': '用已确认的派生属性', **item})
        with self.service(gateway=model) as (base, out):
            ann = self.foundation(base, orders=orders)['ann']
            status, answer = ann.post('/api/workspace/ask', {'question': question})
            self.assertEqual(status, 200, answer)
            return answer

    def test_the_total_of_the_view_is_not_answered_from_a_property_that_leaves_an_order_without_a_customer_out(self):
        self.assertEqual(VIEW_TOTAL, 169810)
        answer = self.ask({'query': ALL, 'definitions_used': [VALID]}, '有效订单的总金额是多少？', orders=with_orphan())
        self.assertEqual(answer['status'], 'definition_unmet')   # 119,810 would be wrong
        self.assertNotIn('answer', answer)
        self.assertIn('有效订单金额', answer['reason'])   # says why the property cannot stand for the view

    def test_the_meanings_left_out_one_by_one_are_not_met_through_it_either(self):
        used = EXCLUDED
        answer = self.ask({'query': ALL, 'definitions_used': used}, '不算新建、已取消和已退款，订单总金额是多少？', orders=with_orphan())
        self.assertEqual(answer['status'], 'definition_unmet')

    def test_when_every_order_has_its_customer_the_property_still_answers(self):
        answer = self.ask({'query': ALL, 'definitions_used': [VALID]}, '有效订单的总金额是多少？')
        self.assertEqual((answer['status'], answer['answer']['measure']['value']), ('answered', VIEW_TOTAL - int(ORPHAN['amount'])))


class WaitingViewTests(pilot.PilotFoundation):
    """The view 有效订单 is changed (it now also leaves out 已付款) and waits for confirming; 有效订单金额 still has the view's old conditions and stays
    confirmed. A reply that leaves out the three meanings one by one would be answered from the property's old conditions, hiding that 有效 is being
    redefined: it is refused, naming the view."""

    def test_meanings_left_out_through_a_property_whose_view_waits_are_refused_naming_the_view(self):
        used = EXCLUDED
        model = AskModel({'reasoning': '用已确认的派生属性', 'query': TIER_A, 'definitions_used': used})
        with self.service(gateway=model) as (base, out):
            ann = self.foundation(base)['ann']
            view = self.view(ann)
            status, body = ann.post('/api/workspace/types/views/update', {'id': '有效订单', 'version': view['version'], 'name': '有效订单', 'type': 'order',
                                                                         'filters': [*pilot.CONDITIONS, {'column': 'status_code', 'op': 'is_not', 'label': '已付款'}]})
            self.assertEqual((status, body['state']), (200, 'checked'))
            status, answer = ann.post('/api/workspace/ask', {'question': 'A 级客户的订单金额合计是多少，不算新建、已取消和已退款？'})
            self.assertEqual(status, 200, answer)
            self.assertEqual(answer['status'], 'definition_unmet')
            self.assertIn('有效订单', answer['reason'])


AVG = {**pilot.VALID_AMOUNT, 'english_name': 'valid_avg', 'name': '有效订单平均金额', 'fn': 'avg'}
COUNT = {**pilot.VALID_AMOUNT, 'english_name': 'valid_count', 'name': '有效订单数', 'measure': {'column': None}, 'fn': 'count'}
VALID_ROWS = sum(1 for r in csv.DictReader((pilot.SAMPLE / 'orders.csv').open(encoding='utf-8')) if r['status_code'] not in ('0', '4', '5'))


class PropertyFunctionTests(pilot.PilotFoundation):
    """The property's own calculation and the query's measure must add up to the view's rows: a sum of a per-customer sum, or a sum of a per-customer count. A
    sum of per-customer averages (or a minimum, an average of sums…) is not the view's total, even with the view's conditions."""

    def ask(self, item, question, derived):
        model = AskModel({'reasoning': '用已确认的派生属性', **item})
        with self.service(gateway=model) as (base, out):
            ann = self.foundation(base, derived)['ann']
            status, answer = ann.post('/api/workspace/ask', {'question': question})
            self.assertEqual(status, 200, answer)
            return answer

    def test_a_sum_of_per_customer_averages_is_not_the_views_total(self):
        answer = self.ask({'query': query('有效订单平均金额'), 'definitions_used': [VALID]}, '有效订单的总金额是多少？', (pilot.VALID_AMOUNT, AVG))
        self.assertEqual(answer['status'], 'definition_unmet')   # 45,289.25 would be wrong
        self.assertNotIn('answer', answer)

    def test_an_average_over_the_per_customer_sums_is_not_the_views_rows_either(self):
        answer = self.ask({'query': {**query(), 'measure': {'field': '有效订单金额', 'op': 'average'}}, 'definitions_used': [VALID]}, '有效订单的平均金额是多少？', (pilot.VALID_AMOUNT,))
        self.assertEqual(answer['status'], 'definition_unmet')

    def test_a_sum_of_per_customer_counts_is_the_views_row_count(self):
        self.assertEqual(VALID_ROWS, 107)
        answer = self.ask({'query': query('有效订单数'), 'definitions_used': [VALID]}, '有效订单一共有多少笔？', (pilot.VALID_AMOUNT, COUNT))
        self.assertEqual((answer['status'], answer['answer']['measure']['value']), ('answered', VALID_ROWS), answer.get('reason'))
