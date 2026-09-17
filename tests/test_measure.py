import unittest

from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, QUESTION_SYSTEM_PROMPT, run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL

# 订单：O1 金额 100（客户甲）、O2 金额 50（客户乙）、O3 金额 70（客户 C9，客户表里没有）
SUM = {'start': 'order', 'measure': {'field': '订单.金额', 'op': 'sum'}}
BY_CUSTOMER = {'via': ['order_customer'], 'field': '客户.名称'}


class MeasureTests(unittest.TestCase):
    def test_a_total_is_added_up_by_code_and_says_how_many_rows_it_added(self):
        answer = run_query(PROPOSAL, BUNDLE, SUM)['answer']
        self.assertEqual(answer['measure'], {'field': '金额', 'op': 'sum', 'value': 220, 'counted': 3, 'skipped': 0})

    def test_an_average_says_what_its_denominator_was(self):
        answer = run_query(PROPOSAL, BUNDLE, {**SUM, 'measure': {'field': '订单.金额', 'op': 'average'}})['answer']
        self.assertEqual(answer['measure']['value'], 220 / 3)
        self.assertEqual(answer['measure']['counted'], 3)

    def test_values_that_are_not_numbers_are_skipped_and_counted_not_read_as_zero(self):
        records = [{**r} for r in BUNDLE['sources']['订单']['records']]
        records[0]['金额'] = 'DUR'   # the shape a real export has: a word where a number belongs
        records[1]['金额'] = ''
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': records, 'requests': []}}}
        measure = run_query(PROPOSAL, bundle, {**SUM, 'measure': {'field': '订单.金额', 'op': 'average'}})['answer']['measure']
        self.assertEqual((measure['value'], measure['counted'], measure['skipped']), (70, 1, 2))

    def test_a_total_per_group_ranks_by_the_total(self):
        answer = run_query(PROPOSAL, BUNDLE, {**SUM, 'group_by': [BY_CUSTOMER]})['answer']
        self.assertEqual(answer['groups'], [['甲', 100], ['乙', 50]])
        self.assertEqual(answer['measure']['field'], '金额')
        self.assertEqual(answer['without_value'], 1)   # O3's customer is not in the customer table

    def test_the_path_says_what_was_added_up(self):
        self.assertEqual(run_query(PROPOSAL, BUNDLE, SUM)['path'], '订单，把“金额”加起来')
        grouped = run_query(PROPOSAL, BUNDLE, {**SUM, 'group_by': [BY_CUSTOMER], 'measure': {'field': '订单.金额', 'op': 'average'}})
        self.assertEqual(grouped['path'], '订单 → 客户，按“名称”分组，算每组“金额”的平均')

    def test_a_measure_on_a_field_the_start_type_lacks_is_a_gap(self):
        gap = run_query(PROPOSAL, BUNDLE, {**SUM, 'measure': {'field': '客户.城市', 'op': 'sum'}})
        self.assertEqual(gap['status'], 'ontology_gap')

    def test_the_prompt_moves_to_v5_and_describes_the_measure(self):
        self.assertEqual(QUESTION_PROMPT_VERSION, 'company_questions.v5')
        self.assertIn('"measure"', QUESTION_SYSTEM_PROMPT)


if __name__ == '__main__':
    unittest.main()
