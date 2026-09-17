import unittest

from ontology_poc_generator.ontology_acceptance import AcceptanceError, check_acceptance, parse_acceptance, snapshot_of
from tests.test_company_ontology import BUNDLE, PROPOSAL

ANSWERED = {'question': '每个客户有多少订单？', 'note': '按订单号计数',
            'query': {'start': 'order', 'where': [], 'via': ['order_customer'], 'group_by': '客户.名称'}}
UNMET = {'question': '上个月延期造成的金额是多少？', 'query': None, 'note': '客户点名要的',
         'status': 'query_limit', 'reason': '查询还不能限定时间段'}


class UnmetAcceptanceTests(unittest.TestCase):
    def test_a_question_that_cannot_be_answered_yet_can_still_be_fixed(self):
        items = parse_acceptance([ANSWERED, UNMET])
        self.assertEqual([i['question'] for i in items], [ANSWERED['question'], UNMET['question']])
        self.assertEqual((items[1]['query'], items[1]['status'], items[1]['reason']), (None, 'query_limit', '查询还不能限定时间段'))

    def test_only_a_question_that_was_really_asked_and_failed_may_be_saved_without_a_query(self):
        for item, message in (({**UNMET, 'status': 'answered'}, '没有查询'), ({**UNMET, 'status': None}, '没有查询'),
                              ({**UNMET, 'reason': ''}, '原因')):
            with self.subTest(item=item), self.assertRaisesRegex(AcceptanceError, message):
                parse_acceptance([item])

    def test_the_unmet_question_stays_in_the_count_so_the_others_cannot_hide_it(self):
        items = parse_acceptance([{**ANSWERED, 'snapshot': snapshot_of(PROPOSAL, ANSWERED['query'])}, UNMET])
        out = check_acceptance(PROPOSAL, BUNDLE, items)
        self.assertEqual((out['answered'], out['total']), (1, 2))
        unmet = out['items'][1]
        self.assertEqual((unmet['status'], unmet['reason'], unmet['query'], unmet['changed']), ('query_limit', '查询还不能限定时间段', None, None))
        again = check_acceptance(PROPOSAL, BUNDLE, out['items'])   # a rerun reads back what it wrote
        self.assertEqual((again['answered'], again['total'], again['items'][1]['status']), (1, 2, 'query_limit'))


if __name__ == '__main__':
    unittest.main()
