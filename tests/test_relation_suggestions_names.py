"""Values alone are not enough: small numbers fall inside any list of ids numbered from 1. On Northwind, shipVia (1-3)
landed in productID; on BART, wheelchair_accessible (0-2) landed in route_id. A person reads a foreign key by its name
as well, so a suggestion needs both."""
import unittest

from ontology_poc_generator.relation_suggestions import suggest_relations
from tests.test_relation_suggestions import ontology, table


class NameTests(unittest.TestCase):
    def test_small_numbers_that_happen_to_be_ids_are_not_a_relation(self):
        bundle = {'sources': {'orders': table(('订单号', 'shipVia'), ('O1', '1'), ('O2', '3')),
                              'suppliers': table(('供应商编号', '名称'), ('1', '甲'), ('2', '乙'), ('3', '丙'))}}
        self.assertEqual(suggest_relations(ontology(), bundle), [])

    def test_the_same_values_under_a_name_that_says_so_are(self):
        bundle = {'sources': {'orders': table(('订单号', '供应商编号'), ('O1', '1'), ('O2', '3')),
                              'suppliers': table(('供应商编号', '名称'), ('1', '甲'), ('2', '乙'), ('3', '丙'))}}
        self.assertEqual([(s['from'], s['to']) for s in suggest_relations(ontology(), bundle)], [('order', 'supplier')])


if __name__ == '__main__':
    unittest.main()
