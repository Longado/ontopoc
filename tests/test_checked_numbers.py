"""Numbers the team has checked (核对过的数), walked through the real service: a builder records, for a board card or for one of their own saved answers, the number
the team trusts and where it came from; from then on code works the card or the answer out again (no model) each time it is shown, and says whether it still
matches (一致), moved since the check (变了: from → to, and which data or definition versions moved), now refuses (拒答, with the plain reason), or differs from the
trusted value as it did at the check (不一致). The trusted value is never changed by anything but a new check. A viewer sees on a board only the mark and who checked
it when; nobody sees another person's question."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.test_dashboards import CARD, BoardCase
from tests.test_explorer import LIVE, ORDERS
from tests.test_object_types import ORDER, TABLES, VALID, orders_upload, shifted_orders_csv
from tests.test_two_person import SigningTestCase
from tests.test_workspace_questions import ALL_ORDERS, AskModel, CANCELLED, QUESTION, cancelled

CANCELLED_CARD = {'id': 'cancelled', 'title': '取消的订单', 'text': "SELECT count(o) FROM (o:订单) WHERE o.状态码 = '已取消'", 'chart': {'kind': 'query'}}
BAR = {'id': 'status', 'title': '按状态', 'query': {'type': 'order'}, 'chart': {'kind': 'bar', 'group': '状态码', 'fn': 'count'}}
AMOUNT = {'id': 'valid_amount', 'title': '有效订单金额', 'query': {'type': 'order', 'view': '有效订单'}, 'chart': {'kind': 'number', 'measure': '金额', 'fn': 'sum'}}
SPEC = {'components': [CARD, AMOUNT, CANCELLED_CARD, BAR], 'filters': [{'field': '状态码', 'label': '状态'}]}
FIRST_LIVE = next(i for i, r in enumerate(ORDERS) if r['状态码'] == '0')   # one delivered order that a new version changes
LIVE_AMOUNT = sum(float(r['金额']) for r in LIVE)


def one_more_cancelled(record, i):
    return {**record, '状态码': '2'} if i == FIRST_LIVE else record


def hundred_more(record, i):
    """The same orders, one delivered order 100 more: no code and no row a view keeps moves, the amount does."""
    return {**record, '金额': str(int(float(record['金额'])) + 100)} if i == FIRST_LIVE else record


class CheckedBoardCase(BoardCase):
    def board(self, team):
        self.world(team)
        status, body = team['ann'].post('/api/workspace/dashboards', {'name': '订单看板', 'spec': SPEC, 'scope': 'everyone'})
        self.assertEqual(status, 200, body)
        return body['id']

    def check(self, client, board, component, expect=200, **more):
        status, body = client.post('/api/workspace/checked', {'board': board, 'component': component, 'note': '财务 10 月报表', **more})
        self.assertEqual(status, expect, body)
        return body

    def checks(self, client, board):
        body = self.data(client, board)
        return {c['id']: c.get('check') for c in body['components']}, body['headline'].get('checked')


class RecordAndRecomputeTests(CheckedBoardCase):
    def test_a_checked_card_matches_until_a_new_data_version_moves_it_and_then_says_from_what_to_what_and_which_version_moved(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            bob = team['bob']
            made = self.check(bob, board, 'valid')   # the trusted value defaults to the number shown
            self.assertEqual((made['status'], made['trusted'], made['then'], made['now'], made['note'], made['by']), ('same', len(LIVE), len(LIVE), len(LIVE), '财务 10 月报表', 'Bob'))
            self.assertEqual(self.check(bob, board, 'valid_amount')['status'], 'same')
            self.assertEqual(self.check(bob, board, 'cancelled')['status'], 'same')
            checks, summary = self.checks(bob, board)
            self.assertEqual((checks['valid']['status'], checks['valid_amount']['status'], checks['cancelled']['status'], checks['status']), ('same', 'same', 'same', None))
            self.assertEqual((summary['total'], summary['same'], summary['moved'], summary['refused'], summary['differs']), (3, 3, 0, 0, 0))
            self.assertEqual(summary['text'], '3 个数核对过：3 一致、0 变了、0 拒答、0 不一致')
            # a new version of 订单 in which one delivered order is 100 more: the definitions stay confirmed, the amount moves and the counts do not
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [orders_upload(hundred_more)]})[0], 200)
            checks, summary = self.checks(bob, board)
            amount = checks['valid_amount']
            self.assertEqual((amount['status'], amount['trusted'], amount['then'], amount['now']), ('moved', LIVE_AMOUNT, LIVE_AMOUNT, LIVE_AMOUNT + 100))
            self.assertEqual(amount['moved'], [{'kind': 'dataset', 'name': '订单', 'from': 1, 'to': 2}])
            self.assertEqual((checks['valid']['status'], checks['cancelled']['status']), ('same', 'same'))
            self.assertEqual(summary['text'], '3 个数核对过：2 一致、1 变了、0 拒答、0 不一致')
            # nothing changed what the team trusts: a new check does, and is kept apart from the first
            again = self.check(bob, board, 'valid_amount', note='重新对过')
            self.assertEqual((again['status'], again['trusted'], again['note']), ('same', LIVE_AMOUNT + 100, '重新对过'))
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(conn.execute("SELECT trusted FROM checked_number WHERE component_id = 'valid_amount' ORDER BY id").fetchall(), [(LIVE_AMOUNT,), (LIVE_AMOUNT + 100,)])
            conn.close()
            # one delivered order cancelled: the view keeps other rows now and needs another look, so what stands on it refuses; the plain count moves by one
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [orders_upload(one_more_cancelled)]})[0], 200)
            checks, summary = self.checks(bob, board)
            self.assertEqual((checks['valid']['status'], checks['valid']['now']), ('refused', None))
            self.assertIn('有效订单', checks['valid']['reason'])
            self.assertEqual((checks['cancelled']['status'], checks['cancelled']['then'], checks['cancelled']['now']), ('moved', CANCELLED, CANCELLED + 1))
            self.assertEqual(summary['text'], '3 个数核对过：0 一致、1 变了、2 拒答、0 不一致')

    def test_a_trusted_value_that_differs_from_the_number_shown_is_kept_and_shown_as_differing_from_the_start(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            made = self.check(team['bob'], board, 'valid_amount', value='1,234')
            self.assertEqual((made['status'], made['trusted'], made['then']), ('differs', 1234, LIVE_AMOUNT))
            checks, summary = self.checks(team['ann'], board)
            self.assertEqual((checks['valid_amount']['status'], checks['valid_amount']['now']), ('differs', LIVE_AMOUNT))
            self.assertEqual(summary['text'], '1 个数核对过：0 一致、0 变了、0 拒答、1 不一致')
            # when the data moves the number again, it is a change since the check, still never the trusted value
            team['ann'].post('/api/workspace/datasets/upload', {'files': [orders_upload(hundred_more)]})
            check = self.checks(team['ann'], board)[0]['valid_amount']
            self.assertEqual((check['status'], check['trusted']), ('moved', 1234))

    def test_when_a_definition_under_a_checked_number_needs_another_look_the_check_says_it_refuses_and_why(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            bob = team['bob']
            self.check(bob, board, 'valid')
            self.check(bob, board, 'cancelled')
            self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)   # every code one higher: the meanings need another look
            checks, summary = self.checks(bob, board)
            self.assertEqual((checks['valid']['status'], checks['valid']['now']), ('refused', None))
            self.assertIn('状态码', checks['valid']['reason'])
            self.assertEqual(checks['cancelled'], {'status': 'refused', 'by': 'Bob', 'at': checks['cancelled']['at']})   # the query card no longer reads for Bob (not its author): he is told it refuses, not what it read
            self.assertEqual(summary['text'], '2 个数核对过：0 一致、0 变了、2 拒答、0 不一致')

    def test_what_cannot_be_checked_is_refused_in_words(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            bob, vera = team['bob'], team['vera']
            self.assertIn('一个数', self.check(bob, board, 'status', expect=400)['error'])   # a bar chart is not one number
            self.assertIn('来源', self.check(bob, board, 'valid', expect=400, note=' ')['error'])
            self.assertIn('数字', self.check(bob, board, 'valid', expect=400, value='很多')['error'])
            self.assertEqual(self.check(bob, board, 'nothing', expect=404)['error'], '看板上没有这个组件')
            self.check(vera, board, 'valid', expect=403)   # a viewer reads the mark, records none
            draft = team['ann'].post('/api/workspace/dashboards', {'name': '草稿', 'spec': SPEC})[1]
            self.assertEqual(self.check(bob, draft['id'], 'valid', expect=404)['error'], '没有这个看板')   # a board Bob may not open
            team['ann'].post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})
            self.assertIn('不是按已确认的定义', self.check(bob, board, 'valid', expect=400)['error'])   # a number that does not stand on confirmed definitions is no yardstick

    def test_a_card_changed_after_its_check_no_longer_carries_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            ann = team['ann']
            self.check(team['bob'], board, 'valid')
            shown = ann.get(f'/api/workspace/dashboards/{board}')[1]
            spec = {**SPEC, 'components': [{**CARD, 'query': {'type': 'order'}}, AMOUNT, CANCELLED_CARD, BAR]}
            self.assertEqual(ann.post('/api/workspace/dashboards/update', {'id': board, 'name': '订单看板', 'spec': spec, 'version': shown['version'], 'scope': 'everyone'})[0], 200)
            checks, summary = self.checks(ann, board)
            self.assertIsNone(checks['valid'])
            self.assertEqual(summary['total'], 0)


class WhoSeesWhatTests(CheckedBoardCase):
    def test_a_viewer_sees_only_the_mark_and_who_checked_it_when_and_a_builder_sees_the_value_and_the_source(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            self.check(team['bob'], board, 'valid', value=999, note='SQL by 小王')
            vera = self.data(team['vera'], board)
            check = next(c for c in vera['components'] if c['id'] == 'valid')['check']
            self.assertEqual(set(check), {'status', 'by', 'at'})
            self.assertEqual((check['status'], check['by']), ('differs', 'Bob'))
            self.assertNotIn('SQL by 小王', json.dumps(vera, ensure_ascii=False))
            self.assertNotIn('999', json.dumps(check))
            self.assertEqual(vera['headline']['checked']['text'], '1 个数核对过：0 一致、0 变了、0 拒答、1 不一致')
            ann = next(c for c in self.data(team['ann'], board)['components'] if c['id'] == 'valid')['check']
            self.assertEqual((ann['note'], ann['trusted']), ('SQL by 小王', 999))

    def test_a_builder_kept_from_the_cards_column_or_type_gets_only_the_mark_and_never_the_team_number_its_source_or_what_was_computed(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            admin, bob = team['admin'], team['bob']
            self.check(team['ann'], board, 'valid_amount', value=999, note='SECRET-SRC')
            ann_id = self.ids(admin)['ann']
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [ann_id]})[0], 200)
            body = self.data(bob, board)
            check = next(c for c in body['components'] if c['id'] == 'valid_amount')['check']
            self.assertEqual(set(check), {'status', 'by', 'at'})
            self.assertNotIn('SECRET-SRC', json.dumps(body, ensure_ascii=False))
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': []})[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [ann_id]})[0], 200)
            status, body = bob.post('/api/workspace/dashboards/data', {'id': board})
            if status == 200:   # the board may still open on what Bob may read; what was checked on the closed card is not his to read
                for c in body['components']:
                    self.assertTrue(c.get('check') is None or set(c['check']) == {'status', 'by', 'at'}, c)
                self.assertNotIn('SECRET-SRC', json.dumps(body, ensure_ascii=False))

    def test_a_board_read_with_a_filter_or_a_typed_parameter_does_not_hold_its_numbers_against_the_checks(self):
        with self.service() as (base, out):
            team = self.team(base)
            board = self.board(team)
            self.check(team['bob'], board, 'valid')
            body = self.data(team['bob'], board, bar={'状态码': '0'})
            self.assertIsNone(next(c for c in body['components'] if c['id'] == 'valid').get('check'))
            self.assertEqual(body['headline']['checked']['total'], 0)
            self.assertIn('筛选', body['headline']['checked']['text'])


class ParameterTests(CheckedBoardCase):
    def test_a_check_on_a_query_card_holds_only_for_the_parameter_values_it_was_checked_with(self):
        def mine(kh):
            return sum(r['客户编号'] == kh for r in ORDERS)
        who = {'id': 'who', 'title': '客户订单数', 'text': 'SELECT count(o) FROM (o:订单) WHERE o.客户编号 = $who', 'chart': {'kind': 'query'}}
        others = sorted({r['客户编号'] for r in ORDERS} - {'KH001'})
        twin = next((kh for kh in others if mine(kh) == mine('KH001')), None)   # a customer with as many orders: the number alone cannot tell them apart
        apart = next(kh for kh in others if mine(kh) != mine('KH001'))
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']

            def board_with(default, board=None):
                body = {'name': '客户看板', 'spec': {'components': [who], 'filters': [], 'params': [{'name': 'who', 'label': '客户', 'default': default}]}, 'scope': 'everyone'}
                if board is None:
                    return ann.post('/api/workspace/dashboards', body)[1]['id']
                version = ann.get(f'/api/workspace/dashboards/{board}')[1]['version']
                self.assertEqual(ann.post('/api/workspace/dashboards/update', {**body, 'id': board, 'version': version})[0], 200)
                return board
            board = board_with('KH001')
            made = self.check(bob, board, 'who')
            self.assertEqual((made['status'], made['trusted']), ('same', mine('KH001')))
            for other in [kh for kh in (twin, apart) if kh]:
                board_with(other, board)
                checks, summary = self.checks(bob, board)
                self.assertIsNone(checks['who'], other)   # checked for KH001: no mark at all for another customer, never "same" or "moved"
                self.assertEqual(summary['total'], 0)
            board_with('KH001', board)
            self.assertEqual(self.checks(bob, board)[0]['who']['status'], 'same')


class AnswerCheckTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def confirmed_orders(self, team):
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
        for column in ('状态码', None):
            shown = bob.get('/api/workspace/types/order')[1]
            shown = next(p for p in shown['properties'] if p['column'] == column)['meanings'] if column else shown
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})[0], 200)

    def test_an_asker_checks_their_own_saved_number_and_the_tally_counts_it_without_the_question(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            ann, bob = team['ann'], team['bob']
            asked = ann.post('/api/workspace/ask', {'question': QUESTION})[1]
            self.assertEqual(asked['answer']['total'], CANCELLED)
            status, made = ann.post('/api/workspace/checked', {'question': asked['id'], 'note': '运营周报'})
            self.assertEqual(status, 200, made)
            self.assertEqual((made['status'], made['trusted'], made['now']), ('same', CANCELLED, CANCELLED))
            self.assertEqual(ann.get(f'/api/workspace/checked/question/{asked["id"]}')[1]['check']['status'], 'same')
            # nobody else records on it or reads it
            self.assertEqual(bob.post('/api/workspace/checked', {'question': asked['id'], 'note': 'x'})[0], 404)
            self.assertEqual(bob.get(f'/api/workspace/checked/question/{asked["id"]}')[0], 404)
            self.assertEqual(team['vera'].get(f'/api/workspace/checked/question/{asked["id"]}')[0], 403)
            tally = bob.get('/api/workspace/ask/tally')[1]
            self.assertEqual({k: tally['checked'][k] for k in ('total', 'same', 'moved', 'refused', 'differs')}, {'total': 1, 'same': 1, 'moved': 0, 'refused': 0, 'differs': 0})
            self.assertNotIn(QUESTION, json.dumps(tally, ensure_ascii=False))
            self.assertNotIn('运营周报', json.dumps(tally, ensure_ascii=False))
            # the data moves: the answer is worked out again by code as Ann, never by the model
            calls = len(model.requests)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(one_more_cancelled)]})[0], 200)
            moved = ann.get(f'/api/workspace/checked/question/{asked["id"]}')[1]['check']
            self.assertEqual((moved['status'], moved['then'], moved['now']), ('moved', CANCELLED, CANCELLED + 1))
            self.assertEqual(bob.get('/api/workspace/ask/tally')[1]['checked']['moved'], 1)
            # the codes shift: the answer's meaning needs another look, so the check refuses
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            refused = ann.get(f'/api/workspace/checked/question/{asked["id"]}')[1]['check']
            self.assertEqual((refused['status'], refused['now']), ('refused', None))
            self.assertIn('状态码', refused['reason'])
            self.assertEqual(bob.get('/api/workspace/ask/tally')[1]['checked']['refused'], 1)
            self.assertEqual(len(model.requests), calls)   # all of it worked out by code

    def test_a_checked_answer_whose_view_left_the_askers_scope_refuses_and_is_never_worked_out_over_more_rows(self):
        model = AskModel({'reasoning': '有效订单', 'query': ALL_ORDERS, 'definitions_used': [{'id': '有效订单', 'direction': 'include', 'basis': '有效订单'}]})
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            ann, bob = team['ann'], team['bob']
            self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
            shown = bob.get('/api/workspace/types/order/views')[1]['views'][0]
            self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': VALID['name'], 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            asked = ann.post('/api/workspace/ask', {'question': '有效订单有多少？'})[1]
            self.assertEqual(asked['answer']['total'], len(LIVE))
            self.assertEqual(ann.post('/api/workspace/checked', {'question': asked['id'], 'note': '运营周报'})[1]['status'], 'same')
            self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': '状态码', 'hide_values': True})[0], 200)   # the view's column: its values go to no model, so the view leaves the scope
            check = ann.get(f'/api/workspace/checked/question/{asked["id"]}')[1]['check']
            self.assertEqual((check['status'], check['now']), ('refused', None))
            self.assertIn('有效订单', check['reason'])

    def test_a_checked_answer_whose_asker_a_row_rule_limits_since_refuses_like_the_answer_itself(self):
        model = AskModel(cancelled())
        with self.service(gateway=model) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            ann, admin = team['ann'], team['admin']
            asked = ann.post('/api/workspace/ask', {'question': QUESTION})[1]
            self.assertEqual(ann.post('/api/workspace/checked', {'question': asked['id'], 'note': '运营周报'})[1]['status'], 'same')
            ann_id = next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == 'ann')
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': [{'column': '订单号', 'value': next(r['订单号'] for r in ORDERS if r['状态码'] == '2'), 'user_ids': [ann_id]}]})[0], 200)
            self.assertIn('withheld', ann.get(f'/api/workspace/ask/{asked["id"]}')[1])   # the answer itself is no longer shown to her
            check = ann.get(f'/api/workspace/checked/question/{asked["id"]}')[1]['check']
            self.assertEqual((check['status'], check['now']), ('refused', None))
            self.assertIn('行规则', check['reason'])
            tally = team['bob'].get('/api/workspace/ask/tally')[1]['checked']
            self.assertEqual((tally['refused'], tally['moved']), (1, 0))

    def test_the_tally_works_out_again_only_the_latest_checked_answers_and_says_how_many_it_left(self):
        from unittest import mock
        from ontology_poc_generator import checked_numbers
        with self.service(gateway=AskModel(cancelled())) as (base, out), mock.patch.object(checked_numbers, 'TALLY_WORKED_OUT', 1):
            team = self.team(base)
            self.confirmed_orders(team)
            ann = team['ann']
            first = ann.post('/api/workspace/ask', {'question': QUESTION})[1]
            second = ann.post('/api/workspace/ask', {'question': '已取消的订单数？'})[1]
            self.assertEqual(ann.post('/api/workspace/checked', {'question': first['id'], 'note': '周报'})[1]['status'], 'same')
            self.assertEqual(ann.post('/api/workspace/checked', {'question': second['id'], 'value': 999, 'note': '周报'})[1]['status'], 'differs')
            checked = team['bob'].get('/api/workspace/ask/tally')[1]['checked']
            self.assertEqual((checked['total'], checked['all'], checked['same'], checked['differs']), (1, 2, 0, 1))   # the latest check only
            self.assertIn('只重算了最近核对的 1 个（共 2 个）', checked['text'])

    def test_a_viewer_cannot_record_a_checked_number(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.confirmed_orders(team)
            asked = team['vera'].post('/api/workspace/ask', {'question': QUESTION})[1]
            self.assertEqual(team['vera'].post('/api/workspace/checked', {'question': asked['id'], 'note': 'x'})[0], 403)


class StoreTests(unittest.TestCase):
    def test_a_workspace_file_made_before_checked_numbers_existed_gets_the_table_when_it_is_opened(self):
        from ontology_poc_generator.workspace_store import open_workspace
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'workspace.sqlite'
            open_workspace(path).close()
            conn = sqlite3.connect(path)
            conn.execute('DROP TABLE checked_number')
            conn.commit()
            conn.close()
            conn = open_workspace(path)
            self.assertIn('trusted', {r[1] for r in conn.execute('PRAGMA table_info(checked_number)')})
            conn.close()


if __name__ == '__main__':
    unittest.main()
