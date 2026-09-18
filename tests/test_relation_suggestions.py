"""Relations code can see in the data that the ontology does not have: offered as suggestions, never added."""
import unittest

from ontology_poc_generator.relation_suggestions import suggest_relations


def table(*rows):
    header, *data = rows
    return {'records': [dict(zip(header, r)) for r in data], 'requests': []}


BUNDLE = {'sources': {
    'orders': table(('订单号', '客户编号', '供应商', '备注'), ('O1', 'C1', 'SUP-001', '急'), ('O2', 'C2', 'SUP-002', '急'), ('O3', 'C1', '', '缓')),
    'customers': table(('客户编号', '名称'), ('C1', '甲'), ('C2', '乙')),
    'suppliers': table(('供应商编号', '名称'), ('SUP001', '丙'), ('SUP002', '丁'), ('SUP003', '戊')),
}}


def ontology(relations=()):
    return {
        'object_types': [
            {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'id': '订单号'}}], 'attributes': []},
            {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'customers', 'identity': {'id': '客户编号'}}], 'attributes': []},
            {'key': 'supplier', 'label': '供应商', 'populated_from': [{'source': 'suppliers', 'identity': {'id': '供应商编号'}}], 'attributes': []},
        ],
        'relations': list(relations), 'ignored_fields': [], 'open_questions': [],
    }


ORDER_CUSTOMER = {'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': 'orders'}


class SuggestionTests(unittest.TestCase):
    def test_a_column_pointing_at_another_objects_number_is_suggested_with_its_evidence(self):
        found = suggest_relations(ontology([ORDER_CUSTOMER]), BUNDLE)
        self.assertEqual(found, [{'kind': 'pointer', 'from': 'order', 'to': 'supplier', 'via': {'source': 'orders', 'field': '供应商'},
                                  'key': {'source': 'suppliers', 'field': '供应商编号'}, 'rows': 3, 'linked': 2, 'loose': True}])

    def test_a_relation_the_ontology_already_has_is_not_suggested_again(self):
        self.assertNotIn(('order', 'customer'), [(s['from'], s['to']) for s in suggest_relations(ontology([ORDER_CUSTOMER]), BUNDLE)])
        self.assertIn(('order', 'customer'), [(s['from'], s['to']) for s in suggest_relations(ontology(), BUNDLE)])

    def test_one_value_that_matches_nothing_means_no_suggestion(self):
        bundle = {'sources': {**BUNDLE['sources'], 'orders': table(('订单号', '供应商'), ('O1', 'SUP-001'), ('O2', 'SUP-009'))}}
        self.assertEqual([s for s in suggest_relations(ontology(), bundle) if s['to'] == 'supplier'], [])

    def test_leading_zeros_still_count_as_a_difference(self):
        bundle = {'sources': {'orders': table(('订单号', '客户编号'), ('O1', '007')), 'customers': table(('客户编号',), ('7',))}}
        self.assertEqual(suggest_relations(ontology(), bundle), [])


if __name__ == '__main__':
    unittest.main()
