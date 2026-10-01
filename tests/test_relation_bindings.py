"""Relation roles refer to existing objects without creating a second copy of their source row."""
import copy
import unittest

from ontology_poc_generator.company_ontology import build_company_ontology, verify_company_proposal
from ontology_poc_generator.ontology_eval import data_fit
from ontology_poc_generator.ontology_questions import run_query
from ontology_poc_generator.public_ontology import build_graph
from test_company_ontology import Reply


BUNDLE = {
    'schema': 'company_source_bundle.v1', 'decision': '员工向谁汇报？',
    'file': {'name': 'employees.csv', 'sha256': 'b' * 64, 'kind': 'table'},
    'sources': {'Employee': {'records': [
        {'EmployeeId': '1', 'Name': '主管', 'ReportsTo': ''},
        {'EmployeeId': '2', 'Name': '甲', 'ReportsTo': '1'},
        {'EmployeeId': '3', 'Name': '乙', 'ReportsTo': '1'},
    ], 'requests': []}},
}
PROPOSAL = {
    'object_types': [{'key': 'employee', 'label': '员工',
                     'populated_from': [{'source': 'Employee', 'identity': {'id': 'EmployeeId'}}],
                     'attributes': [{'source': 'Employee', 'path': 'Name'}]}],
    'relations': [{'key': 'reports_to', 'from': 'employee', 'to': 'employee', 'source': 'Employee',
                   'label': '汇报给', 'meaning': '员工向上级汇报',
                   'from_identity': {'id': 'EmployeeId'}, 'to_identity': {'id': 'ReportsTo'}}],
    'ignored_fields': [], 'open_questions': [],
}


