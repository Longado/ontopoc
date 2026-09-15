import unittest

from ontology_poc_generator.ontology_questions import _catalog, run_query
from ontology_poc_generator.ontology_stability import stability_of
from tests.test_company_ontology import BUNDLE, PROPOSAL
from tests.test_ontology_stability import FIRST, ontology


class IdentityFieldTests(unittest.TestCase):
    """A type identified by its name (a department) has no other attribute; its identity field must still group."""

    def test_group_by_an_identity_field(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'group_by': [{'via': ['order_customer'], 'field': '客户编号'}]})
        self.assertEqual(result['status'], 'answered', result)
        self.assertEqual(result['answer']['groups'], [['C1', 1], ['C2', 1], ['C9', 1]])

    def test_identity_fields_are_listed_for_the_question_model(self):
        customer = next(t for t in _catalog(PROPOSAL, BUNDLE)['object_types'] if t['key'] == 'customer')
        self.assertIn({'path': '客户编号', 'identity': True}, [{k: v for k, v in a.items() if k != 'values'} for a in customer['attributes']])


class FailedRunReasonTests(unittest.TestCase):
    def test_a_failed_extra_run_keeps_its_reason(self):
        blocked = ontology([], [], status='blocked')
        blocked['attempts'] = [{'errors': [{'code': 'relation_source_mismatch'}]}, {'errors': [{'code': 'time_field_invalid'}, {'code': 'time_field_invalid'}]}]
        crashed = {'status': 'failed', 'error': 'TimeoutError: read timed out'}
        result = stability_of(FIRST, [blocked, crashed])
        self.assertEqual(result['failures'], [{'codes': ['time_field_invalid']}, {'error': 'TimeoutError: read timed out'}])


if __name__ == '__main__':
    unittest.main()
