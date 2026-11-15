"""Notices: an action names who hears when one of its changes is approved: named people, the people whose attribute equals a column of the row, or the people whose
attribute equals a column of the object the row points to through a relation. A notice goes only to someone who may read that row; the approver is not told."""
from urllib.parse import quote

from tests.test_derived_properties import ORDER, RELATIONS, DerivedTestCase
from tests.test_object_relations import CUSTOMER
from tests.test_explorer import CUSTOMERS, ORDERS

ACTION = {'name': '改交付天数', 'type': 'order', 'properties': ['交付天数'], 'description': '客户改了交付时间'}
ACTION_URL = '/api/workspace/actions/' + quote(ACTION['name'])
THE_ORDER = next(r for r in ORDERS if r['客户编号'] == 'KH001')
ITS_CITY = next(c['城市'] for c in CUSTOMERS if c['客户编号'] == 'KH001')


class NoticeTests(DerivedTestCase):
    def user_id(self, admin, username):
        return next(u['id'] for u in admin.get('/api/users')[1]['users'] if u['username'] == username)

    def ready(self, team):
        """The planted world, the action confirmed (Ann puts it forward, Bob confirms)."""
        self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post('/api/workspace/actions', ACTION)[0], 200)
        shown = bob.get(ACTION_URL)[1]
        status, body = bob.post('/api/workspace/actions/confirm', {'id': ACTION['name'], 'version': shown['version']})
        self.assertEqual(status, 200, body)

    def change(self, submitter, approver, order=THE_ORDER, days='45'):
        status, body = submitter.post('/api/workspace/actions/submit', {'action': ACTION['name'], 'key': {'订单号': order['订单号']}, 'params': {'交付天数': days}, 'reason': '客户要求'})
        self.assertEqual(status, 200, body)
        status, body = approver.post('/api/workspace/actions/decide', {'id': body['record'], 'decision': 'approve'})
        self.assertEqual((status, body.get('state')), (200, 'approved'), body)

    def notices(self, client):
        status, body = client.get('/api/workspace/notices')
        self.assertEqual(status, 200, body)
        return body

    def test_named_people_people_by_attribute_and_people_found_through_a_relation_are_told_of_an_approved_change_and_the_approver_is_not(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.ready(team)
            ids = {u: self.user_id(admin, u) for u in ('ann', 'bob', 'vera', 'root')}
            self.assertEqual(admin.post('/api/users/update', {'id': ids['root'], 'attrs': {'负责客户': 'KH001'}})[0], 200)
            self.assertEqual(admin.post('/api/users/update', {'id': ids['bob'], 'attrs': {'城市': ITS_CITY}})[0], 200)
            self.assertEqual(admin.post('/api/users/update', {'id': ids['ann'], 'attrs': {'城市': ITS_CITY}})[0], 200)
            recipients = [{'kind': 'people', 'user_ids': [ids['vera']]}, {'kind': 'attr', 'column': '客户编号', 'user_attr': '负责客户'},
                          {'kind': 'via', 'relation': 'order_customer', 'column': '城市', 'user_attr': '城市'}]
            self.assertEqual(vera.post('/api/workspace/actions/notify', {'action': ACTION['name'], 'recipients': recipients})[0], 403)   # a builder's
            status, body = ann.post('/api/workspace/actions/notify', {'action': ACTION['name'], 'recipients': recipients})
            self.assertEqual(status, 200, body)
            said = ann.get(ACTION_URL)[1]['notify']
            self.assertEqual(said['recipients'], recipients)
            self.assertEqual(said['lines'], ['Vera', '客户编号 = 自己的负责客户 的人', '经关系“订单属于客户”，客户的 城市 = 自己的城市 的人'])
            self.change(bob, ann)
            for person in (vera, admin, bob):
                body = self.notices(person)
                self.assertEqual(body['unread'], 1)
                notice = body['notices'][0]
                self.assertIn(THE_ORDER['订单号'], notice['text'])
                self.assertIn('45', notice['text'])
                self.assertEqual((notice['action'], notice['read']), ('改交付天数', False))
            self.assertEqual(self.notices(ann)['unread'], 0)   # she approved it
            notice = self.notices(vera)['notices'][0]
            self.assertEqual(vera.post('/api/workspace/notices/read', {'ids': [notice['id']]})[0], 200)
            self.assertEqual(self.notices(vera)['unread'], 0)
            self.assertEqual(vera.post('/api/workspace/notices/read', {'ids': [self.notices(admin)['notices'][0]['id']]})[0], 200)   # another's: nothing happens to it
            self.assertEqual(self.notices(admin)['unread'], 1)
            self.assertEqual(admin.post('/api/workspace/notices/read', {'all': True})[0], 200)
            self.assertEqual(self.notices(admin)['unread'], 0)
            # a row rule keeps KH001 from Vera: the next change on it is not told to her
            rule = [{'column': '客户编号', 'value': 'KH002', 'user_ids': [ids['vera']]}, {'user_ids': [ids['ann'], ids['bob']]}]
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rule})[0], 200)
            self.change(bob, ann, days='50')
            self.assertEqual(len(self.notices(vera)['notices']), 1)
            self.assertEqual(len(self.notices(admin)['notices']), 2)
            conn_log = [e for e in ann.get(ACTION_URL)[1]['log'] if e['change'] == 'notify_changed']
            self.assertEqual(len(conn_log), 1)

    def test_recipients_are_checked(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, admin = team['ann'], team['admin']
            self.ready(team)
            vera = self.user_id(admin, 'vera')
            for bad in ([{'kind': 'nobody'}], [{'kind': 'people', 'user_ids': []}], [{'kind': 'people', 'user_ids': [99999]}],
                        [{'kind': 'attr', 'column': '不存在', 'user_attr': '部门'}], [{'kind': 'attr', 'column': '客户编号', 'user_attr': ''}],
                        [{'kind': 'via', 'relation': 'nothing', 'column': '城市', 'user_attr': '城市'}],
                        [{'kind': 'via', 'relation': 'order_customer', 'column': '不存在', 'user_attr': '城市'}],
                        [{'kind': 'people', 'user_ids': [vera]}] * 6, 'x'):
                status, body = ann.post('/api/workspace/actions/notify', {'action': ACTION['name'], 'recipients': bad})
                self.assertEqual(status, 400, (bad, body))
            self.assertEqual(ann.post('/api/workspace/actions/notify', {'action': '不存在', 'recipients': []})[0], 404)
            self.assertEqual(ann.post('/api/workspace/actions/notify', {'action': ACTION['name'], 'recipients': []})[0], 200)   # nobody: the default
            self.assertEqual(self.notices(ann), {'notices': [], 'unread': 0})
