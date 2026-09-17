import unittest

from ontology_poc_generator.ontology_confirm import ConfirmError, confirmed_reference, prefill_from_reference
from tests.test_company_ontology import PROPOSAL
from tests.test_confirm_variants import KEPT


class VariantInputTests(unittest.TestCase):
    def test_a_group_that_does_not_say_which_object_it_belongs_to_is_refused(self):
        for variants in ([{'values': ['C1', 'C2']}], ['C1', 'C2'], [None]):
            with self.subTest(variants=variants), self.assertRaisesRegex(ConfirmError, '哪个对象'):
                confirmed_reference(PROPOSAL, {**KEPT, 'variants': variants})

    def test_a_hand_edited_reference_file_does_not_break_the_next_run(self):
        reference = confirmed_reference(PROPOSAL, KEPT)
        for broken in ('nope', ['x'], [{'type': 'customer'}], [{'values': ['C1', 'C2']}]):
            with self.subTest(broken=broken):
                self.assertEqual(prefill_from_reference(PROPOSAL, {**reference, 'name_variants': broken})['variants'], [])


if __name__ == '__main__':
    unittest.main()
