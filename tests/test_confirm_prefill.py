import unittest

from ontology_poc_generator.ontology_confirm import confirmed_reference, prefill_from_reference
from tests.test_company_ontology import PROPOSAL


class PrefillTests(unittest.TestCase):
    def test_a_new_run_starts_with_what_matched_the_last_confirmation(self):
        ref = confirmed_reference(PROPOSAL, {'types': {'customer': {'verdict': 'ok', 'label': '客户主体'}, 'order': {'verdict': 'ok'}},
                                             'relations': {'order_customer': {'verdict': 'ok'}}, 'added': ['发票']})
        rerun = {**PROPOSAL, 'object_types': [{**t, 'key': f'{t["key"]}_v2'} for t in PROPOSAL['object_types']],
                 'relations': [{**r, 'key': 'belongs', 'from': 'order_v2', 'to': 'customer_v2'} for r in PROPOSAL['relations']]}
        prefill = prefill_from_reference(rerun, ref)
        self.assertEqual(prefill['types'], {'customer_v2': {'verdict': 'ok', 'label': '客户主体'}, 'order_v2': {'verdict': 'ok'}})
        self.assertEqual(prefill['relations'], {'belongs': {'verdict': 'ok'}})
        self.assertEqual(prefill['added'], ['发票'])


if __name__ == '__main__':
    unittest.main()
