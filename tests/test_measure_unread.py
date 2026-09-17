import unittest

from ontology_poc_generator.ontology_questions import run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL

# 订单：O1 金额 100（客户甲）、O2（客户乙）、O3 金额 70（客户 C9，客户表里没有）
BY_CUSTOMER = {'via': ['order_customer'], 'field': '客户.名称'}
AVERAGE = {'start': 'order', 'measure': {'field': '订单.金额', 'op': 'average'}}


def bundle_with(amounts: dict) -> dict:
    records = [{**r, '金额': amounts.get(r['订单号'], r['金额'])} for r in BUNDLE['sources']['订单']['records']]
    return {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': records, 'requests': []}}}


class UnreadMeasureTests(unittest.TestCase):
    def test_a_group_with_no_readable_value_is_not_shown_as_zero(self):
        # the shape real exports have: a whole kind of hospital that never reports the figure, written as words
        answer = run_query(PROPOSAL, bundle_with({'O2': 'Not Available'}), {**AVERAGE, 'group_by': [BY_CUSTOMER]})['answer']
        self.assertEqual(answer['groups'], [['甲', 100, 1]])
        self.assertEqual(answer['unread_groups'], {'count': 1, 'examples': ['乙']})
        self.assertEqual(answer['total_groups'], 1)

    def test_every_group_says_how_many_values_it_was_computed_from(self):
        answer = run_query(PROPOSAL, BUNDLE, {**AVERAGE, 'group_by': [BY_CUSTOMER]})['answer']
        self.assertEqual(answer['groups'], [['甲', 100, 1], ['乙', 50, 1]])   # an average of one is a fact worth seeing
        self.assertNotIn('unread_groups', answer)

    def test_a_total_of_nothing_readable_is_no_data_and_says_why(self):
        for op in ('sum', 'average'):
            with self.subTest(op=op):
                result = run_query(PROPOSAL, bundle_with({'O1': 'DUR', 'O2': '', 'O3': 'N/A'}), {'start': 'order', 'measure': {'field': '订单.金额', 'op': op}})
                self.assertEqual(result['status'], 'no_data')
                self.assertIn('金额', result['reason'])
                self.assertEqual((result['answer']['measure']['value'], result['answer']['measure']['counted'], result['answer']['measure']['skipped']), (None, 0, 3))


if __name__ == '__main__':
    unittest.main()
