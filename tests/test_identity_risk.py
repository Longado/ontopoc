import unittest

from ontology_poc_generator.ontology_eval import data_fit
from tests.test_company_ontology import BUNDLE, PROPOSAL


def by_name(proposal):
    """The same ontology, but the customer is identified by its name instead of its number."""
    types = []
    for t in proposal['object_types']:
        if t['key'] == 'customer':
            t = {**t, 'populated_from': [{'source': '客户', 'identity': {'customer_name': '名称'}}],
                 'attributes': [{'source': '客户', 'path': '城市'}]}
        types.append(t)
    return {**proposal, 'object_types': types}


class IdentityRiskTests(unittest.TestCase):
    def test_an_object_identified_only_by_a_name_is_flagged_because_renaming_would_split_it(self):
        risks = data_fit(by_name(PROPOSAL), BUNDLE)['identity_risks']
        self.assertEqual([(r['type'], r['fields']) for r in risks], [('customer', ['名称'])])

    def test_an_object_identified_by_a_number_is_not_flagged(self):
        self.assertEqual(data_fit(PROPOSAL, BUNDLE)['identity_risks'], [])
