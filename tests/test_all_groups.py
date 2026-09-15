import unittest

from ontology_poc_generator.ontology_questions import run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL


class AllGroupsTests(unittest.TestCase):
    def test_every_group_is_returned_so_the_page_can_show_them_all(self):
        orders = [{'订单号': f'O{i}', '客户编号': 'C1', '金额': str(i), '下单日期': '2026-01-02'} for i in range(25)]
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': orders, 'requests': []}}}
        result = run_query(PROPOSAL, bundle, {'start': 'order', 'group_by': [{'via': [], 'field': '订单.金额'}]})
        self.assertEqual((len(result['answer']['groups']), result['answer']['total_groups']), (25, 25))


if __name__ == '__main__':
    unittest.main()
