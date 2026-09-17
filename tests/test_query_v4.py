import unittest

from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, QUESTION_SYSTEM_PROMPT, run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL

BY_CUSTOMER = {'via': ['order_customer'], 'field': '客户.名称'}


class GroupByManyTests(unittest.TestCase):
    def test_each_dimension_walks_its_own_relations_and_groups_combine(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [BY_CUSTOMER, {'via': [], 'field': '订单.金额'}]})
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer'], {'groups': [['乙 · 50', 1], ['甲 · 100', 1]], 'total_groups': 2, 'without_value': 1, 'without_value_examples': ['O3']})
        self.assertEqual(result['path'], '订单：按“名称”（经 订单 → 客户）和“金额”分组数订单')

    def test_a_dimension_on_a_field_the_type_lacks_is_a_gap(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [{'via': [], 'field': '客户.名称'}]})
        self.assertEqual(result['status'], 'ontology_gap')


class ShareTests(unittest.TestCase):
    def test_each_group_gives_matched_over_all_and_is_ordered_by_the_share(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [BY_CUSTOMER], 'share': {'field': '订单.金额', 'equals': '100'}})
        self.assertEqual(result['answer']['groups'], [['甲', 1, 1], ['乙', 0, 1]])
        self.assertEqual(result['answer']['share'], {'field': '金额', 'equals': '100'})
        self.assertEqual(result['path'], '订单 → 客户，按“名称”分组，算“金额”为“100”的订单占比')

    def test_without_groups_the_share_is_over_all_start_objects(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'share': {'field': '订单.金额', 'equals': '100'}})
        self.assertEqual(result['answer'], {'total': 3, 'matched': 1, 'share': {'field': '金额', 'equals': '100'}})

    def test_a_share_on_a_field_the_start_type_lacks_is_a_gap(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'share': {'field': '客户.城市', 'equals': '苏州'}})
        self.assertEqual(result['status'], 'ontology_gap')


class PromptTests(unittest.TestCase):
    def test_the_prompt_version_moves_and_describes_both_forms(self):
        self.assertEqual(QUESTION_PROMPT_VERSION, 'company_questions.v5')
        self.assertIn('"share"', QUESTION_SYSTEM_PROMPT)
        self.assertIn('"group_by": [{', QUESTION_SYSTEM_PROMPT)


if __name__ == '__main__':
    unittest.main()
