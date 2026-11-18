"""The assistant's assumptions and self-check, worked out by code from what a draft already contains (no model call, no prompt change): each assumption is confirmed
(with a link to its definition) or open; the self-check lists what was done and what was not. Pure functions, in both languages."""
import unittest

from ontology_poc_generator import lang
from ontology_poc_generator.assistant_checks import blocks_apply, plan_assumptions, plan_self_check, type_assumptions, type_self_check

STEP = {'id': 'ai1', 'summary': 's', 'rows_in': [160], 'rows_out': 144, 'failures': {}}
CITE = {'column': '状态码', 'meaning': '已取消', 'codes': ['2'], 'text': 'cited sentence', 'definition': 'enum:order:状态码'}
QUESTION = {'id': '状态码|已取消', 'column': '状态码', 'concept': '已取消', 'ask': 'Which code?', 'evidence': 'Not confirmed', 'options': []}


class PlanTests(unittest.TestCase):
    def test_confirmed_meanings_are_confirmed_assumptions_with_a_link_and_open_questions_are_open(self):
        out = {'cites': [CITE], 'questions': [QUESTION], 'steps': [STEP], 'check': {'ok': True, 'dry_run': 'tried'}}
        found = plan_assumptions(out, {})
        self.assertEqual([(a['status'], a['text'], a.get('definition')) for a in found], [('confirmed', 'cited sentence', 'enum:order:状态码'), ('open', 'Which code?', None)])
        self.assertEqual(found[1]['question'], '状态码|已取消')
        self.assertTrue(blocks_apply(found))
        self.assertFalse(blocks_apply(found[:1]))

    def test_an_answered_question_becomes_a_confirmed_assumption_stated_as_the_person_s(self):
        out = {'cites': [], 'questions': [], 'steps': [STEP], 'check': {'ok': True}}
        with lang.speaking('en'):
            [a] = plan_assumptions(out, {'状态码|已取消': ['2']})
            self.assertEqual((a['status'], a['by']), ('confirmed', 'you'))
            self.assertEqual(a['text'], 'You chose "2" for "已取消" in "状态码"')
        with lang.speaking('zh'):
            self.assertEqual(plan_assumptions(out, {'状态码|已取消': ['2']})[0]['text'], '你选定：「状态码」里“已取消”是 2')
        self.assertEqual(plan_assumptions(out, {'状态码|已取消': []}), [])   # an empty answer is no answer

    def test_the_self_check_says_what_was_done_and_what_was_not(self):
        out = {'cites': [CITE], 'questions': [QUESTION], 'steps': [STEP, {**STEP, 'id': 'ai2', 'failures': {'x': 1}}], 'check': {'ok': True, 'dry_run': 'Tried on the current data'}}
        with lang.speaking('en'):
            got = plan_self_check(out)
        self.assertEqual([x['key'] for x in got['done']], ['columns', 'dry', 'counts', 'cites'])
        self.assertEqual([x['key'] for x in got['not_done']], ['open', 'stepFailures', 'fullRun', 'saved'])
        self.assertEqual(got['done'][0]['text'], 'Columns, operators and functions exist')
        self.assertEqual(got['done'][1]['text'], 'Tried on the current data')
        self.assertEqual(got['not_done'][3]['text'], 'Saved: nothing is in a pipeline yet')
        failed = plan_self_check({'cites': [], 'questions': [], 'steps': [], 'check': {'ok': False, 'error': 'bad column'}})
        self.assertEqual([x['key'] for x in failed['done']], [])
        self.assertEqual(failed['not_done'][0]['key'], 'failed')
        self.assertIn('bad column', failed['not_done'][0]['text'])
        with lang.speaking('zh'):
            self.assertEqual(plan_self_check(out)['done'][0]['text'], '列、操作和函数都存在')


class TypeTests(unittest.TestCase):
    def test_a_key_the_code_checked_is_confirmed_and_a_code_column_nobody_confirmed_is_open(self):
        with lang.speaking('en'):
            found = type_assumptions('order', ['订单号'], 160, ['状态码'])
        self.assertEqual([(a['status'], a.get('definition')) for a in found], [('confirmed', 'objtype:order'), ('open', 'enum:order:状态码')])
        self.assertEqual(found[0]['text'], 'The key (订单号) is unique and filled on all 160 rows')
        self.assertEqual(found[1]['text'], 'Nobody has confirmed what the codes in "状态码" mean')
        self.assertTrue(blocks_apply(found))
        self.assertFalse(blocks_apply(type_assumptions('order', ['订单号'], 160, [])))

    def test_the_type_self_check_counts_what_was_kept_and_dropped(self):
        with lang.speaking('en'):
            got = type_self_check(2, 1)
        self.assertEqual([x['key'] for x in got['done']], ['checked', 'kept'])
        self.assertEqual([x['key'] for x in got['not_done']], ['confirmed', 'dropped'])
        self.assertEqual(type_self_check(0, 0), {'done': [], 'not_done': []})


if __name__ == '__main__':
    unittest.main()
