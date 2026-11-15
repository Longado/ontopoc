"""A column kept from people: for them the type is the type without that property, and everything built on it is not there."""
import json
from urllib.parse import quote

from ontology_poc_generator.workspace_questions import _inputs, scope
from ontology_poc_generator.workspace_store import open_workspace
import unittest

from tests.test_object_types import ACTION_URL, DATASET_URL, ORDERS, STATUS_ACTION, VALID, ActionTests


def load_tests(loader, standard, pattern):
    """Only the tests written here: the class borrows the action tests' team and helpers, not their tests (they run in their own module)."""
    return unittest.TestSuite(ColumnAccessTests(name) for name in vars(ColumnAccessTests) if name.startswith('test_'))


class ColumnAccessTests(ActionTests):
    def keep(self, admin, column, *usernames, type_='order'):
        return admin.post('/api/workspace/column-access', {'type': type_, 'column': column, 'visible_to': [self.user_id(admin, u) for u in usernames]})

    def test_a_column_kept_from_a_person_is_gone_from_every_page_they_read_and_the_others_still_see_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.assertEqual(ann.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': []})[0], 403)   # the admin's
            status, body = self.keep(admin, '金额', 'ann')
            self.assertEqual((status, body['visible_to']), (200, ['Ann']))
            for person in (bob, vera):
                detail = person.get('/api/workspace/types/order')[1]
                self.assertNotIn('金额', [p['column'] for p in detail['properties']])
                self.assertNotIn('金额', [c['name'] for c in detail['columns']])
                objects = person.get('/api/workspace/types/order/objects')[1]
                self.assertNotIn('金额', [c['column'] for c in objects['columns']])
                self.assertEqual(objects['total'], 160)   # every row, without the column
                amounts = {r['金额'] for r in ORDERS}
                self.assertFalse(amounts & {str(v) for row in objects['rows'] for v in row if v is not None} - {r['订单号'] for r in ORDERS} - set('012'))
                table = person.post('/api/workspace/explore/table', {'query': {'type': 'order'}})[1]
                self.assertNotIn('金额', json.dumps(table['fields'] if 'fields' in table else table, ensure_ascii=False))
                status, _ = person.post('/api/workspace/explore/chart', {'query': {'type': 'order'}, 'chart': {'kind': 'bar', 'group': '状态码', 'measure': '金额', 'fn': 'sum'}})
                self.assertEqual(status, 400)
                node = next(n for n in person.get('/api/workspace/graph/relations')[1]['nodes'] if n['key'] == 'order')
                self.assertNotIn('金额', [p['column'] for p in node['properties']])
            self.assertEqual(bob.get(DATASET_URL)[0], 404)   # the dataset holds the column: not theirs
            self.assertEqual(bob.get(DATASET_URL + '?format=csv')[0], 404)
            self.assertEqual(bob.get('/api/ontology/runs')[0], 403)   # the early screen holds whole tables
            # Ann is on the list and the admin sees all
            for person in (ann, admin):
                self.assertIn('金额', [p['column'] for p in person.get('/api/workspace/types/order')[1]['properties']])
            self.assertEqual(ann.get(DATASET_URL)[0], 200)
            # Q&A: the model's ontology and the rows it is given have no 金额 for Bob
            conn = open_workspace(out / 'workspace.sqlite')
            bob_user = {'id': self.user_id(admin, 'bob'), 'role': 'builder', 'attrs': {}}
            inputs = _inputs(conn, scope(conn, bob_user))
            dumped = json.dumps(inputs['ontology'], ensure_ascii=False) + json.dumps(next(iter(inputs['bundle']['sources'].values()))['records'][:5], ensure_ascii=False)
            self.assertNotIn('金额', dumped)
            ann_user = {'id': self.user_id(admin, 'ann'), 'role': 'builder', 'attrs': {}}
            self.assertIn('金额', json.dumps(_inputs(conn, scope(conn, ann_user))['ontology'], ensure_ascii=False))
            logged = conn.execute("SELECT after_json FROM log WHERE change = 'column_access_changed'").fetchone()[0]
            conn.close()
            self.assertEqual(json.loads(logged), {'column': '金额', 'visible_to': ['Ann']})
            # back to everyone
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '金额', 'visible_to': 'everyone'})[1], {'visible_to': 'everyone'})
            self.assertIn('金额', [p['column'] for p in bob.get('/api/workspace/types/order')[1]['properties']])

    def test_what_reads_a_kept_column_is_not_there_and_nothing_can_be_defined_or_confirmed_on_the_type_by_that_person(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.confirmed_action(team)   # writes and tests 状态码
            self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)   # a view on 状态码
            self.assertEqual(self.keep(admin, '状态码', 'ann')[0], 200)
            # the action, the view and the meanings of 状态码 are not there for Bob
            self.assertEqual(bob.get(ACTION_URL)[0], 404)
            self.assertEqual(ann.get(ACTION_URL)[0], 200)
            self.assertNotIn('有效订单', [v['name'] for v in bob.get('/api/workspace/types/order/views')[1]['views']])
            self.assertIn('有效订单', [v['name'] for v in ann.get('/api/workspace/types/order/views')[1]['views']])
            items = bob.get('/api/workspace/queue')[1]['items']
            self.assertFalse([i for i in items if i.get('kind') in ('meaning', 'view') or '状态码' in json.dumps(i, ensure_ascii=False)])
            log = bob.get('/api/workspace/types/order/log')[1]['log']
            self.assertFalse([e for e in log if e['element'] in ('meaning', 'action', 'view')])
            self.assertTrue([e for e in ann.get('/api/workspace/types/order/log')[1]['log'] if e['element'] == 'meaning'])
            status, body = self.submit(bob)
            self.assertEqual(status, 404, body)
            # nothing defined on the type by Bob, and no confirming without seeing all of it
            for path, payload in (('/api/workspace/types/views', {**VALID, 'name': '另一个'}), ('/api/workspace/actions', {**STATUS_ACTION, 'name': '另一个'}),
                                  ('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{'value': '1', 'label': '制造中'}]}),
                                  ('/api/workspace/types/privacy', {'id': 'order', 'column': '金额', 'hide_values': True})):
                status, body = bob.post(path, payload)
                self.assertIn(status, (403, 404), (path, body))
            self.assertIsNone(bob.get('/api/workspace/types/order/views')[1]['form'])
            self.assertIsNone(bob.get('/api/workspace/actions?type=order')[1].get('form'))
            self.assertIsNotNone(ann.get('/api/workspace/types/order/views')[1]['form'])
            detail = bob.get('/api/workspace/types/order')[1]
            self.assertFalse(detail['can_confirm'])

    def test_a_key_or_unknown_column_cannot_be_kept_and_the_list_must_name_real_people(self):
        with self.service() as (base, out):
            team = self.team(base)
            admin = team['admin']
            for payload, status in (({'type': 'order', 'column': '订单号', 'visible_to': []}, 400), ({'type': 'order', 'column': '不存在', 'visible_to': []}, 400),
                                    ({'type': 'nothing', 'column': '金额', 'visible_to': []}, 404), ({'type': 'order', 'column': '金额', 'visible_to': [99999]}, 400),
                                    ({'type': 'order', 'column': '金额', 'visible_to': 'some'}, 400)):
                self.assertEqual(admin.post('/api/workspace/column-access', payload)[0], status, payload)
            table = admin.get('/api/workspace/permissions')[1]
            order = next(t for t in table['types'] if t['id'] == 'order')
            self.assertEqual(order['column_access'], {})
            self.assertEqual(self.keep(admin, '金额')[0], 200)   # nobody but admins
            order = next(t for t in admin.get('/api/workspace/permissions')[1]['types'] if t['id'] == 'order')
            self.assertEqual(order['column_access'], {'金额': []})

    def test_review_fixes_a_pending_record_a_second_type_on_the_dataset_and_the_lineage_cause_keep_the_column_from_the_person(self):
        from tests.test_object_types import orders_upload
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.confirmed_action(team)
            record = self.submit(ann)[1]['record']
            self.assertTrue([i for i in bob.get('/api/workspace/queue')[1]['items'] if i.get('kind') == 'approval'])
            # a second type over the same table, with 金额 among its properties: keeping 状态码 and 金额 on 订单 binds the table's columns
            second = {'english_name': 'order_copy', 'name': '订单副本', 'dataset': '订单', 'key': ['订单号'], 'description': '同一张表', 'properties': [{'column': '订单号'}, {'column': '金额'}]}
            self.assertEqual(ann.post('/api/workspace/types', second)[0], 200)
            self.assertEqual(self.keep(admin, '订单号', 'ann')[0], 400)   # a key of the type
            self.assertEqual(self.keep(admin, '状态码', 'ann')[0], 200)
            self.assertEqual(self.keep(admin, '金额', 'ann')[0], 200)
            # the pending record is about a column kept from Bob: no card for him
            items = bob.get('/api/workspace/queue')[1]['items']
            self.assertFalse([i for i in items if i.get('kind') == 'approval'], items)
            self.assertNotIn('状态码', json.dumps(items, ensure_ascii=False))
            self.assertEqual(bob.post('/api/workspace/actions/decide', {'id': record, 'decision': 'approve'})[0], 404)
            self.assertNotIn('金额', [p['column'] for p in bob.get('/api/workspace/types/order_copy')[1]['properties']])
            self.assertIn('金额', [p['column'] for p in ann.get('/api/workspace/types/order_copy')[1]['properties']])
            # new values under 状态码 send its meanings to another look: the lineage does not name the column to Bob
            moved = orders_upload(lambda r, i: {**r, '状态码': '3'} if i == 0 else r, target='订单', mode='update_by_key', key_columns=['订单号'])
            status, body = admin.post('/api/workspace/datasets/upload', {'files': [moved]})
            self.assertEqual(status, 200, body)
            for path in ('/api/workspace/graph/relations', '/api/workspace/graph/lineage', '/api/workspace/types/order', '/api/workspace/queue'):
                self.assertNotIn('状态码', json.dumps(bob.get(path)[1], ensure_ascii=False), path)
            self.assertIn('状态码', json.dumps(ann.get('/api/workspace/graph/relations')[1], ensure_ascii=False))
            node = next(n for n in ann.get('/api/workspace/graph/relations')[1]['nodes'] if n['key'] == 'order')
            self.assertIsNotNone(node['stale'])   # the chain is really there: Ann is told what moved
            self.assertIn('状态码', json.dumps(node['stale'], ensure_ascii=False))
            bob_node = next(n for n in bob.get('/api/workspace/graph/relations')[1]['nodes'] if n['key'] == 'order')
            self.assertIsNotNone(bob_node['stale'])
