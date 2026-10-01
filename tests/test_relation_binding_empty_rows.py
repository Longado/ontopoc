import unittest
from ontology_poc_generator.ontology_eval import data_fit
from test_relation_bindings import PROPOSAL, BUNDLE


class EmptyEndpointTests(unittest.TestCase):
    def test_empty_parent_number_is_counted_separately_from_broken_references(self):
        relation = data_fit(PROPOSAL, BUNDLE)['relations'][0]
        self.assertEqual(relation.get('empty_rows'), 1)
        self.assertEqual(relation['linked_rows'], 2)
