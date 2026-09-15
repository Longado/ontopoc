import unittest

from ontology_poc_generator.ontology_eval import data_fit
from tests.test_company_ontology import BUNDLE, PROPOSAL


class DataFitTests(unittest.TestCase):
    def setUp(self):
        self.fit = data_fit(PROPOSAL, BUNDLE)

    def test_field_coverage_per_source(self):
        self.assertEqual(self.fit['fields'], {
            '客户': {'total': 3, 'used': 3, 'ignored': 0, 'unaccounted': 0},
            '订单': {'total': 4, 'used': 4, 'ignored': 0, 'unaccounted': 0}})

    def test_identity_conflicts_show_the_clashing_values(self):
        self.assertEqual(self.fit['identity_conflicts'], [
            {'type': 'customer', 'source': '客户', 'identity': 'C2', 'field': '城市', 'values': ['常州', '无锡']}])

    def test_objects_missing_from_a_source_they_should_appear_in(self):
        self.assertEqual(self.fit['missing_across_sources'], [
            {'type': 'customer', 'source': '客户', 'count': 1, 'examples': ['C9']}])

    def test_relation_link_rate_counts_rows(self):
        self.assertEqual(self.fit['relations'], [{'key': 'order_customer', 'source': '订单', 'rows': 3, 'linked_rows': 3}])

    def test_orphans_and_source_connectivity(self):
        self.assertEqual(self.fit['orphans'], [{'type': 'customer', 'count': 0, 'examples': []},
                                               {'type': 'order', 'count': 0, 'examples': []}])
        self.assertEqual(self.fit['source_groups'], [['客户', '订单']])

    def test_checks_pass_or_fail_only_where_right_and_wrong_are_clear(self):
        self.assertEqual({c['key']: c['passed'] for c in self.fit['checks']}, {
            'fields_accounted': True, 'identity_consistent': False, 'identity_spelling': True, 'relations_link': True,
            'references_resolve': False, 'sources_connected': True})

    def test_an_unconnected_sheet_is_reported(self):
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], '员工': {'records': [{'工号': 'E1'}], 'requests': []}}}
        proposal = {**PROPOSAL, 'object_types': [*PROPOSAL['object_types'], {
            'key': 'employee', 'label': '员工', 'populated_from': [{'source': '员工', 'identity': {'employee_id': '工号'}}],
            'attributes': []}]}
        fit = data_fit(proposal, bundle)
        self.assertEqual(fit['source_groups'], [['客户', '订单'], ['员工']])
        self.assertFalse(next(c for c in fit['checks'] if c['key'] == 'sources_connected')['passed'])


if __name__ == '__main__':
    unittest.main()
