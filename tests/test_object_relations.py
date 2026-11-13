"""Relations, the 待确认 queue and per-type visibility on the workspace, walked through the real service with two builders, a viewer and an admin on the
seven planted tables. Expected numbers come from the planted fixtures (160 orders, 3 of them naming KH099 which the customer table lacks; KH012 twice in the
customer table), counted from the records here, not from the service."""
import base64
import csv
import io
import unittest

from ontology_poc_generator.type_access import visible_type_ids
from ontology_poc_generator.workspace_store import open_workspace
from tests import test_workspace_store as planted
from tests.test_object_types import TABLES
from tests.test_two_person import SigningTestCase

SOURCES = planted.planted_bundle()['sources']
ORDERS, CUSTOMERS = SOURCES['订单']['records'], SOURCES['客户']['records']
KH012_ORDERS = sum(1 for r in ORDERS if r['客户编号'] == 'KH012')
ORDER = {'english_name': 'order', 'name': '订单', 'dataset': '订单', 'key': ['订单号'], 'properties': [{'column': '订单号'}, {'column': '金额'}]}
CUSTOMER = {'english_name': 'customer', 'name': '客户', 'dataset': '客户', 'key': ['客户编号', '城市'], 'properties': [{'column': '客户名称'}, {'column': '客户等级'}]}   # 客户编号 alone repeats (KH012)
RELATION = {'english_name': 'order_customer', 'name': '订单属于客户', 'from': 'order', 'to': 'customer', 'cardinality': 'many_to_one',
            'from_column': '客户编号', 'to_column': '客户编号'}


def orders_csv(change) -> dict:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(ORDERS[0]))
    writer.writeheader()
    writer.writerows(change(dict(r)) for r in ORDERS)
    return {'filename': '订单.csv', 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode(), 'target': '订单', 'mode': 'overwrite'}


