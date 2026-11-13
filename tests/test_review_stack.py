"""The review stack: the reply menu of each kind, what a reply keeps (who, one by one or in bulk, and for "not applicable" and
"exception" what the item was about), and when such a decision comes back. Numbers are the planted fixtures'
(tests/fixtures/planted): 客户 KH012 is on two rows (合肥 / 苏州), 订单.状态码 has 0, 1 and 2 on 96, 48 and 16 of 160 rows."""
import base64
import copy
import unittest

from ontology_poc_generator.ontology_card import CardError
from ontology_poc_generator.open_items import check_answers, linked_cells, split_answers
from ontology_poc_generator.review_stack import anchor_changes, menu
from tests.test_open_items import AT, AnswerTests
from tests.test_open_items_server import fetch
from tests.test_ontology_server import OntologyServerTests
from tests.test_ontology_ask_server import call


def ids(kind):
    return [m['id'] for m in menu(kind)]


class MenuTests(unittest.TestCase):
    def test_every_kind_offers_at_most_four_replies_and_the_ones_that_close_it_without_a_choice_always_include_an_exception(self):
        for kind in ('unlinked', 'same_name', 'merged', 'found_elsewhere', 'unstable', 'check_finding', 'data_gap', 'data_gaps', 'unanswered',
                     'name_vs_calc', 'name_source', 'name_by_view', 'name_values', 'code_meaning', 'repeated_key'):
            with self.subTest(kind):
                self.assertLessEqual(len(menu(kind)), 4)
                self.assertIn('exception', ids(kind))

    def test_a_kind_has_its_own_choices_beside_the_general_replies(self):
        self.assertEqual(ids('unlinked'), ['expected', 'incomplete', 'not_applicable', 'exception'])
        self.assertEqual(ids('repeated_key'), ['keep_both', 'keep_latest', 'data_error', 'exception'])
        self.assertEqual(ids('found_elsewhere'), ['confirm', 'wrong', 'not_applicable', 'exception'])
        self.assertEqual(ids('code_meaning'), ['confirm', 'not_applicable', 'exception'])

    def test_what_is_settled_by_doing_something_has_no_replies(self):
        for kind in ('model_filter', 'unjudged', 'card_blank'):
            self.assertEqual(menu(kind), [], kind)

    def test_an_exception_and_a_wrong_reply_need_words_and_a_not_applicable_does_not(self):
        needs = {m['id']: m['needs_text'] for m in menu('found_elsewhere')}
        self.assertEqual(needs, {'confirm': False, 'wrong': True, 'not_applicable': False, 'exception': True})


class ReplyTests(unittest.TestCase):
    """The listed items are AnswerTests': spend_contract and contract_vehicle (unlinked), data_gaps, unjudged."""
    LISTED = AnswerTests.LISTED

    def check(self, *items, by='张三'):
        return check_answers(self.LISTED, list(items), by, AT)

    def test_an_exception_is_kept_with_its_reason_who_gave_it_how_and_what_the_item_was_about(self):
        got = self.check({'id': 'unlinked:spend_contract', 'reply': 'exception', 'text': '这批是测试数据'})['unlinked:spend_contract']
        self.assertEqual((got['reply'], got['text'], got['by'], got['mode'], got['choice']), ('exception', '这批是测试数据', '张三', 'single', None))
        self.assertEqual(got['anchor'], {'noun': '内容', 'members': [], 'counts': {'没连上的行': 1308}, 'total': 1921})

    def test_an_exception_without_a_reason_is_refused(self):
        with self.assertRaisesRegex(CardError, '写原因'):
            self.check({'id': 'unlinked:spend_contract', 'reply': 'exception'})

    def test_not_applicable_needs_no_words_and_bulk_is_recorded_as_bulk(self):
        got = self.check({'id': 'data_gaps', 'reply': 'not_applicable', 'mode': 'bulk'})['data_gaps']
        self.assertEqual((got['reply'], got['text'], got['mode']), ('not_applicable', '', 'bulk'))

    def test_a_mode_that_is_neither_is_refused(self):
        with self.assertRaisesRegex(CardError, 'single 或 bulk'):
            self.check({'id': 'data_gaps', 'reply': 'not_applicable', 'mode': 'many'})

    def test_a_reply_the_kind_does_not_offer_is_refused(self):
        with self.assertRaisesRegex(CardError, 'reply 只能是'):
            self.check({'id': 'unlinked:spend_contract', 'reply': 'wrong', 'text': 'x'})   # a relation's rows are not "wrong": it has its own choices

    def test_a_choice_and_a_reply_together_are_refused(self):
        with self.assertRaisesRegex(CardError, '不能和 choice 一起'):
            self.check({'id': 'unlinked:spend_contract', 'reply': 'exception', 'choice': 'expected', 'text': 'x'})

    def test_what_is_settled_by_doing_something_takes_no_reply(self):
        with self.assertRaisesRegex(CardError, '逐项判对错'):
            self.check({'id': 'unjudged', 'reply': 'exception', 'text': 'x'})

    def test_a_decision_can_be_taken_back_and_the_old_one_stays_in_the_cards_history(self):
        self.assertEqual(self.check({'id': 'unlinked:spend_contract', 'reply': 'reopen'}), {'unlinked:spend_contract': None})

    def test_taking_back_a_data_incomplete_answer_clears_the_card_cell_it_wrote_and_only_that(self):
        listed = [{'id': 'unlinked:a', 'complete_id': 'complete:x'}]
        self.assertEqual(linked_cells(listed, {'unlinked:a': None}, {'complete:x': {'value': 'partial', 'item': 'unlinked:a'}}, AT), {'complete:x': None})
        self.assertEqual(linked_cells(listed, {'unlinked:a': None}, {'complete:x': {'value': 'partial', 'item': 'unlinked:other'}}, AT), {})   # set by someone since: theirs

    def test_an_answer_by_choice_is_kept_as_single_and_has_no_anchor(self):
        got = self.check({'id': 'unlinked:spend_contract', 'choice': 'expected'})['unlinked:spend_contract']
        self.assertEqual((got['mode'], 'anchor' in got, 'reply' in got), ('single', False, False))


