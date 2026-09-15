import unittest

from ontology_poc_generator.ontology_questions import MAX_GROUPS, run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL


class GroupCapTests(unittest.TestCase):
    def test_a_question_with_thousands_of_groups_keeps_the_largest_and_says_how_many_there_were(self):
        orders = [{'订单号': f'O{i}', '客户编号': 'C1', '金额': str(i // 2), '下单日期': '2026-01-02'} for i in range(2 * (MAX_GROUPS + 50))]
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': orders, 'requests': []}}}
        answer = run_query(PROPOSAL, bundle, {'start': 'order', 'group_by': [{'via': [], 'field': '订单.金额'}]})['answer']
        self.assertEqual(len(answer['groups']), MAX_GROUPS)
        self.assertEqual(answer['total_groups'], MAX_GROUPS + 50)


if __name__ == '__main__':
    unittest.main()