class RelationTests(SigningTestCase):
    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        return team

    def propose_types(self, ann):
        for payload in (ORDER, CUSTOMER):
            status, body = ann.post('/api/workspace/types', payload)
            self.assertEqual(status, 200, body)

    def confirm_types(self, bob):
        for name in ('order', 'customer'):
            version = bob.get(f'/api/workspace/types/{name}')[1]['version']
            status, body = bob.post('/api/workspace/types/confirm', {'id': name, 'version': version})
            self.assertEqual(status, 200, body)

    def detail(self, client, name='order_customer'):
        status, body = client.get(f'/api/workspace/relations/{name}')
        self.assertEqual(status, 200, body)
        return body

    def confirmed_relation(self, team):
        self.propose_types(team['ann'])
        self.assertEqual(team['ann'].post('/api/workspace/relations', RELATION)[0], 200)
        self.confirm_types(team['bob'])
        detail = self.detail(team['bob'])
        status, body = team['bob'].post('/api/workspace/queue/confirm', {'element': 'relation:order_customer', 'version': detail['version'], 'seen': detail['check']['signature']})
        self.assertEqual(status, 200, body)

    def test_the_relation_shows_157_of_160_with_kh099_listed_and_the_kh012_fan_out_and_waits_for_both_types_and_another_builder(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.propose_types(ann)
            status, body = ann.post('/api/workspace/relations', RELATION)
            self.assertEqual(status, 200, body)
            self.assertEqual((body['numbers']['rows'], body['numbers']['matched'], body['numbers']['unmatched']), (160, 157, 3))
            detail = self.detail(ann)
            check = detail['check']
            self.assertEqual((detail['state'], detail['proposed_by'], detail['from_name'], detail['to_name']), ('checked', 'Ann', '订单', '客户'))
            self.assertEqual(check['samples'], [{'key': 'KH099', 'rows': 3}])
            self.assertEqual([r[-1] for r in check['unmatched_rows']['rows']], ['KH099'] * 3)
            self.assertEqual((check['fanout']['keys'], check['fanout']['source_rows'], check['fanout']['extra_rows']), (1, KH012_ORDERS, KH012_ORDERS))
            self.assertEqual([r[0] for r in check['fanout']['rows']['rows']], ['KH012', 'KH012'])
            self.assertIn('KH099', ' '.join(e['text'] for e in detail['lines']))
            self.assertIn('KH012（2 次）', ' '.join(e['text'] for e in detail['lines']))
            # not while the types are not confirmed, however many people are willing
            self.assertEqual(detail['waiting_on'], [{'id': 'order', 'name': '订单', 'state': 'checked'}, {'id': 'customer', 'name': '客户', 'state': 'checked'}])
            self.assertFalse(self.detail(bob)['can_confirm'])
            status, body = bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': detail['version'], 'seen': check['signature']})
            self.assertEqual(status, 409)
            self.assertIn('都确认之后才能确认', body['error'])
            self.confirm_types(bob)
            # the proposer sees no button and cannot; the other builder can, but only on the numbers they saw
            self.assertEqual((self.detail(ann)['can_confirm'], self.detail(bob)['can_confirm']), (False, True))
            version = self.detail(ann)['version']
            self.assertEqual(ann.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': version, 'seen': check['signature']})[0], 403)
            self.assertEqual(bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': version, 'seen': [160, 160, 0, 0, 0, 0]})[0], 409)
            self.assertEqual(bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': version})[0], 400)
            status, body = bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': version, 'seen': check['signature']})
            self.assertEqual(status, 200, body)
            detail = self.detail(bob)
            self.assertEqual((detail['state'], detail['confirmed_by'], detail['confirmed_on']), ('confirmed', 'Bob', {'订单': 1, '客户': 1}))
            self.assertEqual(detail['anchored']['numbers']['matched'], 157)
            conn = open_workspace(out / 'workspace.sqlite')
            self.assertEqual(sorted(r[0] for r in conn.execute("SELECT depends_on FROM element_dep WHERE element_id = 'relation:order_customer'")),
                             ['dataset:客户', 'dataset:订单', 'objtype:customer', 'objtype:order'])
            self.assertEqual(conn.execute("SELECT confirmed_by, proposed_by FROM confirmation WHERE element_id = 'relation:order_customer'").fetchall(), [('Bob', 'Ann')])
            conn.close()
            log = bob.get('/api/workspace/relations/order_customer/log')[1]['log']
            self.assertEqual([(e['who'], e['to']) for e in log], [('Bob', 'confirmed'), ('Ann', 'checked')])

    def test_other_builder_finds_the_item_through_the_count_on_the_queue_and_confirms_it_there(self):
        with self.service() as (base, _):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.propose_types(ann)
            ann.post('/api/workspace/relations', RELATION)
            self.assertEqual((ann.get('/api/workspace/queue')[1]['count'], bob.get('/api/workspace/queue')[1]['count']), (0, 2))   # the two types, not the relation yet
            self.assertEqual(team['vera'].get('/api/workspace/queue')[0], 403)
            self.confirm_types(bob)
            self.assertEqual(bob.get('/api/workspace/queue')[1]['count'], 1)
            queue = bob.get('/api/workspace/queue')[1]
            item = next(i for i in queue['items'] if i['kind'] == 'relation')
            self.assertEqual((item['element'], item['state'], item['proposed_by'], item['can_confirm']), ('relation:order_customer', 'checked', 'Ann', True))
            self.assertIn('157', item['lines'][0]['text'])
            as_ann = next(i for i in ann.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'relation')
            self.assertEqual((as_ann['can_confirm'], as_ann['confirmers']), (False, ['Bob', '管理员']))   # "needs another builder", no button
            status, body = bob.post('/api/workspace/queue/confirm', {'element': item['element'], 'version': item['version'], 'seen': item['signature']})
            self.assertEqual(status, 200, body)
            self.assertEqual((bob.get('/api/workspace/queue')[1]['items'], bob.get('/api/workspace/queue')[1]['count']), ([], 0))

    def test_an_item_can_be_sent_back_with_a_reason_and_is_put_forward_again_by_saving(self):
        with self.service() as (base, _):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.propose_types(ann)
            ann.post('/api/workspace/relations', RELATION)
            item = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['element'] == 'objtype:customer')
            self.assertEqual(ann.post('/api/workspace/queue/send-back', {'element': item['element'], 'version': item['version'], 'reason': '不行'})[0], 403)   # its proposer
            self.assertEqual(bob.post('/api/workspace/queue/send-back', {'element': item['element'], 'version': item['version'], 'reason': ' '})[0], 400)
            status, body = bob.post('/api/workspace/queue/send-back', {'element': item['element'], 'version': item['version'], 'reason': '主键该是客户编号加城市以外的东西'})
            self.assertEqual((status, body), (200, {'state': 'rejected'}))
            detail = ann.get('/api/workspace/types/customer')[1]
            self.assertEqual((detail['state'], detail['reason'], detail['can_confirm']), ('rejected', '主键该是客户编号加城市以外的东西', False))
            self.assertEqual(bob.post('/api/workspace/types/confirm', {'id': 'customer', 'version': detail['version']})[0], 409)
            self.assertNotIn('objtype:customer', [i['element'] for i in bob.get('/api/workspace/queue')[1]['items']])
            log = ann.get('/api/workspace/types/customer/log')[1]['log']
            self.assertEqual((log[0]['who'], log[0]['change'], log[0]['reason']), ('Bob', 'sent_back', '主键该是客户编号加城市以外的东西'))
            status, body = ann.post('/api/workspace/types/update', {**CUSTOMER, 'id': 'customer', 'version': detail['version']})
            self.assertEqual((status, body['state']), (200, 'checked'))   # saved again: forward anew, a reviewer other than Ann confirms it
            self.assertIn('objtype:customer', [i['element'] for i in bob.get('/api/workspace/queue')[1]['items']])

    def test_new_connected_rows_or_a_type_that_stops_being_confirmed_send_a_confirmed_relation_back_with_the_reason(self):
        with self.service() as (base, _):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.confirmed_relation(team)
            # KH099 is replaced by a customer that exists: 160 of 160 connect, which is not what Bob confirmed
            fixed = lambda r: {**r, '客户编号': 'KH001' if r['客户编号'] == 'KH099' else r['客户编号']}
            status, body = ann.post('/api/workspace/datasets/upload', {'files': [orders_csv(fixed)]})
            self.assertEqual(status, 200, body)
            detail = self.detail(bob)
            self.assertEqual(detail['state'], 'needs_look')
            self.assertIn('157 / 160', detail['reason'])
            self.assertIn('160 / 160', detail['reason'])
            self.assertIn('订单 第 2 版', detail['reason'])
            self.assertEqual(self.detail(bob, 'order_customer')['confirmed_by'], 'Bob')   # who confirmed it before stays beside the reason
            item = next(i for i in bob.get('/api/workspace/queue')[1]['items'] if i['kind'] == 'relation')   # it is in the queue again, with the reason first
            self.assertEqual((item['state'], item['lines'][0]['ok']), ('needs_look', False))
            self.assertIn('157 / 160', item['lines'][0]['text'])
            self.assertEqual(self.detail(ann)['can_confirm'], False)   # Ann proposed it
            status, body = bob.post('/api/workspace/relations/confirm', {'id': 'order_customer', 'version': detail['version'], 'seen': detail['check']['signature']})
            self.assertEqual(status, 200, body)   # looked at again on the new numbers
            self.assertEqual(self.detail(bob)['anchored']['numbers']['matched'], 160)
            # an upload that leaves the connected rows as they were does not move it
            ann.post('/api/workspace/datasets/upload', {'files': [orders_csv(lambda r: {**fixed(r), '金额': r['金额']})]})
            self.assertEqual((self.detail(bob)['state'], self.detail(bob)['reason']), ('confirmed', None))
            # a type it stands on is changed (a different key): the relation cannot stay confirmed
            version = ann.get('/api/workspace/types/order')[1]['version']
            self.assertEqual(ann.post('/api/workspace/types/update', {**ORDER, 'id': 'order', 'version': version, 'key': ['订单号', '客户编号']})[0], 200)
            detail = self.detail(bob)
            self.assertEqual(detail['state'], 'needs_look')
            self.assertIn('“订单”类型改了主键', detail['reason'])
            self.assertEqual(detail['waiting_on'][0]['id'], 'order')

    def test_a_viewer_outside_the_list_sees_neither_the_type_nor_its_objects_nor_the_relation(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.confirmed_relation(team)
            self.assertEqual(sorted(t['id'] for t in vera.get('/api/workspace/types')[1]['types']), ['customer', 'order'])
            self.assertEqual([r['id'] for r in vera.get('/api/workspace/relations')[1]['relations']], ['order_customer'])
            self.assertEqual(vera.get('/api/workspace/types/order/objects')[0], 200)
            people = {p['name']: p['id'] for p in admin.get('/api/workspace/permissions')[1]['people']}
            self.assertEqual(ann.get('/api/workspace/permissions')[0], 403)
            self.assertEqual(ann.post('/api/workspace/permissions', {'type': 'order', 'visible_to': 'everyone'})[0], 403)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [people['Bob']]})[1], {'visible_to': ['Bob']})
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [999]})[0], 400)
            for hidden in (vera, ann):   # not on the list: a viewer, and a builder as well
                self.assertEqual([t['id'] for t in hidden.get('/api/workspace/types')[1]['types'] if t['id'] == 'order'], [])
                for path in ('/api/workspace/types/order', '/api/workspace/types/order/objects', '/api/workspace/types/order/log'):
                    self.assertEqual(hidden.get(path)[0], 404, path)
                self.assertEqual(hidden.get('/api/workspace/relations')[1]['relations'], [])
                self.assertEqual(hidden.get('/api/workspace/relations/order_customer')[0], 404)
                self.assertEqual(hidden.get('/api/workspace/relations/order_customer/log')[0], 404)
                dataset = hidden.get('/api/workspace/datasets/%E8%AE%A2%E5%8D%95')[1]
                self.assertEqual(dataset['readers'], [])   # which types read it is not told to someone who cannot see them
            self.assertEqual([t['id'] for t in vera.get('/api/workspace/types')[1]['types']], ['customer'])
            self.assertEqual([i['element'] for i in ann.get('/api/workspace/queue')[1]['items']], [])
            self.assertEqual(bob.get('/api/workspace/types/order')[0], 200)   # on the list
            self.assertEqual(sorted(i['id'] for i in bob.get('/api/workspace/types')[1]['types']), ['customer', 'order'])
            self.assertEqual(admin.get('/api/workspace/types/order')[0], 200)   # admins see all
            self.assertEqual(admin.get('/api/workspace/permissions')[1]['types'][1]['user_ids'], [people['Bob']])
            self.assertEqual(ann.post('/api/workspace/relations/update', {**RELATION, 'id': 'order_customer', 'version': 1})[0], 404)
            self.assertEqual(ann.post('/api/workspace/relations', {**RELATION, 'english_name': 'again'})[0], 404)   # nor can a relation be made on a type they cannot see
            conn = open_workspace(out / 'workspace.sqlite')
            for who, role, scope in (('Vera', 'viewer', ['customer']), ('Ann', 'builder', ['customer']), ('Bob', 'builder', ['customer', 'order'])):   # the scope of a question
                self.assertEqual(visible_type_ids(conn, {'id': people[who], 'role': role}, confirmed_only=True), scope, who)
            conn.close()
            log = bob.get('/api/workspace/types/order/log')[1]['log']
            self.assertEqual((log[0]['who'], log[0]['change'], log[0]['visible_to']), ('管理员', 'access_changed', ['Bob']))
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': 'everyone'})[1], {'visible_to': 'everyone'})
            self.assertEqual(vera.get('/api/workspace/types/order')[0], 200)


if __name__ == '__main__':
    unittest.main()
