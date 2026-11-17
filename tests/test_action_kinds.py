"""R12a: an action can create an object or delete one, not only edit it, and its submit conditions can be several, each with an operator.

DIP showed what to avoid (walk of 2026-11-16): its create stored a bad value as null and said 处理成功, and a key that already existed overwrote that row while the
page said 更新出错; its delete took no reason, was not logged, and could not be undone. Here:
- create: a value that does not fit is refused and says which property; a key that exists is refused and nothing is written; a key taken between the submit and the
  approval sends the request to needs_look, and the row that is there is left alone. Undoing an approved create is a request to delete that object.
- delete: a reason is required; at approval the object must still hold what it held at the submit (else needs_look, nothing removed); the whole row is kept on the
  record, so undoing it is a request that puts the same row back. A delete reads every column of the row, so a person kept from one of them is not shown the action.
- conditions: up to MAX_CONDITIONS, all of which must hold: =, ≠, >, ≥, <, ≤ (numbers and dates), empty, not empty, one of. The old single `condition` still reads.
- who may submit: an action can name the people who may submit it; anyone else is refused (and logged)."""
import json
import unittest
from urllib.parse import quote

from ontology_poc_generator.workspace_store import current_dataset, dataset_records
from tests.test_object_types import ACTION_URL, ORDERS, STATUS_ACTION, ActionTests

NEW_ORDER = {'name': '新建订单', 'type': 'order', 'kind': 'create', 'properties': ['金额', '状态码', '客户编号'], 'description': '电话下的单补录进来'}
DROP_ORDER = {'name': '删除取消的订单', 'type': 'order', 'kind': 'delete', 'properties': [], 'conditions': [{'column': '状态码', 'op': 'eq', 'value': '2'}],
              'description': '已取消的订单清掉'}
SET_AMOUNT = {'name': '改金额', 'type': 'order', 'properties': ['金额'], 'description': '补差价',
              'conditions': [{'column': '状态码', 'op': 'eq', 'value': '1'}, {'column': '金额', 'op': 'gt', 'value': '3000'},
                             {'column': '客户编号', 'op': 'in', 'value': ['KH001', 'KH002']}]}
CANCELLED = next(r for r in ORDERS if r['状态码'] == '2')
FRESH_KEY = 'DD29990001'


def load_tests(loader, standard, pattern):
    return unittest.TestSuite(KindTests(name) for name in vars(KindTests) if name.startswith('test_'))


def url(name):
    return '/api/workspace/actions/' + quote(name)


