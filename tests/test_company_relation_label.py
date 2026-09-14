import copy
import unittest

from ontology_poc_generator.company_ontology import COMPANY_PROMPT_VERSION, COMPANY_SYSTEM_PROMPT, build_company_ontology
from tests.test_company_ontology import BUNDLE, PROPOSAL, Reply


class RelationLabelTests(unittest.TestCase):
    def test_relations_carry_a_short_name_for_the_graph(self):
        proposal = copy.deepcopy(PROPOSAL)
        proposal['relations'][0]['label'] = '属于'
        ontology = build_company_ontology(BUNDLE, Reply(proposal))
        self.assertEqual(ontology['relations'][0]['label'], '属于')
        self.assertEqual(COMPANY_PROMPT_VERSION, 'company_ontology_modeler.v2')
        self.assertIn('"label": "<2-6', COMPANY_SYSTEM_PROMPT)


if __name__ == '__main__':
    unittest.main()
