"""Two ways a name link can mislead. On Northwind, shipName names the order's customer on all 796 matching rows, the
same customer customerID already gives: the relation said twice. On the Hong Kong licences, one restaurant happens to
be called what a district is called: one name cannot show a pattern."""
import unittest

from ontology_poc_generator.relation_suggestions import suggest_relations
from tests.test_relation_suggestions import table

CUSTOMERS = table(('客户编号', '公司名称'), ('C1', '甲公司'), ('C2', '乙公司'), ('C3', '丙公司'))


def ontology(ship_field):
    return {'object_types': [
        {'key': 'order', 'label': '订单', 'populated_from': [{'source': 'orders', 'identity': {'id': '订单号'}}], 'attributes': [{'source': 'orders', 'path': ship_field}]},
        {'key': 'customer', 'label': '客户', 'populated_from': [{'source': 'orders', 'identity': {'id': '客户编号'}}, {'source': 'customers', 'identity': {'id': '客户编号'}}],
         'attributes': [{'source': 'customers', 'path': '公司名称'}]}],
        'relations': [{'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': 'orders'}], 'ignored_fields': [], 'open_questions': []}


class RepeatTests(unittest.TestCase):
    def test_a_name_that_always_leads_where_an_existing_relation_leads_is_not_a_new_relation(self):
        orders = table(('订单号', '客户编号', '收货方'), ('O1', 'C1', '甲公司'), ('O2', 'C2', '乙公司'), ('O3', 'C1', '甲公司'))
        found = suggest_relations(ontology('收货方'), {'sources': {'orders': orders, 'customers': CUSTOMERS}})
        self.assertEqual([x for x in found if x['kind'] == 'alternate_key'], [])

    def test_a_name_that_leads_elsewhere_even_once_is(self):
        orders = table(('订单号', '客户编号', '收货方'), ('O1', 'C1', '甲公司'), ('O2', 'C2', '丙公司'), ('O3', 'C1', '甲公司'))
        found = [x for x in suggest_relations(ontology('收货方'), {'sources': {'orders': orders, 'customers': CUSTOMERS}}) if x['kind'] == 'alternate_key']
        self.assertEqual([(x['via']['field'], x['linked']) for x in found], [('收货方', 3)])

    def test_one_matching_name_is_not_a_pattern(self):
        orders = table(('订单号', '客户编号', '备注'), ('O1', 'C1', '甲公司'), ('O2', 'C2', '加急'), ('O3', 'C1', '周末送'))
        found = suggest_relations(ontology('备注'), {'sources': {'orders': orders, 'customers': CUSTOMERS}})
        self.assertEqual([x for x in found if x['kind'] == 'alternate_key'], [])


if __name__ == '__main__':
    unittest.main()