class KindTests(ActionTests):
    def rows(self, out):
        conn = self.db(out)
        try:
            dataset = current_dataset(conn, '订单')
            return dataset['version'], {r['订单号']: r for r in dataset_records(conn, dataset)}
        finally:
            conn.close()

    def create(self, client, key=FRESH_KEY, **params):
        values = {'金额': '1200', '状态码': '1', '客户编号': 'KH001', **params}
        return client.post('/api/workspace/actions/submit', {'action': NEW_ORDER['name'], 'key': {'订单号': key}, 'params': values, 'reason': '电话下单'})

    def drop(self, client, order=CANCELLED, reason='客户撤单，清掉'):
        return client.post('/api/workspace/actions/submit', {'action': DROP_ORDER['name'], 'key': {'订单号': order['订单号']}, 'params': {}, **({'reason': reason} if reason is not None else {})})

    # --- create -----------------------------------------------------------------------------------------------------------------------------------------------

    def test_a_create_action_adds_the_object_only_after_another_builder_approves(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team, NEW_ORDER)
            shown = ann.get(url(NEW_ORDER['name']))[1]
            self.assertEqual(shown['kind'], 'create')
            self.assertEqual(shown['says'], '新建 订单，要填「订单号」「金额」「状态码」「客户编号」')
            self.assertEqual([p['column'] for p in shown['parameters']], ['订单号', '金额', '状态码', '客户编号'])
            self.assertTrue(shown['parameters'][0]['key'])
            status, body = self.create(ann)
            self.assertEqual(status, 200, body)
            self.assertEqual(self.rows(out)[0], 1)   # nothing written before the approval
            record = next(r for r in ann.get(url(NEW_ORDER['name']))[1]['records'] if r['id'] == body['record'])
            self.assertEqual((record['kind'], record['object']), ('create', f'订单 {FRESH_KEY}'))
            self.assertEqual(record['change_text'], '新建：金额 1200，状态码 生产中，客户编号 KH001')
            card = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'approval' and i['record'] == body['record'])
            self.assertIn(f'想新建 订单 {FRESH_KEY}', card['lines'][0]['text'])
            status, decided = bob.post('/api/workspace/actions/decide', {'id': body['record'], 'decision': 'approve'})
            self.assertEqual((status, decided['state'], decided['version']), (200, 'approved', 2), decided)
            version, rows = self.rows(out)
            self.assertEqual(len(rows), len(ORDERS) + 1)
            self.assertEqual({c: rows[FRESH_KEY][c] for c in ('金额', '状态码', '客户编号')}, {'金额': 1200, '状态码': 1, '客户编号': 'KH001'})
            log = ann.get(url(NEW_ORDER['name']))[1]['log']
            self.assertTrue(any(e['change'] == 'action_approved' and FRESH_KEY in e['text'] for e in log))

    def test_a_create_refuses_a_value_that_does_not_fit_and_never_overwrites_an_object_that_is_there(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team, NEW_ORDER)
            for params, said in (({'金额': 'abc'}, '金额'), ({'状态码': '9'}, '状态码'), ({'金额': ''}, '金额')):
                status, body = self.create(ann, **params)
                self.assertEqual(status, 400, body)
                self.assertIn(said, body['error'])
            status, body = self.create(ann, key='')
            self.assertEqual(status, 400, body)
            taken = ORDERS[0]['订单号']
            status, body = self.create(ann, key=taken)
            self.assertEqual(status, 409, body)
            self.assertIn(f'已经有 订单 {taken}', body['error'])
            self.assertEqual(self.rows(out)[0], 1)
            # two requests for one new key: the first approved stands, the second is not written over it
            first, second = self.create(ann)[1]['record'], self.create(ann, 金额='999')[1]['record']
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': first, 'decision': 'approve'})[1]['state'], 'approved')
            status, body = bob.post('/api/workspace/actions/decide', {'id': second, 'decision': 'approve'})
            self.assertEqual((status, body['state']), (200, 'needs_look'), body)
            self.assertIn('已经有了', body['why'])
            version, rows = self.rows(out)
            self.assertEqual((version, rows[FRESH_KEY]['金额']), (2, 1200))
            refused = [e for e in ann.get(url(NEW_ORDER['name']))[1]['log'] if e['change'] == 'action_refused']
            self.assertGreaterEqual(len(refused), 4)   # every refused submit is on the log

    def test_a_create_cannot_carry_conditions_and_a_delete_writes_no_property(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            for payload, said in (({**NEW_ORDER, 'conditions': [{'column': '状态码', 'op': 'eq', 'value': '1'}]}, '新建'),
                                  ({**DROP_ORDER, 'properties': ['金额']}, '删除'), ({**NEW_ORDER, 'kind': 'move'}, 'kind')):
                status, body = ann.post('/api/workspace/actions', payload)
                self.assertEqual(status, 400, payload)
                self.assertIn(said, body['error'])

    def test_an_approved_create_is_undone_by_a_request_to_delete_that_object(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team, NEW_ORDER)
            record = self.create(ann)[1]['record']
            bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})
            status, body = ann.post('/api/workspace/actions/undo', {'id': record, 'reason': '重复录入'})
            self.assertEqual((status, body['undo_of']), (200, record), body)
            undo = next(r for r in ann.get(url(NEW_ORDER['name']))[1]['records'] if r['id'] == body['record'])
            self.assertEqual(undo['kind'], 'delete')
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': body['record'], 'decision': 'approve'})[1]['state'], 'approved')
            version, rows = self.rows(out)
            self.assertEqual((version, len(rows), FRESH_KEY in rows), (3, len(ORDERS), False))

    # --- delete -----------------------------------------------------------------------------------------------------------------------------------------------

    def test_a_delete_needs_a_reason_and_its_condition_and_removes_the_object_after_approval_and_an_undo_puts_the_same_row_back(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team, DROP_ORDER)
            shown = ann.get(url(DROP_ORDER['name']))[1]
            self.assertEqual((shown['kind'], shown['parameters']), ('delete', []))
            self.assertEqual(shown['says'], '删除 订单；只在 状态码 是「已取消」时可以提交')
            status, body = self.drop(ann, reason=None)
            self.assertEqual(status, 400, body)
            self.assertIn('理由', body['error'])
            live = next(r for r in ORDERS if r['状态码'] == '1')
            status, body = self.drop(ann, order=live)
            self.assertEqual(status, 409, body)
            self.assertIn('条件不满足', body['error'])
            _, before = self.rows(out)
            status, body = self.drop(ann)
            self.assertEqual(status, 200, body)
            record = next(r for r in ann.get(url(DROP_ORDER['name']))[1]['records'] if r['id'] == body['record'])
            self.assertEqual(record['kind'], 'delete')
            self.assertIn('删除', record['change_text'])
            self.assertIn('已取消', record['change_text'])   # what is removed, as a person reads it
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': body['record'], 'decision': 'approve'})[1]['state'], 'approved')
            version, rows = self.rows(out)
            self.assertEqual((version, len(rows), CANCELLED['订单号'] in rows), (2, len(ORDERS) - 1, False))
            status, undo = ann.post('/api/workspace/actions/undo', {'id': body['record']})
            self.assertEqual(status, 200, undo)
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': undo['record'], 'decision': 'approve'})[1]['state'], 'approved')
            version, rows = self.rows(out)
            self.assertEqual(version, 3)
            self.assertEqual(rows[CANCELLED['订单号']], before[CANCELLED['订单号']])   # every column back, not only the type's properties

    def test_a_delete_of_an_object_changed_since_the_submit_is_not_written(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_action(team, DROP_ORDER)
            record = self.drop(ann)[1]['record']
            from tests.test_object_types import orders_upload
            moved = lambda r, i: {**r, '金额': '1'} if r['订单号'] == CANCELLED['订单号'] else r
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [orders_upload(moved)]})[0], 200)
            status, body = bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})
            self.assertEqual((status, body['state']), (200, 'needs_look'), body)
            self.assertIn(CANCELLED['订单号'], self.rows(out)[1])

    def test_a_delete_action_is_not_shown_to_a_person_kept_from_a_column_of_the_row(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.confirmed_action(team, DROP_ORDER)
            status, body = admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': [self.user_id(admin, 'ann')]})
            self.assertEqual(status, 200, body)
            self.assertNotIn(DROP_ORDER['name'], [a['name'] for a in bob.get('/api/workspace/actions?type=order')[1]['actions']])
            self.assertEqual(bob.get(url(DROP_ORDER['name']))[0], 404)
            self.assertEqual(self.drop(bob)[0], 404)

    # --- conditions and who may submit --------------------------------------------------------------------------------------------------------------------

    def test_several_conditions_with_operators_must_all_hold(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.confirmed_action(team, SET_AMOUNT)
            shown = ann.get(url(SET_AMOUNT['name']))[1]
            self.assertEqual(shown['says'], '改 订单 的「金额」；只在 状态码 是「生产中」、金额 大于 3000、客户编号 是 KH001、KH002 之一 时可以提交')
            self.assertEqual([c['op'] for c in shown['conditions']], ['eq', 'gt', 'in'])
            fits = lambda r: r['状态码'] == '1' and float(r['金额']) > 3000 and r['客户编号'] in ('KH001', 'KH002')
            good = next(r for r in ORDERS if fits(r))
            small = next(r for r in ORDERS if r['状态码'] == '1' and float(r['金额']) <= 3000 and r['客户编号'] in ('KH001', 'KH002'))
            other = next(r for r in ORDERS if r['状态码'] == '1' and float(r['金额']) > 3000 and r['客户编号'] not in ('KH001', 'KH002'))
            send = lambda r: ann.post('/api/workspace/actions/submit', {'action': SET_AMOUNT['name'], 'key': {'订单号': r['订单号']}, 'params': {'金额': '5'}, 'reason': '补差价'})
            for row, said in ((small, '金额'), (other, '客户编号')):
                status, body = send(row)
                self.assertEqual(status, 409, body)
                self.assertIn(said, body['error'])
            self.assertEqual(send(good)[0], 200)

    def test_a_condition_is_checked_when_the_action_is_defined(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            for conditions, said in (([{'column': '状态码', 'op': 'like', 'value': '1'}], '比较'),
                                     ([{'column': '客户编号', 'op': 'gt', 'value': 'KH001'}], '数字或日期'),
                                     ([{'column': '金额', 'op': 'gt', 'value': 'abc'}], '数字'),
                                     ([{'column': '金额', 'op': 'in', 'value': []}], '之一'),
                                     ([{'column': '状态码', 'op': 'eq', 'value': '7'}], '含义'),
                                     ([{'column': '金额', 'op': 'empty', 'value': '1'}], '不写取值'),
                                     ([{'column': '金额', 'op': 'not_empty'}] * 6, '最多')):
                status, body = ann.post('/api/workspace/actions', {**SET_AMOUNT, 'conditions': conditions})
                self.assertEqual(status, 400, conditions)
                self.assertIn(said, body['error'], conditions)
            status, body = ann.post('/api/workspace/actions', {**SET_AMOUNT, 'conditions': [{'column': '金额', 'op': 'not_empty'}, {'column': '客户编号', 'op': 'ne', 'value': 'KH099'}]})
            self.assertEqual(status, 200, body)

    def test_the_old_single_condition_still_reads_as_one_equal_condition(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            self.confirmed_action(team)   # STATUS_ACTION is written with `condition`
            shown = ann.get(ACTION_URL)[1]
            self.assertEqual(shown['conditions'], [{'column': '状态码', 'op': 'eq', 'value': '1', 'name': '状态码', 'label': '生产中'}])
            self.assertEqual(shown['kind'], 'edit')

    def test_an_action_can_name_who_may_submit_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.confirmed_action(team, {**STATUS_ACTION, 'submitters': [self.user_id(admin, 'bob')]})
            shown = ann.get(ACTION_URL)[1]
            self.assertEqual(shown['submitters'], [{'id': self.user_id(admin, 'bob'), 'name': 'Bob'}])
            status, body = self.submit(ann)
            self.assertEqual(status, 403, body)
            self.assertIn('只有', body['error'])
            self.assertEqual(self.submit(bob)[0], 200)
            status, body = ann.post('/api/workspace/actions', {**STATUS_ACTION, 'name': '另一个', 'submitters': [999999]})
            self.assertEqual(status, 400, body)


if __name__ == '__main__':
    unittest.main()