class ReturnTests(unittest.TestCase):
    ITEM = {'id': 'code_meaning:订单.状态码', 'kind': 'code_meaning', 'ask': '状态码是代码', 'facts': ['取值 0：96 行'],
            'anchor': {'noun': '取值', 'members': ['0', '1', '2'], 'counts': {'取值 0': 96, '取值 1': 48, '取值 2': 16}, 'total': 160}}
    DECIDED = {'reply': 'exception', 'says': '已知例外', 'by': '王工', 'at': '2026-11-13T09:00:00+00:00', 'text': '2 是测试单', 'mode': 'single', 'anchor': ITEM['anchor']}

    def listed(self, **over):
        return {**self.ITEM, **over, 'anchor': {**self.ITEM['anchor'], **over.get('anchor', {})}}

    def test_a_decision_stays_decided_while_the_item_is_what_it_was(self):
        open_, answered = split_answers([self.listed()], {self.ITEM['id']: self.DECIDED})
        self.assertEqual(([i['id'] for i in open_], [i['id'] for i in answered]), ([], [self.ITEM['id']]))
        self.assertEqual(answered[0]['answer']['says'], '已知例外')

    def test_a_share_that_stays_the_same_in_a_bigger_table_is_not_a_change(self):
        bigger = {'members': ['0', '1', '2'], 'counts': {'取值 0': 192, '取值 1': 96, '取值 2': 32}, 'total': 320}
        open_, _ = split_answers([self.listed(anchor=bigger)], {self.ITEM['id']: self.DECIDED})
        self.assertEqual(open_, [])

    def test_a_new_value_brings_it_back_with_the_old_decision_and_what_changed(self):
        new = {'members': ['0', '1', '2', '9'], 'counts': {'取值 0': 96, '取值 1': 48, '取值 2': 16, '取值 9': 6}, 'total': 166}
        [back], answered = split_answers([self.listed(anchor=new)], {self.ITEM['id']: self.DECIDED})
        self.assertEqual(answered, [])
        self.assertEqual((back['reopened']['says'], back['reopened']['by'], back['reopened']['text']), ('已知例外', '王工', '2 是测试单'))
        self.assertEqual(back['reopened']['changes'], ['多了取值：9'])

    def test_a_code_whose_rows_grew_to_more_than_twice_its_share_brings_it_back(self):
        moved = {'counts': {'取值 0': 96, '取值 1': 48, '取值 2': 80}, 'total': 224}
        [back], _ = split_answers([self.listed(anchor=moved)], {self.ITEM['id']: self.DECIDED})
        self.assertEqual(back['reopened']['changes'], ['取值 2：上次 16 行（共 160 行），现在 80 行（共 224 行）'])

    def test_an_answer_with_no_anchor_never_comes_back(self):
        old = {k: v for k, v in self.DECIDED.items() if k != 'anchor'}
        open_, _ = split_answers([self.listed(anchor={'members': ['0', '1', '2', '9']})], {self.ITEM['id']: old})
        self.assertEqual(open_, [])

    def test_an_item_with_no_anchor_of_its_own_is_held_to_its_facts(self):
        was = {'noun': '内容', 'members': ['A：1 行']}
        self.assertEqual(anchor_changes(was, {'noun': '内容', 'members': ['A：1 行', 'B：2 行']}), ['多了内容：B：2 行'])
        self.assertEqual(anchor_changes(was, was), [])


