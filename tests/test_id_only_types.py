import unittest

from ontology_poc_generator.ontology_eval import data_fit

# 订单表里有一列员工编号，但没有员工表：员工这个对象只有编号，没有任何一张表在描述它。
BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '看清订单', 'file': {'name': 'nw', 'sha256': 'd' * 64, 'kind': 'table'},
    'sources': {
        '客户': {'records': [{'客户号': 'C1', '名称': '甲'}, {'客户号': 'C2', '名称': '乙'}], 'requests': []},
        '订单': {'records': [{'订单号': 'O1', '客户号': 'C1', '员工号': 'E1', '金额': '100'},
                           {'订单号': 'O2', '客户号': 'C2', '员工号': 'E2', '金额': '50'},
                           {'订单号': 'O3', '客户号': 'C1', '员工号': 'E1', '金额': '70'}], 'requests': []},
    },
}
ONTOLOGY = {
    'object_types': [
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': '客户', 'identity': {'id': '客户号'}}, {'source': '订单', 'identity': {'id': '客户号'}}],
         'attributes': [{'source': '客户', 'path': '名称'}]},
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': '订单', 'identity': {'id': '订单号'}}], 'attributes': [{'source': '订单', 'path': '金额'}]},
        {'key': 'employee', 'label': '员工', 'populated_from': [{'source': '订单', 'identity': {'id': '员工号'}}], 'attributes': []},
    ],
    'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': '订单', 'meaning': '订单属于客户'},
                  {'key': 'order_employee', 'from': 'order', 'to': 'employee', 'source': '订单', 'meaning': '订单由员工负责'}],
    'ignored_fields': [],
}


class IdOnlyTypeTests(unittest.TestCase):
    def test_an_object_no_table_describes_is_named_with_where_its_ids_came_from(self):
        fit = data_fit(ONTOLOGY, BUNDLE)
        self.assertEqual(fit['id_only'], [{'type': 'employee', 'source': '订单', 'field': '员工号', 'count': 2}])

    def test_an_object_a_table_really_describes_is_not_named(self):
        types = [t for t in data_fit(ONTOLOGY, BUNDLE)['id_only']]
        self.assertNotIn('customer', [t['type'] for t in types])   # the customer table is about customers
        self.assertNotIn('order', [t['type'] for t in types])

    def test_it_is_a_caveat_not_a_failed_check(self):
        fit = data_fit(ONTOLOGY, BUNDLE)
        self.assertTrue(all(c['passed'] for c in fit['checks']))   # nothing here is wrong; the person just has to know
        self.assertNotIn('id_only', [c['key'] for c in fit['checks']])


if __name__ == '__main__':
    unittest.main()
