"""Grouping by the same field along the same path twice is how a model writes "which products sell together". The
query cannot pair two different values of one dimension, so it would pair each value with itself and give a count that
looks real. It has to say the question is beyond the query instead."""
import unittest

from ontology_poc_generator.ontology_questions import run_query


def table(*rows):
    header, *data = rows
    return {'records': [dict(zip(header, r)) for r in data], 'requests': []}


BUNDLE = {'sources': {'lines': table(('订单号', '产品'), ('O1', '奶酪'), ('O1', '面包'), ('O2', '奶酪'), ('O2', '面包'), ('O3', '奶酪'))}}
ONTOLOGY = {
    'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'lines', 'identity': {'order_id': '订单号'}}], 'attributes': []},
        {'key': 'product', 'label': '产品', 'populated_from': [{'source': 'lines', 'identity': {'name': '产品'}}], 'attributes': []},
    ],
    'relations': [{'key': 'order_contains_product', 'from': 'order', 'to': 'product', 'source': 'lines'}],
    'ignored_fields': [], 'open_questions': [],
}
PAIR = {'via': ['order_contains_product'], 'field': '产品'}


class RepeatedDimensionTests(unittest.TestCase):
    def test_the_same_dimension_twice_is_beyond_the_query_not_a_self_pair(self):
        result = run_query(ONTOLOGY, BUNDLE, {'start': 'order', 'where': [], 'via': [], 'group_by': [PAIR, dict(PAIR)]})
        self.assertEqual(result['status'], 'query_limit')
        self.assertIn('同一个', result['reason'])
        self.assertNotIn('answer', result)

    def test_one_dimension_still_counts(self):
        result = run_query(ONTOLOGY, BUNDLE, {'start': 'order', 'where': [], 'via': [], 'group_by': [PAIR]})
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(dict((g[0], g[1]) for g in result['answer']['groups']), {'奶酪': 3, '面包': 2})


if __name__ == '__main__':
    unittest.main()
