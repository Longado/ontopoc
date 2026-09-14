import unittest

from ontology_poc_generator.ontology_compare import ReferenceError, compare_ontologies, parse_reference


def t(key, label, source, **identity):
    return {'key': key, 'label': label, 'populated_from': [{'source': source, 'identity': identity}], 'attributes': []}


OURS = {'object_types': [
    t('customer', '客户', '客户', customer_id='客户编号'), t('order', '订单', '订单', order_id='订单号'),
    t('product', '产品', '产品', product_id='产品编号')],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': '订单'},
                  {'key': 'order_product', 'from': 'order', 'to': 'product', 'source': '订单'}]}
THEIRS = {'object_types': [
    t('client', '客户资料', '客户', id='客户编号'), t('order', '订单', '订单', no='订单号'),
    {'key': 'engineer', 'label': '售后工程师', 'populated_from': [{'source': '售后工单', 'identity': {'name': '负责工程师'}}]}],
    'relations': [{'key': 'r1', 'from': 'client', 'to': 'order', 'source': '订单'},
                  {'key': 'r2', 'from': 'order', 'to': 'engineer', 'source': '售后工单'}]}


class CompareTests(unittest.TestCase):
    def test_types_match_on_table_and_identity_fields_even_with_other_names(self):
        diff = compare_ontologies(THEIRS, OURS)
        self.assertEqual(diff['types']['matched'], [['客户资料', '客户'], ['订单', '订单']])
        self.assertEqual(diff['types']['only_reference'], ['售后工程师'])
        self.assertEqual(diff['types']['only_ours'], ['产品'])

    def test_relations_match_when_both_ends_match_in_either_direction(self):
        diff = compare_ontologies(THEIRS, OURS)
        self.assertEqual(diff['relations']['matched'], [['客户资料 — 订单', '订单 — 客户']])
        self.assertEqual(diff['relations']['only_reference'], ['订单 — 售后工程师'])
        self.assertEqual(diff['relations']['only_ours'], ['订单 — 产品'])
        self.assertEqual(diff['counts'], {'types': {'reference': 3, 'ours': 3, 'matched': 2},
                                          'relations': {'reference': 2, 'ours': 2, 'matched': 1}})

    def test_identical_ontologies_have_no_differences(self):
        diff = compare_ontologies(OURS, OURS)
        self.assertEqual((diff['types']['only_reference'], diff['types']['only_ours'], diff['relations']['only_ours']), ([], [], []))

    def test_same_label_matches_when_tables_differ(self):
        other = {'object_types': [t('p', '产品', '商品表', sku='编码')], 'relations': []}
        self.assertEqual(compare_ontologies(other, OURS)['types']['matched'], [['产品', '产品']])


class ReferenceFileTests(unittest.TestCase):
    def test_a_reference_needs_types_with_labels_and_relations_naming_them(self):
        ref = parse_reference({'object_types': [{'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'id': '客户编号'}}]}],
                               'relations': [{'from': '客户', 'to': '客户'}]})
        self.assertEqual(ref['object_types'][0]['key'], '客户')
        for bad, message in (({}, 'object_types'), ({'object_types': [{}]}, 'label'),
                             ({'object_types': [{'label': 'A'}], 'relations': [{'from': 'A', 'to': 'B'}]}, 'B')):
            with self.subTest(message=message), self.assertRaisesRegex(ReferenceError, message):
                parse_reference(bad)


if __name__ == '__main__':
    unittest.main()
