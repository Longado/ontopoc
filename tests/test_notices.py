"""Notices: an action names who hears when one of its changes is approved: named people, the people whose attribute equals a column of the row, or the people whose
attribute equals a column of the object the row points to through a relation. A notice goes only to someone who may read that row; the approver is not told."""
from urllib.parse import quote

from tests.test_derived_properties import ORDER, RELATIONS, DerivedTestCase
from tests.test_object_relations import CUSTOMER, customers_mended
from tests.test_object_types import TABLES, orders_upload, shifted_orders_csv
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
            self.assertEqual(self.notices(vera)['notices'], [])   # not told of the new one, and the old one about that row is no longer hers to read
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

    def test_a_notice_is_checked_again_when_it_is_read_and_a_broken_recipient_does_not_stop_the_change(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            self.ready(team)
            vera_id = self.user_id(admin, 'vera')
            recipients = [{'kind': 'people', 'user_ids': [vera_id]}, {'kind': 'via', 'relation': 'order_customer', 'column': '城市', 'user_attr': '城市'}]
            self.assertEqual(ann.post('/api/workspace/actions/notify', {'action': ACTION['name'], 'recipients': recipients})[0], 200)
            conn = __import__('ontology_poc_generator.workspace_store', fromlist=['open_workspace']).open_workspace(out / 'workspace.sqlite')
            conn.execute("UPDATE element_state SET content_json = json_set(content_json, '$.from', 'gone') WHERE element_id = 'relation:order_customer'")   # a relation that no longer fits
            conn.commit()
            conn.close()
            self.change(bob, ann)   # still approved
            self.assertEqual(self.notices(vera)['unread'], 1)
            self.assertEqual(admin.post('/api/workspace/column-access', {'type': 'order', 'column': '交付天数', 'visible_to': [self.user_id(admin, 'ann')]})[0], 200)
            self.assertEqual(self.notices(vera), {'notices': [], 'unread': 0})   # the column it quotes is kept from her now


class BackForAnotherLookTests(DerivedTestCase):
    """New data sends a confirmed definition back to "needs another look": the people who can confirm it and the person who confirmed it last are each told once,
    in Messages, which definition and why, with a link to it. Someone who may not see it is told nothing, and learns no name or count of it."""

    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'cara', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
        return team

    def ids(self, admin):
        return {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}

    def notices(self, client, **more):
        status, body = client.get('/api/workspace/notices', **more)
        self.assertEqual(status, 200, body)
        return body

    def upload(self, client, part):
        status, body = client.post('/api/workspace/datasets/upload', {'files': [part]})
        self.assertEqual(status, 200, body)

    def states(self, out):
        conn = self.db(out)
        try:
            return dict(conn.execute("SELECT element_id, state FROM element_state WHERE element_id IN ('enum:order:状态码', 'objtype:order', 'relation:order_customer')"))
        finally:
            conn.close()

    def test_an_upload_that_sends_a_confirmed_definition_back_tells_each_person_who_can_confirm_it_once_and_nobody_else(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, cara, vera, admin = team['ann'], team['bob'], team['cara'], team['vera'], team['admin']
            self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])   # Ann puts forward, Bob confirms
            ids = self.ids(admin)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [ids['ann'], ids['bob']]})[0], 200)   # Cara may not see 订单
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['ann']]})[0], 200)   # nor Bob 客户, so nor the relation
            for person in team.values():
                self.assertEqual(self.notices(person), {'notices': [], 'unread': 0})
            self.upload(ann, shifted_orders_csv())   # the codes shift: the meanings go back, and the type and the relation that stand on them
            self.assertEqual(set(self.states(out).values()), {'needs_look'})
            told = self.notices(bob)
            self.assertEqual((told['unread'], len(told['notices'])), (1, 1))   # one notice for the one move, not one per definition it carried
            notice = told['notices'][0]
            self.assertEqual((notice['action'], notice['read'], notice['definition']['kind'], notice['definition']['id'], notice['definition']['state']),
                             (None, False, 'meaning', 'order', 'needs_look'))
            for words in ('订单', '状态码', '数据变了', '新出现 3', '还有 1 项'):   # which definition, the cause, and the type that went back with it
                self.assertIn(words, notice['text'])
            self.assertNotIn('订单属于客户', notice['text'])   # the relation is not Bob's to see: not named, not counted
            self.assertNotIn('客户', notice['text'])
            seen_all = self.notices(admin)['notices']
            self.assertEqual(len(seen_all), 1)
            self.assertIn('还有 2 项', seen_all[0]['text'])   # an admin sees the relation too
            for person in (ann, cara, vera):   # the proposer; a builder the type is kept from; a viewer
                self.assertEqual(self.notices(person), {'notices': [], 'unread': 0})
            self.upload(ann, shifted_orders_csv())   # the same data again: nothing moves, nobody is told again
            self.assertEqual(len(self.notices(bob)['notices']), 1)
            self.assertEqual(len(self.notices(admin)['notices']), 1)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order', 'visible_to': [ids['ann']]})[0], 200)
            self.assertEqual(self.notices(bob), {'notices': [], 'unread': 0})   # taken off the list since: the notice goes with it

    def test_the_proposer_who_confirmed_their_own_is_told_but_not_offered_to_confirm_and_a_builder_a_row_rule_limits_is_not_told(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, cara, admin = team['ann'], team['bob'], team['cara'], team['admin']
            self.assertEqual(admin.post('/api/settings', {'two_person': False})[0], 200)
            self.assertEqual(ann.post('/api/workspace/types', ORDER)[0], 200)
            self.confirm_type(ann, 'order', ('状态码',))   # her own, while the rule was off
            self.assertEqual(admin.post('/api/settings', {'two_person': True})[1]['two_person']['active'], True)
            ids = self.ids(admin)
            rule = [{'column': '客户编号', 'value': 'KH002', 'user_ids': [ids['cara']]}, {'user_ids': [ids['ann'], ids['bob']]}]
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rule})[0], 200)   # Cara sees some rows only
            first = ORDERS[0]['订单号']
            self.upload(bob, orders_upload(lambda r, i: {**r, '订单号': first} if i == 1 else r))   # a repeated key: the type itself goes back
            self.assertEqual(self.states(out)['objtype:order'], 'needs_look')
            notice = self.notices(bob, headers={'Accept-Language': 'en'})['notices'][0]
            self.assertEqual((notice['definition']['kind'], notice['definition']['id'], notice['definition']['can_confirm']), ('type', 'order', True))
            self.assertIn('Data changed', notice['text'])
            self.assertIn('needs another look', notice['text'])
            own = self.notices(ann)['notices']
            self.assertEqual(len(own), 1)   # she confirmed it last, so she is told it went back
            self.assertEqual(own[0]['definition']['can_confirm'], False)   # but not offered to confirm her own
            self.assertEqual(self.notices(cara), {'notices': [], 'unread': 0})   # a row rule keeps her from all the data: she cannot confirm it
            self.assertEqual(len(self.notices(admin)['notices']), 1)

    def test_an_edit_that_sends_a_reader_back_tells_who_can_confirm_the_reader_with_the_cause_definition_changed(self):
        with self.service() as (base, out):
            team = self.people(base, 'ann', 'bob', 'cara', 'dan')
            ann, bob, cara, dan, admin = team['ann'], team['bob'], team['cara'], team['dan'], team['admin']
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
            self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])   # Ann puts forward, Bob confirms
            ids = self.ids(admin)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['ann'], ids['bob'], ids['cara']]})[0], 200)   # the relation is kept from Dan
            shown = cara.get('/api/workspace/types/order')[1]
            edited = {**ORDER, 'id': 'order', 'version': shown['version'], 'properties': [p for p in ORDER['properties'] if p['column'] != '交付天数']}
            status, body = cara.post('/api/workspace/types/update', edited)   # Cara drops a property: the type is hers to have confirmed again, the relation on it goes back
            self.assertEqual(status, 200, body)
            self.assertTrue(body['reset'], body)
            self.assertEqual(self.states(out)['relation:order_customer'], 'needs_look')
            for person in (bob, admin):
                told = self.notices(person)
                self.assertEqual((told['unread'], len(told['notices'])), (1, 1))
                notice = told['notices'][0]
                self.assertEqual((notice['definition']['kind'], notice['definition']['id'], notice['definition']['state']), ('relation', 'order_customer', 'needs_look'))
                for words in ('订单属于客户', '定义改了', '它连接的“订单”类型改了'):
                    self.assertIn(words, notice['text'])
            own = self.notices(cara)['notices']   # the editor can confirm the relation (she did not put it forward), so she is told too
            self.assertEqual(len(own), 1)
            self.assertEqual((own[0]['definition']['id'], own[0]['definition']['can_confirm']), ('order_customer', True))
            for person in (ann, dan):   # the relation's proposer; a builder the relation is kept from
                self.assertEqual(self.notices(person), {'notices': [], 'unread': 0})
