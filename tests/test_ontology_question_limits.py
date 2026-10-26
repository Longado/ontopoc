import json
import unittest

from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, ask_questions, run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL
from tests.test_ontology_questions import AskTests


class QueryLimitTests(unittest.TestCase):
    def test_a_question_the_query_format_cannot_hold_is_not_blamed_on_the_ontology(self):
        model = AskTests.Model({'questions': [
            {'reasoning': '需要同时按两个维度分组', 'question': '哪些客户、产品的订单最多？', 'query': None, 'missing': 'query_language'},
            {'reasoning': '本体里没有发票', 'question': '哪张发票金额最大？', 'query': None, 'missing': 'ontology'},
            {'reasoning': '说不清', 'question': '？', 'query': None},
        ]})
        out = ask_questions(PROPOSAL, BUNDLE, model)
        self.assertEqual([i['status'] for i in out['items']], ['query_limit', 'ontology_gap', 'ontology_gap'])
        self.assertEqual(QUESTION_PROMPT_VERSION, 'company_questions.v7')


class UnknownKeysTests(unittest.TestCase):
    """A condition or a query key the format has no place for must say so, never be dropped: dropped, a date range read
    as an equals of nothing and the answer was "no object satisfies the filter"."""

    def test_a_filter_other_than_equals_is_a_query_limit_that_names_the_key(self):
        for where in ({'field': '订单.下单日期', 'gte': '2026-01-03'},
                      {'field': '订单.金额', 'equals': '100', 'gte': '50'}):
            with self.subTest(where=where):
                result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [where]})
                self.assertEqual(result['status'], 'query_limit')
                self.assertIn('gte', result['reason'])

    def test_a_condition_that_names_no_value_to_equal_is_a_query_limit(self):
        for query in ({'start': 'order', 'where': [{'field': '订单.金额'}]},
                      {'start': 'order', 'share': {'field': '订单.金额'}},
                      {'start': 'order', 'where': ['订单.金额']}):
            with self.subTest(query=query):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, query)['status'], 'query_limit')

    def test_a_share_with_an_extra_key_is_a_query_limit_that_names_the_key(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': ['客户.名称'], 'via': ['order_customer'],
                                              'share': {'field': '订单.金额', 'equals': '100', 'not': '1'}})
        self.assertEqual(result['status'], 'query_limit')
        self.assertIn('not', result['reason'])

    def test_a_query_key_the_format_does_not_have_is_a_query_limit_that_names_it(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'date_range': {'from': '2026-01-01'}, 'limit': 5})
        self.assertEqual(result['status'], 'query_limit')
        self.assertIn('date_range', result['reason'])
        self.assertIn('limit', result['reason'])

    def test_the_check_comes_before_the_data_is_read_and_after_the_start_type(self):
        self.assertEqual(run_query(PROPOSAL, {}, {'start': 'order', 'date_range': 1})['status'], 'query_limit')   # no bundle to build a graph from
        self.assertEqual(run_query(PROPOSAL, {}, {'start': 'invoice', 'date_range': 1})['status'], 'ontology_gap')

    def test_every_older_shape_that_means_something_still_runs(self):
        for query in ({'start': 'order', 'where': [{'field': '订单.金额', 'equals': '100'}], 'via': [], 'group_by': None, 'share': None, 'measure': None},
                      {'start': 'order', 'via': ['order_customer'], 'group_by': '客户.名称'},
                      {'start': 'order', 'where': None, 'group_by': [{'via': [], 'field': '订单.金额'}], 'share': {'field': '订单.金额', 'equals': '100'}},
                      {'start': 'order', 'share': {}, 'measure': {'field': '订单.金额', 'op': 'sum'}}):
            with self.subTest(query=query):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, query)['status'], 'answered')

    def test_a_group_or_a_measure_with_a_key_the_format_does_not_have_is_a_query_limit_that_names_it(self):
        for query, key in (({'start': 'order', 'group_by': [{'via': [], 'field': '订单.金额', 'bucket': 'month'}]}, 'bucket'),
                           ({'start': 'order', 'measure': {'field': '订单.金额', 'op': 'sum', 'where': {'field': '订单.金额', 'equals': '100'}}}, 'where')):
            with self.subTest(key=key):
                result = run_query(PROPOSAL, BUNDLE, query)
                self.assertEqual(result['status'], 'query_limit')
                self.assertIn(key, result['reason'])

    def test_a_list_or_a_range_as_the_value_to_equal_is_a_query_limit(self):
        for equals in (['100', '200'], {'from': '2026-01-01', 'to': '2026-02-01'}):
            with self.subTest(equals=equals):
                result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [{'field': '订单.金额', 'equals': equals}]})
                self.assertEqual(result['status'], 'query_limit')

    def test_a_part_written_in_a_shape_the_format_does_not_have_is_a_query_limit(self):
        for query in ({'start': 'order', 'measure': 'sum'}, {'start': 'order', 'group_by': {'via': [], 'field': '订单.金额'}},
                      {'start': 'order', 'share': '订单.金额=100'}, {'start': 'order', 'where': 5}, {'start': 'order', 'via': 5},
                      {'start': 'order', 'where': {'field': '订单.金额', 'equals': '100'}}):
            with self.subTest(query=query):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, query)['status'], 'query_limit')

    def test_an_extra_key_left_empty_says_nothing_and_is_ignored(self):
        for query in ({'start': 'order', 'limit': None},
                      {'start': 'order', 'where': [{'field': '订单.金额', 'equals': '100', 'note': ''}]},
                      {'start': 'order', 'group_by': [{'via': [], 'field': '订单.金额', 'bucket': None}]},
                      {'start': 'order', 'measure': {'field': '订单.金额', 'op': 'sum', 'derived': None, 'where': []}}):
            with self.subTest(query=query):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, query)['status'], 'answered')


if __name__ == '__main__':
    unittest.main()
