import copy
import unittest

from ontology_poc_generator.company_ontology import verify_company_proposal
from ontology_poc_generator.ontology_eval import data_fit
from test_relation_bindings import BUNDLE, PROPOSAL


class BindingValueFeedbackTests(unittest.TestCase):
    def test_reference_columns_reject_container_values_including_empty_ones(self):
        for value in ([1], {'id': 1}, [], {}):
            with self.subTest(value=value):
                bundle = copy.deepcopy(BUNDLE)
                bundle['sources']['Employee']['records'][1]['ReportsTo'] = value
                errors = verify_company_proposal(PROPOSAL, bundle)['errors']
                error = next((e for e in errors if e['code'] == 'relation_binding_invalid'), None)
                self.assertIsNotNone(error)
                self.assertEqual(error['endpoint'], 'to')
                self.assertEqual(error['fields'], ['ReportsTo'])

    def test_reference_columns_allow_scalar_and_empty_values(self):
        for value in ('1', 1, 1.0, None, ''):
            with self.subTest(value=value):
                bundle = copy.deepcopy(BUNDLE)
                bundle['sources']['Employee']['records'][1]['ReportsTo'] = value
                self.assertEqual(verify_company_proposal(PROPOSAL, bundle)['errors'], [])

    def test_unresolved_bridge_references_name_each_role_and_its_column(self):
        bundle = copy.deepcopy(BUNDLE)
        bundle['sources']['Assignment'] = {'records': [
            {'OwnerId': '2', 'ReviewerId': '3'}, {'OwnerId': '999', 'ReviewerId': '998'}], 'requests': []}
        proposal = copy.deepcopy(PROPOSAL)
        proposal['relations'].append({'key': 'reviewed_by', 'from': 'employee', 'to': 'employee',
                                      'source': 'Assignment', 'meaning': '负责人由复核人审核',
                                      'from_identity': {'id': 'OwnerId'}, 'to_identity': {'id': 'ReviewerId'}})
        missing = [m for m in data_fit(proposal, bundle)['missing_across_sources'] if m.get('relation') == 'reviewed_by']
        self.assertEqual({(m['endpoint'], tuple(m['fields']), tuple(m['examples'])) for m in missing},
                         {('from', ('OwnerId',), ('999',)), ('to', ('ReviewerId',), ('998',))})
