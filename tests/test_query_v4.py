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


class ExclusionTests(unittest.TestCase):
    def test_not_equals_leaves_the_rows_with_that_value_out_and_a_list_leaves_out_all_of_them(self):
        one = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [{'field': '订单.金额', 'not_equals': '100'}]})
        self.assertEqual((one['status'], one['answer']['total']), ('answered', 2))
        self.assertEqual(one['path'], '订单里 金额 不是 100')
        many = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [{'field': '订单.金额', 'not_equals': ['100', '50']}],
                                            'measure': {'field': '订单.金额', 'op': 'sum'}})
        self.assertEqual((many['answer']['total'], many['answer']['measure']['value']), (1, 70))
        self.assertEqual(many['path'], '订单里 金额 不是 50、100，把“金额”加起来')

    def test_a_condition_cannot_say_equals_and_not_equals_and_a_share_cannot_say_not_equals(self):
        for query in ({'start': 'order', 'where': [{'field': '订单.金额', 'equals': '100', 'not_equals': '50'}]},
                      {'start': 'order', 'where': [{'field': '订单.金额', 'not_equals': {'from': '1'}}]},
                      {'start': 'order', 'where': [{'field': '订单.金额', 'not_equals': []}]},
                      {'start': 'order', 'share': {'field': '订单.金额', 'not_equals': '100'}}):
            with self.subTest(query=query):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, query)['status'], 'query_limit')


class TopTests(unittest.TestCase):
    SUM_BY_CUSTOMER = {'start': 'order', 'group_by': [BY_CUSTOMER], 'via': ['order_customer'], 'measure': {'field': '订单.金额', 'op': 'sum'}}

    def test_top_keeps_the_first_groups_of_the_ranking_and_the_total_still_counts_all_of_them(self):
        result = run_query(PROPOSAL, BUNDLE, {**self.SUM_BY_CUSTOMER, 'top': 1})
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer']['groups'], [['甲', 100, 1]])
        self.assertEqual(result['answer']['total_groups'], 2)
        self.assertNotIn('tied_beyond_top', result['answer'])
        self.assertIn('取最高的 1 个', result['path'])

    def test_a_group_tied_with_the_last_one_kept_is_said_not_cut_silently(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [BY_CUSTOMER], 'via': ['order_customer'], 'top': 1})
        self.assertEqual(result['answer']['groups'], [['乙', 1]])
        self.assertEqual(result['answer']['tied_beyond_top'], 1)

    def test_top_needs_a_group_and_a_positive_whole_number(self):
        for query in ({'start': 'order', 'top': 1}, {**self.SUM_BY_CUSTOMER, 'top': 0}, {**self.SUM_BY_CUSTOMER, 'top': '3'},
                      {**self.SUM_BY_CUSTOMER, 'top': True}, {**self.SUM_BY_CUSTOMER, 'top': 1.5}):
            with self.subTest(query=query):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, query)['status'], 'query_limit')



class SmallestFirstTests(unittest.TestCase):
    SUM_BY_CUSTOMER = TopTests.SUM_BY_CUSTOMER

    def test_order_smallest_with_top_keeps_the_lowest_groups_and_says_so(self):
        result = run_query(PROPOSAL, BUNDLE, {**self.SUM_BY_CUSTOMER, 'order': 'smallest', 'top': 1})
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(result['answer']['groups'], [['乙', 50, 1]])
        self.assertEqual(result['answer']['total_groups'], 2)
        self.assertEqual(result['answer']['order'], 'smallest')
        self.assertIn('取最低的 1 个', result['path'])
        self.assertNotIn('取最高', result['path'])

    def test_order_smallest_without_top_lists_every_group_from_the_lowest(self):
        result = run_query(PROPOSAL, BUNDLE, {**self.SUM_BY_CUSTOMER, 'order': 'smallest'})
        self.assertEqual([g[0] for g in result['answer']['groups']], ['乙', '甲'])
        self.assertIn('从低到高', result['path'])

    def test_a_share_ranked_from_the_lowest_puts_the_lowest_rate_first(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [BY_CUSTOMER], 'order': 'smallest',
                                              'share': {'field': '订单.金额', 'equals': '100'}})
        self.assertEqual(result['answer']['groups'], [['乙', 0, 1], ['甲', 1, 1]])

    def test_a_group_tied_with_the_last_lowest_kept_is_said_not_cut_silently(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [BY_CUSTOMER], 'via': ['order_customer'],
                                              'order': 'smallest', 'top': 1})
        self.assertEqual(len(result['answer']['groups']), 1)
        self.assertEqual(result['answer']['tied_beyond_top'], 1)

    def test_largest_is_the_default_and_may_be_written_out(self):
        written = run_query(PROPOSAL, BUNDLE, {**self.SUM_BY_CUSTOMER, 'order': 'largest', 'top': 1})
        default = run_query(PROPOSAL, BUNDLE, {**self.SUM_BY_CUSTOMER, 'top': 1})
        self.assertEqual(written['answer']['groups'], default['answer']['groups'])
        self.assertNotIn('order', default['answer'])

    def test_order_needs_a_group_and_one_of_the_two_words(self):
        for query in ({'start': 'order', 'order': 'smallest'}, {**self.SUM_BY_CUSTOMER, 'order': 'asc'},
                      {**self.SUM_BY_CUSTOMER, 'order': True}, {**self.SUM_BY_CUSTOMER, 'order': ['smallest']}):
            with self.subTest(query=query):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, query)['status'], 'query_limit')

class PromptTests(unittest.TestCase):
    def test_the_prompt_version_moves_and_describes_both_forms(self):
        self.assertEqual(QUESTION_PROMPT_VERSION, 'company_questions.v17')
        self.assertIn('"share"', QUESTION_SYSTEM_PROMPT)
        self.assertIn('"group_by": [{', QUESTION_SYSTEM_PROMPT)
        self.assertIn('"not_equals"', QUESTION_SYSTEM_PROMPT)
        self.assertIn('"top"', QUESTION_SYSTEM_PROMPT)
        self.assertIn('"order"', QUESTION_SYSTEM_PROMPT)
        self.assertIn('`computed_as`', QUESTION_SYSTEM_PROMPT)   # a confirmed derived property is a field, not a derived measure
        self.assertNotIn('is not something the query can say', QUESTION_SYSTEM_PROMPT)


if __name__ == '__main__':
    unittest.main()
