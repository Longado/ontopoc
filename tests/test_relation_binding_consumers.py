import unittest

from ontology_poc_generator.mcp_server import list_relations
from ontology_poc_generator.ontology_compare import compare_ontologies, parse_reference
from test_relation_bindings import PROPOSAL


class RelationBindingConsumerTests(unittest.TestCase):
    def test_importing_an_exported_reference_keeps_its_role_bindings(self):
        reference = parse_reference(PROPOSAL)
        self.assertIn('to_identity', reference['relations'][0])
        self.assertEqual(compare_ontologies(reference, PROPOSAL)['counts']['relations']['matched'], 1)

    def test_an_external_agent_can_read_the_same_endpoint_bindings_as_the_ui(self):
        class Session:
            def run(self, _):
                return {'ontology': PROPOSAL, 'evaluation': {}}
        relation = list_relations(Session(), {'saved_as': 'r.json'})['relations'][0]
        self.assertIn('to_identity', relation)
        self.assertEqual(relation['to_identity'], {'id': 'ReportsTo'})


if __name__ == '__main__':
    unittest.main()