class StackRouteTests(unittest.TestCase):
    """The planted upload over HTTP: the repeated customer key is a card with the rows it is about; an exception on it is kept and
    survives the next upload."""
    ITEM = 'repeated_key:customer.客户'

    def setUp(self):
        from tests.test_workspace_store import PLANTED_DRAFT, DraftsModel, ServerDataChecksTests
        self.files, self.model = ServerDataChecksTests.files, DraftsModel(copy.deepcopy(PLANTED_DRAFT))

    def run_with(self, check):
        with OntologyServerTests().server(gateway=self.model) as (base, out):
            _, run = call(base, '/api/ontology/build', {'files': self.files})
            check(base, out, run['saved_as'])

    def listed(self, base, name):
        status, body = fetch(base, f'/api/ontology/runs/{name}/open-items')
        self.assertEqual(status, 200, body)
        return body

    def test_the_list_gives_each_card_its_replies_example_rows_and_check_result(self):
        def check(base, out, name):
            listed = self.listed(base, name)
            repeat = next(i for i in listed['items'] if i['id'] == self.ITEM)
            self.assertEqual([m['id'] for m in repeat['replies']], ['keep_both', 'keep_latest', 'data_error', 'exception'])
            self.assertEqual(repeat['examples']['table'], '客户')
            self.assertEqual([r[repeat['examples']['columns'].index('客户编号')] for r in repeat['examples']['rows']], ['KH012', 'KH012'])
            self.assertEqual(repeat['check'], {'status': 'failed', 'text': '编号唯一性没通过：1 个编号出现在不止一行，共 2 行'})
            code = next(i for i in listed['items'] if i['id'] == 'code_meaning:订单.状态码')
            self.assertEqual([m['id'] for m in code['replies']], ['confirm', 'not_applicable', 'exception'])
            self.assertEqual(code['examples']['table'], '订单')
            self.assertEqual([r[0] for r in code['examples']['rows']], ['0', '1', '2'])   # one stored row for each code, the code column first
        self.run_with(check)

    def test_an_exception_closes_the_card_is_kept_with_who_and_how_and_is_not_asked_again_on_the_next_upload(self):
        def check(base, out, name):
            status, body = call(base, '/api/ontology/card', {'saved_as': name, 'by': '王工', 'items': [{'id': self.ITEM, 'reply': 'exception', 'text': 'KH012 是同一个客户，两行不用管'}]})
            self.assertEqual(status, 200, body)
            self.assertNotIn(self.ITEM, {i['id'] for i in body['items']})
            [answered] = [i for i in body['answered'] if i['id'] == self.ITEM]
            self.assertEqual((answered['answer']['reply'], answered['answer']['says'], answered['answer']['by'], answered['answer']['mode']), ('exception', '已知例外', '王工', 'single'))
            self.assertEqual(answered['answer']['anchor']['members'], ['KH012'])
            self.assertEqual([m['id'] for m in answered['replies']], ['keep_both', 'keep_latest', 'data_error', 'exception'])   # a decision can be changed
            _, rerun = call(base, '/api/ontology/build', {'files': self.files})   # the same file again
            again = self.listed(base, rerun['saved_as'])
            self.assertNotIn(self.ITEM, {i['id'] for i in again['items']})
            self.assertIn(self.ITEM, {i['id'] for i in again['answered']})
        self.run_with(check)

    def test_what_was_decided_through_the_code_and_repeat_endpoints_counts_as_decided_and_says_how(self):
        def check(base, out, name):
            call(base, '/api/ontology/repeat-rules', {'saved_as': name, 'id': self.ITEM, 'rule': 'keep_both', 'confirmed_by': '王工', 'mode': 'bulk'})
            call(base, '/api/ontology/code-meanings', {'saved_as': name, 'id': 'code_meaning:订单.状态码', 'confirmed_by': '李工',
                                                       'values': [{'value': '0', 'label': '新建'}, {'value': '1', 'label': '已发货'}, {'value': '2', 'label': '已取消'}]})
            call(base, '/api/ontology/code-meanings/dismiss', {'saved_as': name, 'id': 'code_meaning:客户.客户等级', 'confirmed_by': '李工'})
            settled = {s['id']: s['answer'] for s in self.listed(base, name)['settled']}
            self.assertEqual(settled[self.ITEM]['says'], '每一行都留')
            self.assertEqual((settled[self.ITEM]['by'], settled[self.ITEM]['mode']), ('王工', 'bulk'))
            self.assertEqual((settled['code_meaning:订单.状态码']['says'], settled['code_meaning:订单.状态码']['text']), ('含义已确认', '0 = 新建、1 = 已发货、2 = 已取消'))
            self.assertEqual((settled['code_meaning:客户.客户等级']['says'], settled['code_meaning:客户.客户等级']['mode']), ('不是代码', 'single'))
        self.run_with(check)

    def test_taking_a_decision_back_puts_the_card_in_the_stack_again(self):
        def check(base, out, name):
            call(base, '/api/ontology/card', {'saved_as': name, 'by': '王工', 'items': [{'id': self.ITEM, 'reply': 'exception', 'text': '同一个客户'}]})
            status, body = call(base, '/api/ontology/card', {'saved_as': name, 'by': '王工', 'items': [{'id': self.ITEM, 'reply': 'reopen'}]})
            self.assertEqual(status, 200, body)
            self.assertIn(self.ITEM, {i['id'] for i in body['items']})
            self.assertNotIn(self.ITEM, {i['id'] for i in body['answered']})
        self.run_with(check)

    def test_a_key_that_repeats_for_the_first_time_after_an_exception_asks_again(self):
        def check(base, out, name):
            call(base, '/api/ontology/card', {'saved_as': name, 'by': '王工', 'items': [{'id': self.ITEM, 'reply': 'exception', 'text': '同一个客户'}]})
            from tests.test_workspace_store import planted_bundle
            records = planted_bundle()['sources']['客户']['records']
            lines = [','.join(records[0]), *(','.join(r[c] or '' for c in records[0]) for r in records), ','.join(records[2][c] if c != '城市' else '成都' for c in records[0])]   # KH003 again, in another city
            files = [f for f in self.files if not f['filename'].startswith('客户')]
            files.append({'filename': '客户.csv', 'content_base64': base64.b64encode('\n'.join(lines).encode('utf-8')).decode()})
            _, rerun = call(base, '/api/ontology/build', {'files': files, 'previous': name})   # said to be the next version of the first
            [again] = [i for i in self.listed(base, rerun['saved_as'])['items'] if i['id'] == self.ITEM]
            self.assertEqual(again['reopened']['says'], '已知例外')
            self.assertEqual(again['reopened']['text'], '同一个客户')
            self.assertEqual(again['reopened']['changes'], ['多了重复的编号：KH003'])
        self.run_with(check)

    def test_the_repeat_rule_and_the_code_meaning_remember_how_they_were_decided(self):
        def check(base, out, name):
            call(base, '/api/ontology/repeat-rules', {'saved_as': name, 'id': self.ITEM, 'rule': 'keep_both', 'confirmed_by': '王工', 'mode': 'bulk'})
            status, body = call(base, '/api/ontology/code-meanings', {'saved_as': name, 'id': 'code_meaning:订单.状态码', 'confirmed_by': '王工',
                                                                      'values': [{'value': '2', 'label': '已取消'}]})
            self.assertEqual(status, 200, body)
            from ontology_poc_generator.workspace_store import open_workspace
            conn = open_workspace(out / 'workspace.sqlite')
            try:
                modes = dict(conn.execute("SELECT substr(element_id, 1, instr(element_id, ':') - 1), json_extract(content_json, '$.mode') FROM element_state WHERE state = 'confirmed'").fetchall())
            finally:
                conn.close()
            self.assertEqual(modes, {'repeat_rule': 'bulk', 'property': 'single'})
            status, body = call(base, '/api/ontology/repeat-rules', {'saved_as': name, 'id': self.ITEM, 'rule': 'keep_both', 'mode': 'sometimes'})
            self.assertEqual(status, 400)
        self.run_with(check)


if __name__ == '__main__':
    unittest.main()