class RelationBindingTests(unittest.TestCase):
    def test_employee_manager_edges_are_directed_and_reference_fields_are_accounted(self):
        self.assertEqual(verify_company_proposal(PROPOSAL, BUNDLE)['errors'], [])
        edges = build_graph(PROPOSAL, BUNDLE)['edges']['reports_to']
        self.assertEqual({(a[1][0][1], b[1][0][1]) for a, b, _ in edges}, {('2', '1'), ('3', '1')})

    def test_manager_attributes_come_from_its_own_row(self):
        graph = build_graph(PROPOSAL, BUNDLE)
        self.assertEqual(graph['records_of'][('employee', (('id', '1'),))], [('Employee', 0)])
        fit = data_fit(PROPOSAL, BUNDLE)
        self.assertEqual(fit['fields']['Employee']['unaccounted'], 0)
        self.assertEqual(fit['identity_conflicts'], [])

    def test_missing_manager_is_reported_without_creating_an_employee(self):
        bundle = copy.deepcopy(BUNDLE)
        bundle['sources']['Employee']['records'][2]['ReportsTo'] = '999'
        graph = build_graph(PROPOSAL, bundle)
        self.assertEqual(len(graph['sources_of']), 3)
        self.assertEqual(len(graph['edges']['reports_to']), 1)
        fit = data_fit(PROPOSAL, bundle)
        check = next(c for c in fit['checks'] if c['key'] == 'references_resolve')
        self.assertFalse(check['passed'])
        self.assertTrue(any('999' in item['examples'] for item in fit['missing_across_sources']))

    def test_two_roles_in_another_table_do_not_cross_connect(self):
        bundle = copy.deepcopy(BUNDLE)
        bundle['sources']['Assignment'] = {'records': [{'OwnerId': '2', 'ReviewerId': '3'}], 'requests': []}
        proposal = copy.deepcopy(PROPOSAL)
        proposal['relations'].append({'key': 'reviewed_by', 'from': 'employee', 'to': 'employee',
                                      'source': 'Assignment', 'meaning': '负责人由复核人审核',
                                      'from_identity': {'id': 'OwnerId'}, 'to_identity': {'id': 'ReviewerId'}})
        self.assertEqual(verify_company_proposal(proposal, bundle)['errors'], [])
        edges = build_graph(proposal, bundle)['edges']['reviewed_by']
        self.assertEqual({(a[1][0][1], b[1][0][1]) for a, b, _ in edges}, {('2', '3')})

    def test_invalid_bindings_return_specific_feedback_instead_of_crashing(self):
        for binding in ([], None, {}, {'other_key': 'ReportsTo'}, {'id': 'Missing'}, {'id': 42}, {'id': 'items[].id'}):
            with self.subTest(binding=binding):
                proposal = copy.deepcopy(PROPOSAL)
                proposal['relations'][0]['to_identity'] = binding
                errors = verify_company_proposal(proposal, BUNDLE)['errors']
                self.assertIn('relation_binding_invalid', {e['code'] for e in errors})
                error = next(e for e in errors if e['code'] == 'relation_binding_invalid')
                self.assertEqual(error['relation'], 'reports_to')
                self.assertEqual(error['endpoint'], 'to')
                self.assertEqual(error['source'], 'Employee')
                self.assertTrue(error['hint'])

    def test_a_bound_relation_cannot_name_an_unknown_table(self):
        proposal = copy.deepcopy(PROPOSAL)
        proposal['relations'][0]['source'] = 'Unknown'
        self.assertTrue(verify_company_proposal(proposal, BUNDLE)['errors'])

    def test_only_one_explicit_role_of_a_self_relation_is_ambiguous(self):
        proposal = copy.deepcopy(PROPOSAL)
        del proposal['relations'][0]['to_identity']
        self.assertIn('relation_binding_invalid', {e['code'] for e in verify_company_proposal(proposal, BUNDLE)['errors']})

    def test_legacy_relations_still_use_their_populations(self):
        from test_company_ontology import BUNDLE as legacy_bundle, PROPOSAL as legacy_proposal
        self.assertEqual(verify_company_proposal(legacy_proposal, legacy_bundle)['errors'], [])
        self.assertEqual(len(build_graph(legacy_proposal, legacy_bundle)['edges']['order_customer']), 3)

    def test_retry_keeps_verified_endpoint_bindings_in_the_saved_ontology(self):
        wrong = copy.deepcopy(PROPOSAL)
        wrong['relations'][0]['to_identity'] = {'id': 'Missing'}
        gateway = Reply(wrong, PROPOSAL)
        ontology = build_company_ontology(BUNDLE, gateway)
        self.assertEqual(ontology['status'], 'auto_built_verified')
        self.assertEqual(len(ontology['attempts']), 2)
        self.assertEqual(ontology['relations'][0]['to_identity'], {'id': 'ReportsTo'})
        self.assertEqual(gateway.prompts[1][1]['errors_found_by_code'][0]['relation'], 'reports_to')

    def test_query_reports_its_direction_limit_instead_of_mixing_managers_and_reports(self):
        query = {'start': 'employee', 'where': [{'field': 'EmployeeId', 'equals': '2'}], 'via': ['reports_to']}
        answer = run_query(PROPOSAL, BUNDLE, query)
        self.assertEqual(answer['status'], 'query_limit')
        self.assertIn('方向', answer['reason'])

    def test_a_changed_role_binding_does_not_inherit_confirmation_or_stability(self):
        from ontology_poc_generator.ontology_confirm import confirmed_reference, prefill_from_reference
        from ontology_poc_generator.ontology_stability import stability_of
        decisions = {'types': {'employee': {'verdict': 'ok'}}, 'relations': {'reports_to': {'verdict': 'ok'}}}
        reference = confirmed_reference(PROPOSAL, decisions)
        self.assertEqual(reference['relations'][0]['to_identity'], {'id': 'ReportsTo'})
        turned = copy.deepcopy(PROPOSAL)
        turned['relations'][0]['from_identity'], turned['relations'][0]['to_identity'] = (
            turned['relations'][0]['to_identity'], turned['relations'][0]['from_identity'])
        self.assertEqual(prefill_from_reference(turned, reference)['relations'], {})
        self.assertEqual(stability_of(PROPOSAL, [{**turned, 'status': 'auto_built_verified'}])['relations']['reports_to'], 1)

    def test_comparison_does_not_call_changed_bindings_the_same_relation(self):
        from ontology_poc_generator.ontology_compare import compare_ontologies
        changed = copy.deepcopy(PROPOSAL)
        changed['relations'][0]['to_identity'] = {'id': 'EmployeeId'}
        self.assertEqual(compare_ontologies(PROPOSAL, changed)['counts']['relations']['matched'], 0)


if __name__ == '__main__':
    unittest.main()
