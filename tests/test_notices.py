"""Notices: an action names who hears when one of its changes is approved: named people, the people whose attribute equals a column of the row, or the people whose
attribute equals a column of the object the row points to through a relation. A notice goes only to someone who may read that row; the approver is not told."""
import re
from unittest import mock
from urllib.parse import quote

from tests.test_derived_properties import CANCELLED, ORDER, RELATIONS, DerivedTestCase
from tests.test_object_relations import CUSTOMER, customers_mended, table_csv
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

    def test_one_upload_that_moves_several_definitions_on_two_datasets_tells_each_person_once_with_the_count_of_the_rest(self):
        order2 = {'english_name': 'order2', 'name': '订单副表', 'dataset': '订单', 'key': ['订单号'], 'properties': [{'column': '订单号'}, {'column': '金额'}]}
        with self.service() as (base, out):
            team = self.team(base)
            bob, admin = team['bob'], team['admin']
            self.foundation(team, types=(ORDER, order2, CUSTOMER), relations=[])   # Ann puts forward, Bob confirms
            first = ORDERS[0]['订单号']
            mended = [r for i, r in enumerate(CUSTOMERS) if r['客户编号'] not in {c['客户编号'] for c in CUSTOMERS[:i]}]
            repeated_orders = orders_upload(lambda r, i: {**r, '订单号': first} if i == 1 else r)
            repeated_customers = table_csv('客户.csv', [*mended, mended[0]], target='客户', mode='overwrite')
            status, body = team['ann'].post('/api/workspace/datasets/upload', {'files': [repeated_orders, repeated_customers]})   # one upload, two files, three types go back
            self.assertEqual(status, 200, body)
            conn = self.db(out)
            moved = conn.execute("SELECT element_id FROM element_state WHERE state = 'needs_look' ORDER BY element_id").fetchall()
            conn.close()
            self.assertEqual(moved, [('objtype:customer',), ('objtype:order',), ('objtype:order2',)])
            for person in (bob, admin):
                told = self.notices(person)['notices']
                self.assertEqual(len(told), 1, [n['text'] for n in told])   # one upload, one notice
                self.assertIn('还有 2 项', told[0]['text'])

    def broken_notices(self):
        return mock.patch('ontology_poc_generator.notices.tell_moved', side_effect=RuntimeError('the notice table is broken'))

    def test_a_notice_that_cannot_be_written_never_loses_the_move_of_an_upload(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])
            with self.broken_notices():
                status, body = team['ann'].post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})
                self.assertEqual(status, 200, body)
                self.assertIsNone(body['results'][0]['recheck_error'])
            self.assertEqual(set(self.states(out).values()), {'needs_look'})   # the meanings, the type and the relation went back all the same
            self.assertEqual(self.notices(team['bob']), {'notices': [], 'unread': 0})

    def test_a_notice_that_cannot_be_written_never_rolls_back_an_edit(self):
        with self.service() as (base, out):
            team = self.team(base)
            cara = team['cara']
            self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])
            shown = cara.get('/api/workspace/types/order')[1]
            edited = {**ORDER, 'id': 'order', 'version': shown['version'], 'properties': [p for p in ORDER['properties'] if p['column'] != '交付天数']}
            with self.broken_notices():
                status, body = cara.post('/api/workspace/types/update', edited)
                self.assertEqual(status, 200, body)
            states = self.states(out)
            self.assertEqual((states['objtype:order'], states['relation:order_customer']), ('checked', 'needs_look'))   # the edit stands, and the relation went back
            self.assertNotIn('交付天数', [p['column'] for p in cara.get('/api/workspace/types/order')[1]['properties']])


ORDER_COUNT = {'type': 'customer', 'english_name': 'order_count', 'name': '订单数', 'kind': 'statistic', 'path': ['order_customer'], 'measure': {'column': None}, 'fn': 'count'}
ORDER2 = {**ORDER, 'english_name': 'order2', 'name': '订单副表'}   # a second type on 订单, with its own meanings of 状态码
SET_CODE = {'name': '改状态码', 'type': 'order', 'properties': ['状态码'], 'description': '订单的状态改了'}
CANCELLED_ORDERS = [r for r in ORDERS if r['状态码'] == '2']
PIPELINES = '/api/workspace/pipelines'
TOTAL_ROWS_TYPE = {'english_name': 'customer_rows', 'name': '客户行数', 'dataset': '客户合计', 'key': ['客户编号'], 'properties': [{'column': '行数'}]}
TWO_COPIES = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'},
                        {'id': 'a', 'type': 'output', 'from': 'o', 'name': '订单甲', 'key': {'columns': ['订单号']}},
                        {'id': 'b', 'type': 'output', 'from': 'o', 'name': '订单乙', 'key': {'columns': ['订单号']}}]}
