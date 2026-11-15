"""Confirming together what one upload moved, walked through the real service on the planted tables. A builder overwrites 订单 with a shifted status code (a new
3, no 0); the meanings, the type, a view and a relation that stood on it come back for another look, and the second builder confirms them in one action: in
dependency order, each through the confirm it has on its own page, all or nothing. Expected numbers come from the planted rows."""
import json
import sqlite3
import unittest
from unittest import mock

from ontology_poc_generator import batch_confirm
from ontology_poc_generator.accounts import get_user
from ontology_poc_generator.actor import set_actor
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_object_relations import CUSTOMER, RELATION, customers_mended
from tests.test_object_types import ORDER, ORDERS, TABLES, VALID, shifted_orders_csv
from tests.test_two_person import SigningTestCase

ORDER_ELEMENTS = ['enum:order:状态码', 'objtype:order', 'objview:有效订单', 'relation:order_customer']   # the order they are confirmed in
NEW_MEANINGS = [{'value': '0', 'label': ''}, {'value': '1', 'label': '已交付'}, {'value': '2', 'label': '已取消'}, {'value': '3', 'label': '已发货待签收'}]
NEW_ROWS = sum(r['状态码'] == '2' for r in ORDERS)   # the old 2 is the new 3
GROUP = '/api/workspace/queue/group?dataset=订单&version=2'
CONFIRM = '/api/workspace/queue/confirm-group'


