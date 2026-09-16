import unittest

from ontology_poc_generator.ontology_acceptance import MAX_ACCEPTANCE, AcceptanceError, check_acceptance, parse_acceptance
from tests.test_company_ontology import BUNDLE, PROPOSAL

QUERY = {'start': 'order', 'where': [], 'via': ['order_customer'], 'group_by': [{'via': ['order_customer'], 'field': '客户.名称'}]}
ITEM = {'question': '每个客户有多少订单？', 'query': QUERY, 'note': '按订单号计数，不是按订单行'}


class ParseTests(unittest.TestCase):
    def test_saved_questions_keep_the_words_the_query_and_the_meaning_agreed_with_the_user(self):
        items = parse_acceptance([ITEM])
        self.assertEqual(items[0]['question'], '每个客户有多少订单？')
        self.assertEqual(items[0]['note'], '按订单号计数，不是按订单行')
        self.assertEqual(items[0]['query'], QUERY)

    def test_what_cannot_be_rerun_is_refused(self):
        for items, message in (([], '至少'),
                               ([ITEM] * (MAX_ACCEPTANCE + 1), str(MAX_ACCEPTANCE)),
                               ([{**ITEM, 'query': None}], '查询'),
                               ([{**ITEM, 'question': ''}], '问题'),
                               ([{**ITEM, 'note': 'x' * 201}], '200')):
            with self.subTest(message=message), self.assertRaisesRegex(AcceptanceError, message):
                parse_acceptance(items)


class CheckTests(unittest.TestCase):
    def test_the_same_query_is_run_again_and_says_whether_the_answer_moved(self):
        first = check_acceptance(PROPOSAL, BUNDLE, parse_acceptance([ITEM]))
        self.assertEqual(first['items'][0]['status'], 'answered')
        self.assertIsNone(first['items'][0]['changed'])   # nothing to compare with yet
        again = check_acceptance(PROPOSAL, BUNDLE, first['items'])
        self.assertIs(again['items'][0]['changed'], False)
        self.assertEqual(again['answered'], 1)

        fewer = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': BUNDLE['sources']['订单']['records'][:1], 'requests': []}}}
        moved = check_acceptance(PROPOSAL, fewer, again['items'])
        self.assertIs(moved['items'][0]['changed'], True)
        self.assertEqual(moved['items'][0]['previous']['answer'], again['items'][0]['answer'])

    def test_a_query_whose_field_is_gone_stops_and_names_the_break(self):
        renamed = {**PROPOSAL, 'object_types': [{**t, 'attributes': [a for a in t['attributes'] if a['path'] != '名称']} if t['key'] == 'customer' else t
                                                for t in PROPOSAL['object_types']]}
        out = check_acceptance(renamed, BUNDLE, parse_acceptance([ITEM]))
        self.assertEqual(out['items'][0]['status'], 'broken')
        self.assertIn('名称', out['items'][0]['reason'])
        self.assertEqual(out['answered'], 0)


if __name__ == '__main__':
    unittest.main()
