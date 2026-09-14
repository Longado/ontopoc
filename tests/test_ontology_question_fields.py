import unittest

from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION, run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL


class FieldFormTests(unittest.TestCase):
    """A formatting slip by the model must not be scored as a gap in the ontology."""

    def test_table_type_or_bare_field_names_all_resolve_to_the_same_attribute(self):
        for group_by in ('客户.名称', 'customer.名称', '名称'):
            with self.subTest(group_by=group_by):
                result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'via': ['order_customer'], 'group_by': group_by})
                self.assertEqual(result['status'], 'answered')
                self.assertEqual(result['answer']['groups'], [['乙', 1], ['甲', 1]])
        for field in ('订单.金额', 'order.金额', '金额'):
            with self.subTest(field=field):
                self.assertEqual(run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [{'field': field, 'equals': '100'}]})['answer'],
                                 {'total': 1})

    def test_a_field_the_type_really_lacks_is_still_a_gap(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'via': [], 'group_by': 'order.城市'})
        self.assertEqual(result['status'], 'ontology_gap')

    def test_the_prompt_asks_for_bare_attribute_names(self):
        self.assertEqual(QUESTION_PROMPT_VERSION, 'company_questions.v2')


if __name__ == '__main__':
    unittest.main()
