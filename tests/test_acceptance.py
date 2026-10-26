from datetime import datetime
import unittest

from ontology_poc_generator import ontology_acceptance
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

    def test_what_the_person_agreed_to_is_never_taken_from_the_request(self):
        forged = {'status': 'answered', 'answer': {'total': 9}, 'path': '', 'at': '2020-01-01T00:00:00+00:00', 'file': 'f', 'saved_as': 'x.json'}
        self.assertNotIn('confirmed', parse_acceptance([{**ITEM, 'confirmed': forged}])[0])

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

    def test_an_item_with_a_confirmation_is_compared_with_what_the_person_agreed_to_not_with_the_last_run(self):
        first = check_acceptance(PROPOSAL, BUNDLE, parse_acceptance([ITEM]))['items'][0]
        confirmed = {'status': first['status'], 'answer': first['answer'], 'path': first['path'],
                     'at': '2026-10-01T08:00:00+00:00', 'file': 'sha-of-the-agreed-file', 'saved_as': 'first.json'}
        fewer = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': BUNDLE['sources']['订单']['records'][:1], 'requests': []}}}
        moved = check_acceptance(PROPOSAL, fewer, [{**first, 'confirmed': confirmed}])
        again = check_acceptance(PROPOSAL, fewer, moved['items'])   # the same changed data a second time: still not what was agreed
        for run in (moved, again):
            item = run['items'][0]
            self.assertIs(item['changed'], True)
            self.assertEqual(item['previous'], {'status': 'answered', 'answer': first['answer'], 'path': first['path'],
                                                'confirmed_at': '2026-10-01T08:00:00+00:00', 'confirmed_file': 'sha-of-the-agreed-file'})
            self.assertEqual(item['confirmed'], confirmed)
        back = check_acceptance(PROPOSAL, BUNDLE, again['items'])
        self.assertIs(back['items'][0]['changed'], False)
        # a status that is no longer answered differs from the agreement too
        renamed = {**PROPOSAL, 'object_types': [{**t, 'attributes': [a for a in t['attributes'] if a['path'] != '名称']} if t['key'] == 'customer' else t
                                                for t in PROPOSAL['object_types']]}
        broken = check_acceptance(renamed, BUNDLE, back['items'])['items'][0]
        self.assertEqual((broken['status'], broken['changed'], broken['previous']['status']), ('broken', True, 'answered'))

    def test_an_item_without_a_confirmation_is_compared_with_the_last_run_and_stays_without_one(self):
        first = check_acceptance(PROPOSAL, BUNDLE, parse_acceptance([ITEM]))
        again = check_acceptance(PROPOSAL, BUNDLE, first['items'])['items'][0]
        self.assertNotIn('confirmed', again)
        self.assertEqual(set(again['previous']), {'status', 'answer', 'path'})

    def test_the_check_pack_never_decides_whether_an_answer_changed(self):
        filtered = parse_acceptance([{'question': '金额 100 的订单有几个？', 'query': {'start': 'order', 'where': [{'field': '订单.金额', 'equals': '100'}]}}])
        first = check_acceptance(PROPOSAL, BUNDLE, filtered)
        self.assertEqual(first['items'][0]['evidence']['filters'][0]['before'], 3)
        extra = {'订单号': 'O4', '客户编号': 'C1', '金额': '55', '下单日期': '2026-01-05'}   # one more object the filter removes: the answer is the same
        more = {**BUNDLE, 'sources': {**BUNDLE['sources'], '订单': {'records': [*BUNDLE['sources']['订单']['records'], extra], 'requests': []}}}
        again = check_acceptance(PROPOSAL, more, first['items'])
        self.assertEqual(again['items'][0]['evidence']['filters'][0]['before'], 4)
        self.assertIs(again['items'][0]['changed'], False)

    def test_a_query_whose_field_is_gone_stops_and_names_the_break(self):
        renamed = {**PROPOSAL, 'object_types': [{**t, 'attributes': [a for a in t['attributes'] if a['path'] != '名称']} if t['key'] == 'customer' else t
                                                for t in PROPOSAL['object_types']]}
        out = check_acceptance(renamed, BUNDLE, parse_acceptance([ITEM]))
        self.assertEqual(out['items'][0]['status'], 'broken')
        self.assertIn('名称', out['items'][0]['reason'])
        self.assertEqual(out['answered'], 0)


class RecordConfirmedTests(unittest.TestCase):
    def test_a_question_accepted_now_keeps_the_answer_this_check_gave_and_which_file_it_came_from(self):
        checked = check_acceptance(PROPOSAL, BUNDLE, parse_acceptance([ITEM, {**ITEM, 'question': '另一道'}]))
        out = ontology_acceptance.record_confirmed(checked, {ITEM['question']}, 'sha-1', 'run-1.json')
        done, untouched = out['items']
        confirmed = done['confirmed']
        self.assertEqual({k: confirmed[k] for k in ('status', 'answer', 'path', 'file', 'saved_as')},
                         {'status': 'answered', 'answer': checked['items'][0]['answer'], 'path': checked['items'][0]['path'], 'file': 'sha-1', 'saved_as': 'run-1.json'})
        self.assertIsNotNone(datetime.fromisoformat(confirmed['at']))
        self.assertNotIn('confirmed', untouched)
        self.assertNotIn('confirmed', checked['items'][0])   # the checked items are not changed in place
        self.assertIsNone(done['changed'])   # nothing earlier to compare with: accepting is not a rerun

    def test_nothing_is_agreed_when_the_fresh_check_did_not_answer(self):
        renamed = {**PROPOSAL, 'object_types': [{**t, 'attributes': [a for a in t['attributes'] if a['path'] != '名称']} if t['key'] == 'customer' else t
                                                for t in PROPOSAL['object_types']]}
        checked = check_acceptance(renamed, BUNDLE, parse_acceptance([ITEM]))
        out = ontology_acceptance.record_confirmed(checked, {ITEM['question']}, 'sha-1', 'run-1.json')
        self.assertEqual(checked['items'][0]['status'], 'broken')
        self.assertNotIn('confirmed', out['items'][0])


if __name__ == '__main__':
    unittest.main()
