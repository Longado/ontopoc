import unittest

from ontology_poc_generator.ontology_questions import run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL


class WithoutValueTests(unittest.TestCase):
    def test_objects_that_fall_out_of_a_grouping_are_named_not_only_counted(self):
        # 订单 O3 points at customer C9, which the customer table does not have: it can have no customer name
        answer = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [{'via': ['order_customer'], 'field': '客户.名称'}]})['answer']
        self.assertEqual(answer['without_value'], 1)
        self.assertEqual(answer['without_value_examples'], ['O3'])


if __name__ == '__main__':
    unittest.main()