class BatchConfirmTests(SigningTestCase):
    def ops_overwrite(self, base):
        """Ann proposes the order type with its meanings, the customer type, a relation between them and a view; Bob confirms them all. Then Ann, the operations
        manager, overwrites 订单 with the codes shifted up by one and writes the meanings again with the new 3 meaning 已发货待签收."""
        team = self.people(base, 'ann', 'bob', 'cat')
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        for payload in (ORDER, CUSTOMER):
            self.assertEqual(ann.post('/api/workspace/types', payload)[0], 200)
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
        self.assertEqual(ann.post('/api/workspace/relations', RELATION)[0], 200)
        self.assertEqual(ann.post('/api/workspace/types/views', VALID)[0], 200)
        meanings = next(p for p in self.type_of(bob, 'order')['properties'] if p['column'] == '状态码')['meanings']
        self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meanings['version'], 'seen': meanings['seen']})[0], 200)
        for name in ('order', 'customer'):
            shown = self.type_of(bob, name)
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': name, 'version': shown['version'], 'seen': shown['seen']})[0], 200)
        relation = bob.get('/api/workspace/relations/order_customer')[1]
        self.assertEqual(bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': relation['version'], 'seen': relation['check']['signature']})[0], 200)
        view = self.view_of(bob, 'order', '有效订单')
        self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': view['version'], 'seen': view['seen']})[0], 200)
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
        self.assertEqual(ann.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': NEW_MEANINGS})[0], 200)
        return team

    def type_of(self, client, name):
        status, body = client.get(f'/api/workspace/types/{name}')
        self.assertEqual(status, 200, body)
        return body

    def view_of(self, client, type_name, name):
        status, body = client.get(f'/api/workspace/types/{type_name}/views')
        self.assertEqual(status, 200, body)
        return next((v for v in body['views'] if v['name'] == name), None)

    def group(self, client):
        status, body = client.get(GROUP)
        self.assertEqual(status, 200, body)
        return body

    def request(self, group, only=None, choice='in', seen=True, ready_only=True):
        """What the page sends once everything is seen: each item it offers to confirm with the version and the data it showed, and the answer to the view's question."""
        items = []
        for item in group['items']:
            if (only and item['element'] not in only) or (ready_only and not item['ready']):
                continue
            body = {'element': item['element'], 'version': item['version']}
            if seen:
                body['seen'] = item['seen']
            if item['kind'] == 'view':
                body['new_values'] = [{'column': n['column'], 'value': n['value'], 'choice': choice} for n in item['new_values']]
            items.append(body)
        return {'dataset': group['dataset'], 'version': group['version'], 'items': items}

    def states(self, client):
        return {i['element']: i['state'] for i in client.get('/api/workspace/queue')[1]['items']}

    def test_the_overwrite_puts_the_four_things_it_moved_in_one_group_in_dependency_order(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            queue = team['bob'].get('/api/workspace/queue')[1]
            self.assertEqual(sorted(i['element'] for i in queue['items']), sorted(ORDER_ELEMENTS))
            self.assertEqual([(g['dataset'], g['version'], g['uploaded_by'], g['hidden'], g['items']) for g in queue['groups']], [('订单', 2, 'Ann', 0, ORDER_ELEMENTS)])
            self.assertEqual({i['group'] for i in queue['items']}, {queue['groups'][0]['key']})
            group = self.group(team['bob'])
            self.assertEqual([i['element'] for i in group['items']], ORDER_ELEMENTS)
            self.assertEqual([(i['mine'], i['ready'], i['why_not']) for i in group['items']], [(True, True, None)] * 4)   # none of them can be confirmed alone yet but the first; in the group each waits only for what comes before it
            meaning, kind, view, relation = group['items']
            self.assertEqual([(v['value'], v['label_then'], v['rows_then'], v['label'], v['rows']) for v in meaning['values']],
                             [('0', '已交付', 96, '', None), ('1', '生产中', 48, '已交付', 96), ('2', '已取消', 16, '已取消', 48), ('3', None, None, '已发货待签收', NEW_ROWS)])   # what each code meant and how many rows had it when it was confirmed, and now
            self.assertEqual(view['new_values'], [{'column': '状态码', 'value': '3', 'label': '已发货待签收', 'rows': NEW_ROWS}])
            self.assertEqual(relation['lines'][0]['ok'], False)   # why it came back is the first line of each, as on the queue card
            self.assertEqual([m['can_confirm'] for m in queue['items'] if m['element'] != 'enum:order:状态码'], [False] * 3)

    def test_a_person_who_wrote_every_item_is_offered_none_of_them(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            group = self.group(team['ann'])
            self.assertEqual([(i['mine'], i['ready']) for i in group['items']], [(False, False)] * 4)
            self.assertTrue(all(i['why_not'] for i in group['items']))
            self.assertEqual(team['ann'].post(CONFIRM, self.request(self.group(team['bob'])))[0], 409)   # nothing of it is hers to confirm
            self.assertEqual(team['cat'].get(GROUP)[1]['items'][0]['element'], 'enum:order:状态码')   # a third builder sees the same group

    def test_the_group_is_confirmed_in_one_action_only_with_every_item_seen_and_the_view_question_answered(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            group = self.group(bob)
            before = self.states(bob)
            status, body = bob.post(CONFIRM, self.request(group, seen=False))   # the data each item showed is asked for, as on its own page
            self.assertEqual(status, 400, body)
            self.assertIn('确认要带上你看到的', body['error'])
            status, body = bob.post(CONFIRM, {**self.request(group), 'items': [{k: v for k, v in i.items() if k != 'new_values'} for i in self.request(group)['items']]})
            self.assertEqual(status, 409, body)
            self.assertIn('有效订单', body['error'])
            self.assertIn('新值 3', body['error'])
            self.assertIn('算不算进来', body['error'])
            self.assertEqual(self.states(bob), before)   # the meanings and the type came first and were not kept: all or nothing
            partial = self.request(group, only={'enum:order:状态码', 'objtype:order'})
            status, body = bob.post(CONFIRM, partial)
            self.assertEqual(status, 409, body)
            self.assertIn('有效订单', body['error'])   # what is ready and left out of the request is asked for by name
            self.assertEqual(self.states(bob), before)
            status, body = bob.post(CONFIRM, self.request(group))
            self.assertEqual(status, 200, body)
            self.assertEqual([c['element'] for c in body['confirmed']], ORDER_ELEMENTS)
            self.assertEqual((body['left_out'], body['sent_on']), ([], []))
            queue = bob.get('/api/workspace/queue')[1]
            self.assertEqual((queue['items'], queue['groups']), ([], []))
            self.assertEqual(self.view_of(bob, 'order', '有效订单')['confirmed_on'], {'订单': 2})
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(conn.execute('SELECT element_id, confirmed_by, proposed_by, dataset_versions_json FROM confirmation ORDER BY id DESC LIMIT 2').fetchall()[::-1],
                             [('objview:有效订单', 'Bob', 'Ann', '{"订单": 2}'), ('relation:order_customer', 'Bob', 'Ann', '{"订单": 2, "客户": 2}')])
            conn.close()

    def test_each_item_log_gets_its_normal_confirm_line_and_one_that_says_it_was_confirmed_with_three_others(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            self.assertEqual(team['bob'].post(CONFIRM, self.request(self.group(team['bob'])))[0], 200)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            for element in ORDER_ELEMENTS:
                lines = conn.execute("SELECT change, who, after_json FROM log WHERE element_id = ? AND who = 'Bob' ORDER BY id", (element,)).fetchall()[-2:]   # the earlier confirmation on version 1 stays above
                self.assertEqual([c for c, _, _ in lines], ['confirmed', 'confirmed_together'], element)
                self.assertEqual(json.loads(lines[1][2]), {'with': 3, 'text': '和另外 3 项一起确认'})
            conn.close()
            log = team['bob'].get('/api/workspace/types/order/log')[1]['log']
            self.assertIn('和另外 3 项一起确认', [e['text'] for e in log if e['change'] == 'confirmed_together'])

    def test_a_failure_in_the_last_item_takes_back_the_ones_confirmed_before_it(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            group = self.group(bob)
            before = self.states(bob)
            wrong = self.request(group)
            wrong['items'][-1]['seen'] = [160, 157, 3, 0, 0, 1]   # the relation's counts as they were not: its own check refuses
            status, body = bob.post(CONFIRM, wrong)
            self.assertEqual(status, 409, body)
            self.assertIn('订单', body['error'].split('：')[0])
            self.assertIn('数据在你看过之后变了', body['error'])
            self.assertEqual(self.states(bob), before)
            conn = open_workspace(out / 'workspace.sqlite')
            confirmations = conn.execute('SELECT COUNT(*) FROM confirmation').fetchone()[0]
            kept = {k: v for k, v in conn.execute('SELECT element_id, version FROM element_state')}
            user = get_user(conn, next(i for i, in conn.execute("SELECT id FROM user WHERE username = 'bob'")))
            set_actor(user)
            with mock.patch.object(batch_confirm, 'confirm_relation', side_effect=RuntimeError('disk gone')):   # an error nobody foresaw, after three were written
                with self.assertRaises(RuntimeError):
                    batch_confirm.confirm_group(conn, self.request(group), 'Bob', user)
            set_actor(None)
            self.assertFalse(conn.in_transaction)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM confirmation').fetchone()[0], confirmations)
            self.assertEqual({k: v for k, v in conn.execute('SELECT element_id, version FROM element_state')}, kept)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM log WHERE change = 'confirmed_together'").fetchone()[0], 0)
            conn.close()
            self.assertEqual(bob.post(CONFIRM, self.request(self.group(bob)))[0], 200)   # and the group is still there to be confirmed

    def test_the_data_moving_between_looking_and_confirming_refuses_the_whole_group(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            group = self.group(bob)
            self.assertEqual(team['ann'].post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{**m, 'label': m['label'] + '。'} if m['label'] else m for m in NEW_MEANINGS]})[0], 200)
            before = self.states(bob)
            status, body = bob.post(CONFIRM, self.request(group))   # the meanings he looked at were written again
            self.assertEqual(status, 409, body)
            self.assertIn('状态码', body['error'])
            self.assertEqual(self.states(bob), before)

    def test_the_person_who_edited_one_item_does_not_confirm_it_and_it_is_listed_as_not_theirs_while_the_rest_are_confirmed(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            view = self.view_of(bob, 'order', '有效订单')
            both = [{'column': '状态码', 'op': 'is_not', 'label': '已取消'}, {'column': '状态码', 'op': 'is_not', 'label': '已发货待签收'}]
            self.assertEqual(bob.post('/api/workspace/types/views/update', {**VALID, 'id': '有效订单', 'version': view['version'], 'filters': both})[0], 200)   # Bob rewrote the view's conditions
            group = self.group(bob)
            mine = {i['element']: (i['mine'], i['ready']) for i in group['items']}
            self.assertEqual(mine, {'enum:order:状态码': (True, True), 'objtype:order': (True, True), 'objview:有效订单': (False, False), 'relation:order_customer': (True, True)})
            view_item = next(i for i in group['items'] if i['kind'] == 'view')
            self.assertIn('你提的', view_item['why_not'])
            status, body = bob.post(CONFIRM, self.request(group))
            self.assertEqual(status, 200, body)
            self.assertEqual([c['element'] for c in body['confirmed']], ['enum:order:状态码', 'objtype:order', 'relation:order_customer'])
            self.assertEqual([(l['element'], l['title']) for l in body['left_out']], [('objview:有效订单', '有效订单（订单的视图）')])
            self.assertIn('你提的', body['left_out'][0]['why'])
            self.assertEqual(self.states(bob), {'objview:有效订单': 'checked'})
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(json.loads(conn.execute("SELECT after_json FROM log WHERE element_id = 'relation:order_customer' AND change = 'confirmed_together'").fetchone()[0]),
                             {'with': 2, 'text': '和另外 2 项一起确认'})   # with the two that were confirmed, not the one left out
            conn.close()
            shown = self.view_of(team['cat'], 'order', '有效订单')
            self.assertEqual(team['cat'].post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': shown['version'], 'seen': shown['seen']})[0], 200)   # a third builder does

    def test_what_waits_on_an_item_that_is_not_theirs_is_left_out_with_the_reason_instead_of_failing_the_group(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            self.assertEqual(bob.post('/api/workspace/types/meanings', {'id': 'order', 'column': '状态码', 'values': [{**m, 'label': m['label'] + '，'} if m['label'] else m for m in NEW_MEANINGS]})[0], 200)   # Bob wrote the meanings
            group = self.group(bob)
            self.assertEqual([(i['element'], i['ready']) for i in group['items']], [(e, False) for e in ORDER_ELEMENTS])   # the type, the view and the relation stand on them
            self.assertIn('要先确认', group['items'][1]['why_not'])
            status, body = bob.post(CONFIRM, self.request(group, ready_only=False))
            self.assertEqual(status, 409, body)   # nothing left that he can confirm
            self.assertIn('没有你现在能确认的', body['error'])

    def test_a_builder_who_cannot_see_one_item_gets_the_others_and_a_count_of_what_they_cannot_see(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            admin, bob = team['admin'], team['bob']
            people = {p['name']: p['id'] for p in admin.get('/api/workspace/permissions')[1]['people']}
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [people['Ann'], people['Cat']]})[0], 200)   # Bob loses the customer type, and with it the relation
            queue = bob.get('/api/workspace/queue')[1]
            self.assertEqual([(g['items'], g['hidden']) for g in queue['groups']], [(ORDER_ELEMENTS[:3], 1)])
            group = self.group(bob)
            self.assertEqual(([i['element'] for i in group['items']], group['hidden']), (ORDER_ELEMENTS[:3], 1))
            self.assertNotIn('客户', json.dumps(group, ensure_ascii=False))   # a number, not a name
            status, body = bob.post(CONFIRM, self.request(group))
            self.assertEqual(status, 200, body)
            self.assertEqual([c['element'] for c in body['confirmed']], ORDER_ELEMENTS[:3])
            self.assertEqual(team['cat'].get('/api/workspace/queue')[1]['items'][0]['element'], 'relation:order_customer')

    def test_saying_a_new_value_does_not_count_changes_the_view_for_the_other_builder_and_the_rest_are_still_confirmed(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            status, body = bob.post(CONFIRM, self.request(self.group(bob), choice='out'))
            self.assertEqual(status, 200, body)
            self.assertEqual(([c['element'] for c in body['confirmed']], [c['element'] for c in body['sent_on']]), (['enum:order:状态码', 'objtype:order', 'relation:order_customer'], ['objview:有效订单']))
            moved = self.view_of(bob, 'order', '有效订单')
            self.assertEqual((moved['state'], moved['proposed_by'], moved['can_confirm']), ('checked', 'Bob', False))
            self.assertEqual(self.group(team['cat'])['items'][0]['element'], 'objview:有效订单')

    def test_one_item_left_is_not_a_group(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            meanings = next(p for p in self.type_of(bob, 'order')['properties'] if p['column'] == '状态码')['meanings']
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'column': '状态码', 'version': meanings['version'], 'seen': meanings['seen']})[0], 200)
            shown = self.type_of(bob, 'order')
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen']})[0], 200)
            shown = self.view_of(bob, 'order', '有效订单')
            self.assertEqual(bob.post('/api/workspace/types/views/confirm', {'id': '有效订单', 'version': shown['version'], 'seen': shown['seen'],
                                                                              'new_values': [{'column': '状态码', 'value': '3', 'choice': 'in'}]})[0], 200)
            queue = bob.get('/api/workspace/queue')[1]
            self.assertEqual(([i['element'] for i in queue['items']], queue['groups'], 'group' in queue['items'][0]), (['relation:order_customer'], [], False))

    def test_a_request_for_something_that_is_not_in_the_group_or_is_malformed_is_refused(self):
        with self.service() as (base, out):
            team = self.ops_overwrite(base)
            bob = team['bob']
            self.assertEqual(bob.get('/api/workspace/queue/group?dataset=订单&version=1')[0], 404)
            self.assertEqual(bob.get('/api/workspace/queue/group?dataset=客户&version=2')[0], 404)
            self.assertEqual(bob.get('/api/workspace/queue/group?dataset=订单')[0], 400)
            request = self.request(self.group(bob))
            self.assertEqual(bob.post(CONFIRM, {**request, 'items': [*request['items'], {'element': 'objtype:customer', 'version': 1, 'seen': {}}]})[0], 404)
            self.assertEqual(bob.post(CONFIRM, {**request, 'items': request['items'] + request['items'][:1]})[0], 400)
            self.assertEqual(bob.post(CONFIRM, {**request, 'items': []})[0], 400)
            self.assertEqual(bob.post(CONFIRM, {**request, 'version': 1})[0], 404)
            self.assertEqual(bob.post(CONFIRM, {**request, 'items': 'all'})[0], 400)
            self.assertEqual(team['admin'].get(GROUP)[0], 200)   # an admin is a builder here


if __name__ == '__main__':
    unittest.main()
