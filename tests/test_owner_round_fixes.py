import copy
import unittest

from ontology_poc_generator.company_ontology import build_company_ontology
from ontology_poc_generator.ontology_questions import run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL, Reply


class RetryTests(unittest.TestCase):
    def test_a_retry_that_fixes_one_error_and_hits_another_gets_its_third_attempt(self):
        wrong_table = copy.deepcopy(PROPOSAL)
        wrong_table['relations'][0]['source'] = '客户'
        missing_field = copy.deepcopy(PROPOSAL)
        missing_field['object_types'][1]['attributes'] = [a for a in missing_field['object_types'][1]['attributes'] if a['path'] != '金额']
        gateway = Reply(wrong_table, missing_field, PROPOSAL)
        ontology = build_company_ontology(BUNDLE, gateway)
        self.assertEqual(len(gateway.prompts), 3)
        self.assertEqual(ontology['status'], 'auto_built_verified')

    def test_the_same_errors_again_still_stop_early(self):
        missing_field = copy.deepcopy(PROPOSAL)
        missing_field['object_types'][1]['attributes'] = []
        gateway = Reply(missing_field, missing_field, PROPOSAL)
        self.assertEqual(build_company_ontology(BUNDLE, gateway)['status'], 'blocked')
        self.assertEqual(len(gateway.prompts), 2)


class QueryPathTests(unittest.TestCase):
    def test_the_path_says_which_records_were_kept(self):
        result = run_query(PROPOSAL, BUNDLE, {'start': 'order', 'where': [{'field': '订单.金额', 'equals': '100'}], 'via': ['order_customer'], 'group_by': '客户.名称'})
        self.assertEqual(result['path'], '只看“金额”为“100”的订单 → 客户，按“名称”分组数订单')


if __name__ == '__main__':
    unittest.main()
