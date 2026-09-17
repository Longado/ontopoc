import unittest

from ontology_poc_generator.ontology_confirm import ConfirmError, confirmed_reference, prefill_from_reference
from tests.test_company_ontology import PROPOSAL

KEPT = {'types': {'customer': {'verdict': 'ok', 'label': '客户主体'}, 'order': {'verdict': 'ok'}},
        'relations': {'order_customer': {'verdict': 'ok'}}, 'added': []}
SAME = [{'type': 'customer', 'values': ['C2', 'C1']}]


class ConfirmedVariantTests(unittest.TestCase):
    def test_the_spellings_a_person_accepted_are_kept_with_the_object_they_belong_to(self):
        ref = confirmed_reference(PROPOSAL, {**KEPT, 'variants': SAME})
        self.assertEqual(ref['name_variants'], [{'type': 'customer', 'values': ['C1', 'C2']}])

    def test_nothing_is_written_when_no_group_was_accepted(self):
        self.assertNotIn('name_variants', confirmed_reference(PROPOSAL, KEPT))

    def test_groups_that_do_not_fit_the_confirmation_are_refused(self):
        for variants, message in (
                ([{'type': 'invoice', 'values': ['C1', 'C2']}], 'invoice'),
                ([{'type': 'customer', 'values': ['C1']}], '两个'),
                ([{'type': 'customer', 'values': ['C1', 1]}], '两个'),
                ([{'type': 'customer', 'values': ['C1', 'C1']}], '两个'),
                ('nope', '格式')):
            with self.subTest(message=message), self.assertRaisesRegex(ConfirmError, message):
                confirmed_reference(PROPOSAL, {**KEPT, 'variants': variants})

    def test_a_group_on_an_object_judged_wrong_is_refused(self):
        with self.assertRaisesRegex(ConfirmError, '客户'):
            confirmed_reference(PROPOSAL, {**KEPT, 'types': {'customer': {'verdict': 'wrong'}, 'order': {'verdict': 'ok'}},
                                           'relations': {}, 'variants': SAME})

    def test_a_rerun_starts_with_the_spellings_already_accepted_for_that_object(self):
        ref = confirmed_reference(PROPOSAL, {**KEPT, 'variants': SAME})
        rerun = {**PROPOSAL, 'object_types': [{**t, 'key': f'{t["key"]}_v2'} for t in PROPOSAL['object_types']],
                 'relations': [{**r, 'key': 'belongs', 'from': 'order_v2', 'to': 'customer_v2'} for r in PROPOSAL['relations']]}
        self.assertEqual(prefill_from_reference(rerun, ref)['variants'], [{'type': 'customer_v2', 'values': ['C1', 'C2']}])

    def test_a_rerun_that_no_longer_has_that_object_starts_without_its_spellings(self):
        ref = confirmed_reference(PROPOSAL, {**KEPT, 'variants': SAME})
        rerun = {**PROPOSAL, 'object_types': [t for t in PROPOSAL['object_types'] if t['key'] != 'customer'], 'relations': []}
        self.assertEqual(prefill_from_reference(rerun, ref)['variants'], [])


if __name__ == '__main__':
    unittest.main()