COPY_A = {**ORDER, 'english_name': 'order_a', 'name': '订单甲', 'dataset': '订单甲'}
COPY_B = {**ORDER, 'english_name': 'order_b', 'name': '订单乙', 'dataset': '订单乙'}
MORE = re.compile(r'还有 (\d+) 项')


class ToldOncePerMoveTests(DerivedTestCase):
    """The other ways a confirmed definition goes back, each one operation: a relation edit, a pipeline edit, an approved action's write, a pipeline run with two
    outputs. Each person who can confirm what moved (or confirmed it last) and may see it gets one notice for the operation, counting the rest they may see; a notice
    that cannot be written never loses the move nor stops the answer. Who may see is checked three times over (who is asked, who is told, who reads it): what each
    person was told is read from the notice table as well as from their list, so a check that fails is not hidden by the next one."""

    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'cara', 'dan', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': TABLES})[0], 200)
        self.assertEqual(team['ann'].post('/api/workspace/datasets/upload', {'files': [customers_mended()]})[0], 200)
        return team

    def ids(self, admin):
        return {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}

    def notices(self, client):
        status, body = client.get('/api/workspace/notices')
        self.assertEqual(status, 200, body)
        return body['notices']

    def written(self, out, user_id):
        """What the notice table holds for this person about definitions that went back (the definition each one names), oldest first: not filtered as it is read."""
        conn = self.db(out)
        try:
            return [a for (a,) in conn.execute('SELECT action_name FROM notice WHERE user_id = ? AND record_id IS NULL ORDER BY id', (user_id,))]
        finally:
            conn.close()

    def all_written(self, out):
        conn = self.db(out)
        try:
            return conn.execute('SELECT COUNT(*) FROM notice WHERE record_id IS NULL').fetchone()[0]
        finally:
            conn.close()

    def states(self, out, *element_ids):
        conn = self.db(out)
        try:
            return {e: (conn.execute('SELECT state FROM element_state WHERE element_id = ?', (e,)).fetchone() or [None])[0] for e in element_ids}
        finally:
            conn.close()

    def asked(self, out, element_id):
        """The ids of the people who may confirm this definition now (confirmer_people)."""
        from ontology_poc_generator.object_types import confirmer_people, element_row
        from ontology_poc_generator.workspace_store import open_workspace
        conn = open_workspace(out / 'workspace.sqlite')
        try:
            return {person for person, _ in confirmer_people(conn, element_row(conn, element_id))}
        finally:
            conn.close()

    def says_more(self, notice, more):
        """The notice counts exactly `more` others this person may see (0: it gives no count at all)."""
        found = MORE.findall(notice['text'])
        self.assertEqual(found, [str(more)] if more else [], notice['text'])

    def told_once(self, client, kinds, more):
        """One notice, about one of the definitions that moved, saying exactly how many more this person may see went back."""
        told = self.notices(client)
        self.assertEqual(len(told), 1, [n['text'] for n in told])
        notice = told[0]
        self.assertIn(notice['definition']['kind'], kinds)
        self.assertEqual(notice['definition']['state'], 'needs_look')
        self.says_more(notice, more)
        return notice

    def broken_notices(self):
        """Writing notices fails after the first one is written: the half-written set must go, and the move must stay."""
        from ontology_poc_generator import notices
        real, calls = notices.now_text, []

        def second_fails():
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError('the notice table is broken')
            return real()
        return mock.patch.object(notices, 'now_text', side_effect=second_fails)

    # --- a relation edit ------------------------------------------------------------------------------------------------------------------------------

    def relation_read_twice(self, team):
        """order_customer confirmed, and two derived properties on 客户 that read it, put forward by Ann and confirmed by Bob."""
        ann, bob = team['ann'], team['bob']
        self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])
        for derived in (CANCELLED, ORDER_COUNT):
            status, body = ann.post('/api/workspace/types/derived', derived)
            self.assertEqual(status, 200, body)
            status, body = self.confirm(bob, derived)
            self.assertEqual(status, 200, body)

    def edit_relation(self, client):
        detail = client.get('/api/workspace/relations/order_customer')[1]
        edited = {**next(r for r in RELATIONS if r['english_name'] == 'order_customer'), 'id': 'order_customer', 'version': detail['version'], 'cardinality': 'one_to_one'}
        return client.post('/api/workspace/relations/update', edited)

    RELATION_AND_READERS = ('relation:order_customer', 'derived:customer:cancelled_orders', 'derived:customer:order_count')

    def test_a_relation_edit_that_sends_two_confirmed_readers_back_tells_each_person_once_with_the_count(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, cara, dan, vera, admin = (team[k] for k in ('ann', 'bob', 'cara', 'dan', 'vera', 'admin'))
            self.relation_read_twice(team)
            ids = self.ids(admin)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['ann'], ids['bob'], ids['cara']]})[0], 200)   # 客户 kept from Dan
            moved_before = self.states(out, *self.RELATION_AND_READERS)
            self.assertEqual(set(moved_before.values()), {'confirmed'}, moved_before)
            status, body = self.edit_relation(cara)
            self.assertEqual(status, 200, body)
            self.assertTrue(body['reset'], body)
            states = self.states(out, *self.RELATION_AND_READERS)
            self.assertEqual(list(states.values()), ['checked', 'needs_look', 'needs_look'], states)   # the relation is Cara's to have confirmed again; what reads it went back
            for person in (bob, admin, cara):   # who confirmed it last; an admin; the editor, who did not put the properties forward
                notice = self.told_once(person, ('derived',), 1)
                self.assertIn('定义改了', notice['text'])
            for person in (ann, dan, vera):   # the proposer; a builder 客户 is kept from; a viewer
                self.assertEqual(self.notices(person), [])
            for name in ('ann', 'dan', 'vera'):
                self.assertEqual(self.written(out, ids[name]), [], name)

    def test_a_relation_edit_whose_notices_cannot_all_be_written_still_sends_its_readers_back_and_answers(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.relation_read_twice(team)
            with self.broken_notices():
                status, body = self.edit_relation(team['cara'])
            self.assertEqual(status, 200, body)
            self.assertEqual(list(self.states(out, *self.RELATION_AND_READERS).values()), ['checked', 'needs_look', 'needs_look'])
            self.assertEqual(self.all_written(out), 0)   # the one written before the failure went with the rest
            self.assertEqual(team['cara'].get('/api/workspace/relations/order_customer')[1]['cardinality'], 'one_to_one')

    # --- a pipeline edit ------------------------------------------------------------------------------------------------------------------------------

    def pipeline_read_twice(self, team):
        """The 客户合计 pipeline, written and run by Ann and confirmed by Bob, and two types on its output, put forward by Ann and confirmed by Bob."""
        from tests.test_pipeline_server import SPEC, TOTAL_TYPE
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post(PIPELINES, {'name': '客户合计', 'description': '每个客户的订单金额合计', 'spec': SPEC})[0], 200)
        status, body = ann.post(f'{PIPELINES}/run', {'id': '客户合计'})
        self.assertEqual((status, body.get('status')), (200, 'success'), body)
        shown = bob.get(f'{PIPELINES}/{quote("客户合计")}')[1]
        status, body = bob.post(f'{PIPELINES}/confirm', {'id': '客户合计', 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
        self.assertEqual(status, 200, body)
        for t in (TOTAL_TYPE, TOTAL_ROWS_TYPE):
            self.assertEqual(ann.post('/api/workspace/types', t)[0], 200, t['english_name'])
            self.confirm_type(bob, t['english_name'])

    def edit_pipeline(self, client):
        from tests.test_pipeline_server import SPEC
        now = client.get(f'{PIPELINES}/{quote("客户合计")}')[1]
        inner = {'steps': [{**s, 'how': 'inner'} if s['id'] == 'j' else s for s in SPEC['steps']]}
        return client.post(f'{PIPELINES}/update', {'id': '客户合计', 'version': now['version'], 'spec': inner})

    PIPELINE_AND_READERS = ('pipeline:客户合计', 'objtype:customer_total', 'objtype:customer_rows')

    def test_a_pipeline_edit_that_sends_two_confirmed_types_back_tells_each_person_once_with_the_count_they_may_see(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, cara, dan, vera, admin = (team[k] for k in ('ann', 'bob', 'cara', 'dan', 'vera', 'admin'))
            self.pipeline_read_twice(team)
            ids = self.ids(admin)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer_total', 'visible_to': [ids['ann'], ids['bob'], ids['cara']]})[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer_rows', 'visible_to': [ids['ann'], ids['bob']]})[0], 200)   # Cara sees one of the two, Dan neither
            self.assertEqual(set(self.states(out, *self.PIPELINE_AND_READERS).values()), {'confirmed'})
            status, body = self.edit_pipeline(bob)   # a type on the output kept from Cara and Dan keeps the output from them: theirs neither to write nor to edit
            self.assertEqual((status, body.get('changed')), (200, True), body)
            states = self.states(out, *self.PIPELINE_AND_READERS)
            self.assertEqual(list(states.values()), ['checked', 'needs_look', 'needs_look'], states)
            self.assertEqual(self.asked(out, 'objtype:customer_rows'), {ids['bob'], ids['root']})   # who may confirm it: not its proposer, nor anyone it is kept from
            self.assertEqual(self.asked(out, 'objtype:customer_total'), {ids['bob'], ids['cara'], ids['root']})
            for person in (bob, admin):   # the editor, who confirmed both types last; an admin
                self.told_once(person, ('type',), 1)
            notice = self.told_once(cara, ('type',), 0)   # she may see one of the two: told of it, and of no other
            self.assertEqual(notice['definition']['id'], 'customer_total')
            self.assertNotIn('客户行数', notice['text'])
            self.assertEqual(self.written(out, ids['cara']), ['objtype:customer_total'])
            for name in ('ann', 'dan', 'vera'):   # the types' proposer; a builder kept from both; a viewer: nothing is even written for them
                self.assertEqual(self.written(out, ids[name]), [], name)
                self.assertEqual(self.notices(team[name]), [], name)

    def test_a_pipeline_edit_whose_notices_cannot_all_be_written_still_sends_the_types_back_and_answers(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.pipeline_read_twice(team)
            with self.broken_notices():
                status, body = self.edit_pipeline(team['dan'])
            self.assertEqual((status, body.get('changed'), body.get('definition_version')), (200, True, 2), body)
            self.assertEqual(list(self.states(out, *self.PIPELINE_AND_READERS).values()), ['checked', 'needs_look', 'needs_look'])
            self.assertEqual(self.all_written(out), 0)

    # --- an approved action ---------------------------------------------------------------------------------------------------------------------------

    def code_action(self, team):
        """订单 with two types that each confirmed the meanings of 状态码 (two roots), order_customer and a derived property on it; the action 改状态码. All put forward
        by Ann and confirmed by Bob."""
        ann, bob = team['ann'], team['bob']
        self.foundation(team, types=(ORDER, CUSTOMER), relations=[r for r in RELATIONS if r['english_name'] == 'order_customer'])
        self.assertEqual(ann.post('/api/workspace/types', ORDER2)[0], 200)
        self.confirm_type(bob, 'order2', ('状态码',))
        self.assertEqual(ann.post('/api/workspace/types/derived', ORDER_COUNT)[0], 200)
        self.assertEqual(self.confirm(bob, ORDER_COUNT)[0], 200)
        self.assertEqual(ann.post('/api/workspace/actions', SET_CODE)[0], 200)
        shown = bob.get('/api/workspace/actions/' + quote(SET_CODE['name']))[1]
        status, body = bob.post('/api/workspace/actions/confirm', {'id': SET_CODE['name'], 'version': shown['version']})
        self.assertEqual(status, 200, body)

    def approve(self, submitter, approver, order):
        status, body = submitter.post('/api/workspace/actions/submit', {'action': SET_CODE['name'], 'key': {'订单号': order['订单号']}, 'params': {'状态码': '0'}, 'reason': '其实交付了'})
        self.assertEqual(status, 200, body)
        return approver.post('/api/workspace/actions/decide', {'id': body['record'], 'decision': 'approve'})

    def approve_all_but_the_last(self, submitter, approver):
        """Every cancelled order but one is set to 0, one approval each: the code 2 is still there, so nothing moves."""
        self.assertGreater(len(CANCELLED_ORDERS), 1)
        for order in CANCELLED_ORDERS[:-1]:
            status, body = self.approve(submitter, approver, order)
            self.assertEqual((status, body.get('state')), (200, 'approved'), body)

    MOVED_BY_CODE = ('enum:order:状态码', 'objtype:order', 'enum:order2:状态码', 'objtype:order2', 'relation:order_customer', 'derived:customer:order_count',
                     'objaction:改状态码')

    def test_an_approved_action_whose_write_sends_two_confirmed_meanings_back_with_what_stands_on_them_tells_each_person_once_with_the_count(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, cara, dan, vera, admin = (team[k] for k in ('ann', 'bob', 'cara', 'dan', 'vera', 'admin'))
            self.code_action(team)
            ids = self.ids(admin)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['ann'], ids['bob'], ids['cara']]})[0], 200)   # 客户 kept from Dan
            self.approve_all_but_the_last(ann, cara)
            self.assertEqual(set(self.states(out, *self.MOVED_BY_CODE).values()), {'confirmed'})
            self.assertEqual(self.all_written(out), 0)
            status, body = self.approve(ann, cara, CANCELLED_ORDERS[-1])   # the last 2 goes: both sets of meanings go back, each with its type, and what stands on 订单 (the relation, the count, the action)
            self.assertEqual((status, body.get('state'), body.get('recheck_error')), (200, 'approved', None), body)
            self.assertEqual(set(self.states(out, *self.MOVED_BY_CODE).values()), {'needs_look'})
            for person in (bob, admin, cara):   # who confirmed all seven last; an admin; the approver, who may confirm all seven
                notice = self.told_once(person, ('meaning', 'type', 'relation', 'derived', 'action'), 6)
                self.assertIn('数据变了', notice['text'])
            notice = self.told_once(dan, ('meaning', 'type', 'action'), 4)   # 客户 kept from him: the meanings, the types and the action, not the relation nor the count on 客户
            self.assertNotIn('订单属于客户', notice['text'])
            self.assertEqual(len(self.written(out, ids['dan'])), 1)
            for name in ('ann', 'vera'):   # the proposer and submitter; a viewer
                self.assertEqual(self.notices(team[name]), [], name)
                self.assertEqual(self.written(out, ids[name]), [], name)

    def test_an_approved_action_whose_notices_cannot_all_be_written_still_moves_what_it_sent_back_and_answers(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.code_action(team)
            self.approve_all_but_the_last(team['ann'], team['cara'])
            with self.broken_notices():
                status, body = self.approve(team['ann'], team['cara'], CANCELLED_ORDERS[-1])
            self.assertEqual((status, body.get('state'), body.get('recheck_error')), (200, 'approved', None), body)
            self.assertEqual(set(self.states(out, *self.MOVED_BY_CODE).values()), {'needs_look'})
            self.assertEqual(self.all_written(out), 0)

    # --- a pipeline run with two outputs --------------------------------------------------------------------------------------------------------------

    def two_outputs_read(self, team):
        """A pipeline that copies 订单 to 订单甲 and 订单乙, run and confirmed, and a type with its 状态码 meanings on each copy, confirmed; then 订单 is uploaded with
        its codes shifted, and Bob confirms the pipeline and the two types again on it. The next run is what moves the copies' definitions."""
        ann, bob = team['ann'], team['bob']
        self.assertEqual(ann.post(PIPELINES, {'name': '两份副本', 'description': '订单抄两份', 'spec': TWO_COPIES})[0], 200)
        status, body = ann.post(f'{PIPELINES}/run', {'id': '两份副本'})
        self.assertEqual((status, body.get('status')), (200, 'success'), body)
        self.confirm_pipeline(bob)
        for t in (COPY_A, COPY_B):
            self.assertEqual(ann.post('/api/workspace/types', t)[0], 200, t['english_name'])
            self.confirm_type(bob, t['english_name'], ('状态码',))
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)   # the pipeline goes back, and the types that stand on it
        self.confirm_pipeline(bob)
        for t in (COPY_A, COPY_B):
            self.confirm_type(bob, t['english_name'])

    def confirm_pipeline(self, bob):
        shown = bob.get(f'{PIPELINES}/{quote("两份副本")}')[1]
        status, body = bob.post(f'{PIPELINES}/confirm', {'id': '两份副本', 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
        self.assertEqual(status, 200, body)

    COPIES = ('enum:order_a:状态码', 'objtype:order_a', 'enum:order_b:状态码', 'objtype:order_b')

    def test_a_pipeline_run_whose_two_outputs_each_send_confirmed_definitions_back_tells_each_person_once_for_the_run(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, cara, dan, vera, admin = (team[k] for k in ('ann', 'bob', 'cara', 'dan', 'vera', 'admin'))
            self.two_outputs_read(team)
            ids = self.ids(admin)
            # the first copy is Ann's only now, so kept from Bob, who confirmed it last; the second from Dan. What moves first in the run is the first copy's
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order_a', 'visible_to': [ids['ann']]})[0], 200)
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order_b', 'visible_to': [ids['ann'], ids['bob'], ids['cara']]})[0], 200)
            self.assertEqual(set(self.states(out, *self.COPIES).values()), {'confirmed'})
            before = {name: len(self.written(out, ids[name])) for name in ('ann', 'bob', 'cara', 'dan', 'vera', 'root')}
            status, run = ann.post(f'{PIPELINES}/run', {'id': '两份副本'})
            self.assertEqual((status, run.get('status')), (200, 'success'), run)
            self.assertEqual([(w['dataset'], w['recheck_error']) for w in run['outputs']], [('订单甲', None), ('订单乙', None)])
            self.assertEqual(set(self.states(out, *self.COPIES).values()), {'needs_look'})   # both meanings and both types, on two outputs
            self.assertEqual(self.asked(out, 'enum:order_a:状态码'), {ids['root']})   # who may confirm the first copy's meanings: only the admin
            self.assertEqual(self.asked(out, 'enum:order_b:状态码'), {ids['bob'], ids['cara'], ids['root']})
            fresh = {name: self.written(out, ids[name])[n:] for name, n in before.items()}
            self.assertEqual(len(fresh['root']), 1)   # one notice for the run, not one per output
            self.assertEqual(fresh['bob'], ['enum:order_b:状态码'])   # he confirmed the first copy last, but may not see it now: told of the second only
            self.assertEqual(fresh['cara'], ['enum:order_b:状态码'])
            for name in ('ann', 'dan', 'vera'):   # the proposer; a builder kept from both copies; a viewer
                self.assertEqual(fresh[name], [], name)
            listed = {name: self.notices(team[name] if name != 'root' else admin) for name in ('bob', 'cara', 'root')}
            self.says_more(listed['root'][0], 3)
            for name in ('bob', 'cara'):
                self.assertEqual(listed[name][0]['definition']['id'], 'order_b')
                self.says_more(listed[name][0], 1)
                self.assertNotIn('订单甲', listed[name][0]['text'])
            # the second copy kept from Cara since: her notice is no longer hers to read, though it is still in the table
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'order_b', 'visible_to': [ids['ann'], ids['bob']]})[0], 200)
            self.assertNotIn('order_b', [n['definition']['id'] for n in self.notices(cara)])
            self.assertIn('enum:order_b:状态码', self.written(out, ids['cara']))
            self.assertEqual(len(self.notices(bob)), len(listed['bob']))

    def test_a_pipeline_run_whose_notices_cannot_all_be_written_still_writes_both_outputs_moves_their_readers_and_answers(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.two_outputs_read(team)
            before = self.all_written(out)
            with self.broken_notices():
                status, run = team['ann'].post(f'{PIPELINES}/run', {'id': '两份副本'})
            self.assertEqual((status, run.get('status')), (200, 'success'), run)
            self.assertEqual([(w['dataset'], w['recheck_error']) for w in run['outputs']], [('订单甲', None), ('订单乙', None)])
            self.assertEqual(set(self.states(out, *self.COPIES).values()), {'needs_look'})
            self.assertEqual(self.all_written(out), before)
