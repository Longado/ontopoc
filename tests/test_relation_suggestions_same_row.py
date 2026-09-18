"""How this project's ontologies are built: an object is read from every table that names it, and a relation is two
objects named on the same row. So the relation code can see missing is two objects read from one table with nothing
joining them there. Removing any one relation from the saved real runs and asking for suggestions is the check."""
import unittest

from ontology_poc_generator.relation_suggestions import suggest_relations
from tests.test_relation_suggestions import table

BUNDLE = {'sources': {'orders': table(('订单号', '客户编号', '员工号'), ('O1', 'C1', 'E1'), ('O2', 'C2', ''), ('O3', 'C1', 'E2'))}}


def ontology(*relations):
    pop = lambda field: [{'source': 'orders', 'identity': {'id': field}}]
    return {'object_types': [{'key': 'order', 'label': '订单', 'populated_from': pop('订单号'), 'attributes': []},
                             {'key': 'customer', 'label': '客户', 'populated_from': pop('客户编号'), 'attributes': []},
                             {'key': 'employee', 'label': '员工', 'populated_from': pop('员工号'), 'attributes': []}],
            'relations': [{'key': f'{a}_{b}', 'from': a, 'to': b, 'source': 'orders'} for a, b in relations], 'ignored_fields': [], 'open_questions': []}


class SameRowTests(unittest.TestCase):
    def test_two_objects_on_the_same_rows_with_nothing_joining_them_are_suggested(self):
        found = suggest_relations(ontology(('order', 'customer')), BUNDLE)
        self.assertEqual(found, [{'kind': 'same_row', 'from': 'order', 'to': 'employee', 'via': {'source': 'orders', 'field': '员工号'},
                                  'rows': 3, 'linked': 2}])

    def test_objects_already_joined_through_another_on_that_table_are_left_alone(self):
        self.assertEqual(suggest_relations(ontology(('order', 'customer'), ('order', 'employee')), BUNDLE), [])


if __name__ == '__main__':
    unittest.main()
