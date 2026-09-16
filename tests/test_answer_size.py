import json
import unittest

from ontology_poc_generator.ontology_questions import MAX_GROUPS, run_query
from tests.test_company_ontology import BUNDLE, PROPOSAL

LIMIT = 400 * 1024   # a result has to fit the browser's storage beside everything else in the run


class AnswerSizeTests(unittest.TestCase):
    def test_an_answer_stays_small_even_when_every_group_name_is_long(self):
        long = '某某某某某某某某某某某某某某某某某某某某某某某某某某某某某某'   # 30 chars, as long as a real product name gets
        orders = [{'订单号': f'O{i}', '客户编号': 'C1', '金额': f'{long}{i}', '下单日期': '2026-01-02'} for i in range(MAX_GROUPS * 3)]
        bundle = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': orders, 'requests': []}}}
        answer = run_query(PROPOSAL, bundle, {'start': 'order', 'group_by': [{'via': [], 'field': '订单.金额'}]})['answer']
        self.assertLess(len(json.dumps(answer, ensure_ascii=False).encode()), LIMIT)
        self.assertEqual(answer['total_groups'], MAX_GROUPS * 3)


if __name__ == '__main__':
    unittest.main()
