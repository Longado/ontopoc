import unittest
from ontology_poc_generator.ontology_eval import data_fit
from test_relation_bindings import PROPOSAL, BUNDLE


class EmptyEndpointTests(unittest.TestCase):
    def test_empty_parent_number_is_counted_separately_from_broken_references(self):
        relation = data_fit(PROPOSAL, BUNDLE)['relations'][0]
        self.assertEqual(relation.get('empty_rows'), 1)
        self.assertEqual(relation['linked_rows'], 2)


class EmptyKeyInsideListTests(unittest.TestCase):
    ONTOLOGY = {
        'object_types': [{'key': 'order', 'label': '订单', 'attributes': [], 'populated_from': [{'source': 'orders', 'identity': {'order_no': 'order_no'}}]},
                         {'key': 'sku', 'label': '货品', 'attributes': [], 'populated_from': [{'source': 'skus', 'identity': {'sku': 'sku'}}]}],
        'relations': [{'key': 'order_sku', 'from': 'order', 'to': 'sku', 'source': 'orders', 'to_identity': {'sku': 'lines[].sku'}}],
        'ignored_fields': []}
    BUNDLE = {'schema': 'company_source_bundle.v1', 'decision': 'd', 'file': {'name': 'orders.xlsx', 'sha256': 'c' * 64, 'kind': 'table'},
              'sources': {'orders': {'records': [{'order_no': 'O1', 'lines': [{'sku': 'S1'}, {'sku': ''}]},
                                                 {'order_no': 'O2', 'lines': []},
                                                 {'order_no': 'O3', 'lines': [{'sku': None}]},
                                                 {'order_no': 'O4', 'lines': [{'sku': 'S9'}]}], 'requests': []},
                          'skus': {'records': [{'sku': 'S1'}], 'requests': []}}}

    def test_a_row_is_empty_when_none_of_the_values_in_its_list_is_filled(self):
        [relation] = data_fit(self.ONTOLOGY, self.BUNDLE)['relations']
        self.assertEqual(relation['linked_rows'], 1)
        self.assertEqual(relation['empty_rows'], 2)   # no line at all, and a line without a sku; the row with one filled value is not empty
