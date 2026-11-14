"""Dashboards, walked through the real service with two builders, a viewer and an admin on the planted tables. Acceptance of stage 6: the 有效订单 card reads
"剔除 状态码 = 2（已取消），Bob 确认于 订单 v1" and turns grey with the reason after a shifted upload. Also who may open a board (private, named people, everyone,
expired), that a share link still needs a sign-in, that every reader gets numbers over what *they* may read, and the filter bar."""
from datetime import date, timedelta
import sqlite3

from tests.test_access import Client
from tests.test_explorer import LIVE, ORDERS, UseLayerCase
from tests.test_object_types import shifted_orders_csv

CARD = {'id': 'valid', 'title': '有效订单', 'query': {'type': 'order', 'view': '有效订单'}, 'chart': {'kind': 'number'}}
BY_STATUS = {'id': 'status', 'title': '按状态', 'query': {'type': 'order'}, 'chart': {'kind': 'bar', 'group': '状态码', 'fn': 'count'}}
CUSTOMERS = {'id': 'cust', 'title': '客户数', 'query': {'type': 'customer'}, 'chart': {'kind': 'number'}}
RECENT = {'id': 'recent', 'title': '最近的订单', 'query': {'type': 'order'}, 'chart': {'kind': 'rows'}}
SPEC = {'components': [CARD, BY_STATUS, CUSTOMERS, RECENT], 'filters': [{'field': '状态码', 'label': '状态'}]}


class BoardCase(UseLayerCase):
    def make(self, client, name='订单看板', spec=SPEC, expect=200, **more):
        status, body = client.post('/api/workspace/dashboards', {'name': name, 'spec': spec, **more})
        self.assertEqual(status, expect, body)
        return body

    def data(self, client, board, bar=None, expect=200):
        status, body = client.post('/api/workspace/dashboards/data', {'id': board, 'bar': bar or {}})
        self.assertEqual(status, expect, body)
        return body

    @staticmethod
    def card(body, ident='valid'):
        return next(c for c in body['components'] if c['id'] == ident)

    def ids(self, admin):
        return {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}


class CaliberTests(BoardCase):
    def test_the_valid_orders_card_reads_its_caliber_from_the_confirmed_definitions_and_turns_grey_with_the_reason_after_a_shifted_upload(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, scope='everyone')
            body = self.data(bob, board['id'])
            card = self.card(body)
            self.assertEqual(card['result']['value'], len(LIVE))
            standing = card['result']['standing']
            self.assertEqual([l['line'] for l in standing['lines']], ['剔除 状态码 = 2（已取消），Bob 确认于 订单 v1'])
            self.assertTrue(standing['confirmed'])
            self.assertEqual((body['headline']['grey'], body['headline']['text']), ([], '全部按已确认的定义算出'))
            self.assertEqual(self.card(body, 'status')['result']['standing']['lines'][0]['line'], '状态码：0 已交付、1 生产中、2 已取消，Bob 确认于 订单 v1')   # a grouped code column cites its meanings
            # a new version of 订单 in which every code is one higher
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            moved = self.data(bob, board['id'])
            grey = self.card(moved)
            self.assertFalse(grey['result']['standing']['confirmed'])
            self.assertIn('订单 第 2 版', grey['result']['standing']['why'])
            self.assertEqual(grey['result']['standing']['lines'][0]['confirmed'], False)
            self.assertIn('需要再看', grey['result']['standing']['lines'][0]['line'])
            self.assertIn('有效订单', moved['headline']['grey'])
            self.assertIn('灰色', moved['headline']['text'])
            self.assertEqual(self.card(moved, 'cust')['result']['standing']['confirmed'], True)   # what does not stand on 订单 is untouched


class ScopeTests(BoardCase):
    def test_a_board_is_opened_by_those_its_scope_names_and_a_share_link_still_needs_a_sign_in(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            ids = self.ids(admin)
            draft = self.make(ann, 'draft')
            self.assertEqual((draft['scope'], draft['visible_to']), ('private', []))
            self.assertEqual([b['name'] for b in bob.get('/api/workspace/dashboards')[1]['dashboards']], [])
            self.assertEqual(bob.get(f'/api/workspace/dashboards/{draft["id"]}')[0], 404)
            self.assertEqual(self.data(bob, draft['id'], expect=404)['error'], '没有这个看板')
            self.assertEqual([b['name'] for b in admin.get('/api/workspace/dashboards')[1]['dashboards']], ['draft'])   # an admin sees every board
            named = self.make(ann, 'named', scope='named', visible_to=[ids['vera']])
            self.assertEqual(named['visible_names'], ['Vera'])
            self.assertEqual(self.card(self.data(vera, named['id']))['status'], 'ok')
            self.assertEqual(bob.get(f'/api/workspace/dashboards/{named["id"]}')[0], 404)
            everyone = self.make(ann, 'everyone', scope='everyone')
            self.assertEqual(sorted(b['name'] for b in vera.get('/api/workspace/dashboards')[1]['dashboards']), ['everyone', 'named'])
            self.assertEqual(bob.get(f'/api/workspace/dashboards/{everyone["id"]}')[0], 200)
            # the link: nobody who is not signed in gets anything
            stranger = Client(base)
            self.assertEqual(stranger.get(f'/api/workspace/dashboards/{everyone["id"]}')[0], 401)
            self.assertEqual(stranger.post('/api/workspace/dashboards/data', {'id': everyone['id']})[0], 401)
            self.assertIn('没有匿名访问', everyone['sign_in_note'])
            # a viewer can open a board and change nothing
            self.assertEqual(vera.post('/api/workspace/dashboards', {'name': 'x', 'spec': SPEC})[0], 403)
            self.assertEqual(vera.post('/api/workspace/dashboards/delete', {'id': everyone['id']})[0], 403)
            self.assertEqual(bob.post('/api/workspace/dashboards/delete', {'id': everyone['id']})[1]['error'], '只有看板的主人或管理员能删它')

    def test_an_expired_board_is_gone_for_everyone_but_its_owner_and_the_admin(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, vera, admin = team['ann'], team['vera'], team['admin']
            soon = (date.today() + timedelta(days=3)).isoformat()
            board = self.make(ann, 'short', scope='everyone', expires_at=soon)
            self.assertEqual(board['expires_at'], soon)
            self.assertEqual(self.make(ann, 'past', scope='everyone', expires_at=(date.today() - timedelta(days=1)).isoformat(), expect=400)['error'], '到期日不能早于今天')
            conn = sqlite3.connect(out / 'workspace.sqlite')
            conn.execute('UPDATE dashboard SET expires_at = ? WHERE id = ?', ((date.today() - timedelta(days=1)).isoformat(), board['id']))
            conn.commit()
            conn.close()
            self.assertEqual(vera.get(f'/api/workspace/dashboards/{board["id"]}')[1]['error'], '这个看板已经过期，不再开放了')
            self.assertEqual(self.data(vera, board['id'], expect=410)['error'], '这个看板已经过期，不再开放了')
            self.assertEqual(vera.get('/api/workspace/dashboards')[1]['dashboards'], [])
            mine = ann.get('/api/workspace/dashboards')[1]['dashboards'][0]
            self.assertEqual((mine['expired'], mine['may_change']), (True, True))
            self.assertTrue(self.data(admin, board['id'])['expired'])

    def test_what_a_board_asks_for_is_checked_when_it_is_saved(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann = team['ann']
            self.assertEqual(self.make(ann, spec={'components': []}, expect=400)['error'], '看板里至少要有一个组件')
            self.assertIn('发布范围', self.make(ann, scope='world', expect=400)['error'])
            self.assertIn('至少一个', self.make(ann, scope='named', visible_to=[], expect=400)['error'])
            self.assertIn('刷新间隔', self.make(ann, refresh_seconds=7, expect=400)['error'])
            self.assertIn('到期日要写成', self.make(ann, expires_at='soon', expect=400)['error'])
            bad = {'components': [{'title': '总金额按状态码', 'query': {'type': 'order'}, 'chart': {'kind': 'number', 'measure': '状态码', 'fn': 'sum'}}]}
            self.assertIn('“总金额按状态码”：', self.make(ann, spec=bad, expect=400)['error'])
            missing = {'components': [{'title': '幽灵', 'query': {'type': 'ghost'}, 'chart': {'kind': 'number'}}]}
            self.assertEqual(self.make(ann, spec=missing, expect=400)['error'], '“幽灵”：你现在看不到这个对象类型：它还没有确认，或者没有开放给你')
            self.assertIn('最多 12 个', self.make(ann, spec={'components': [CARD] * 13}, expect=400)['error'])
            ok = self.make(ann, refresh_seconds=300)
            self.assertEqual(ok['refresh_seconds'], 300)
            # a change from a page that was opened before another change is refused, one on the current version makes a new version
            self.assertEqual(ann.post('/api/workspace/dashboards/update', {'id': ok['id'], 'name': 'renamed', 'spec': SPEC, 'version': 99})[0], 409)
            changed = ann.post('/api/workspace/dashboards/update', {'id': ok['id'], 'name': 'renamed', 'spec': SPEC, 'version': ok['version'], 'scope': 'everyone'})[1]
            self.assertEqual((changed['name'], changed['version'], changed['scope']), ('renamed', 2, 'everyone'))
            self.assertEqual(ann.post('/api/workspace/dashboards/delete', {'id': ok['id']})[1], {'deleted': ok['id']})


class ReaderTests(BoardCase):
    def test_every_reader_gets_numbers_over_what_they_may_read_and_a_type_they_may_not_see_says_so(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, vera, admin = team['ann'], team['bob'], team['vera'], team['admin']
            ids = self.ids(admin)
            board = self.make(ann, scope='everyone')
            rules = [{'column': '客户编号', 'value': 'KH026', 'user_ids': [ids['vera']]}, {'column': '', 'value': '', 'user_ids': [ids['ann'], ids['bob']]}]   # vera reads one customer's orders, the builders all
            self.assertEqual(admin.post('/api/workspace/row-rules', {'type': 'order', 'rules': rules})[0], 200)
            mine = [r for r in ORDERS if r['客户编号'] == 'KH026']
            self.assertEqual(self.card(self.data(vera, board['id']))['result']['value'], sum(r['状态码'] != '2' for r in mine))
            self.assertEqual(self.card(self.data(bob, board['id']))['result']['value'], len(LIVE))
            self.assertTrue(self.card(self.data(vera, board['id']))['result']['rows_limited'])
            # the admin closes the customers to Bob: his card for them says so, the rest of the board is there
            self.assertEqual(admin.post('/api/workspace/permissions', {'type': 'customer', 'visible_to': [ids['vera']]})[0], 200)
            closed = self.data(bob, board['id'])
            self.assertEqual((self.card(closed, 'cust')['status'], self.card(closed, 'cust')['message']), ('unavailable', '你现在看不到这个对象类型：它还没有确认，或者没有开放给你'))
            self.assertEqual(self.card(closed)['status'], 'ok')
            self.assertEqual(closed['headline']['unavailable'], ['客户数'])

    def test_a_viewer_is_shown_no_number_that_stands_on_a_type_that_needs_a_look(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, vera = team['ann'], team['bob'], team['vera']
            board = self.make(ann, scope='everyone')
            self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [shifted_orders_csv()]})[0], 200)
            as_builder, as_viewer = self.data(bob, board['id']), self.data(vera, board['id'])
            self.assertEqual((self.card(as_builder)['status'], self.card(as_builder)['result']['standing']['confirmed']), ('ok', False))   # a builder sees the number, grey, with the reason
            self.assertEqual(self.card(as_viewer)['status'], 'unavailable')   # a viewer reads confirmed things only: the type is not theirs to see now
            self.assertNotIn('value', self.card(as_viewer))
            self.assertEqual(self.card(as_viewer, 'cust')['status'], 'ok')

    def test_the_filter_bar_applies_to_the_components_whose_type_has_the_field(self):
        with self.service() as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob = team['ann'], team['bob']
            board = self.make(ann, scope='everyone')
            bare = self.data(bob, board['id'])
            self.assertEqual([(f['field'], f['name'], f['value']) for f in bare['bar']], [('状态码', '状态', '')])
            self.assertEqual({o['value']: o['label'] for o in bare['bar'][0]['options']}, {'0': '已交付', '1': '生产中', '2': '已取消'})
            picked = self.data(bob, board['id'], {'状态码': '1', '重量': 'x'})   # a pick for a field the board has no filter for is ignored
            self.assertEqual(self.card(picked)['result']['value'], sum(r['状态码'] == '1' for r in ORDERS))   # the view keeps 0 and 1; the pick keeps 1
            self.assertEqual(self.card(picked, 'cust')['result']['value'], self.card(bare, 'cust')['result']['value'])   # 客户 has no 状态码
            self.assertEqual(self.card(picked, 'recent')['result']['total'], sum(r['状态码'] == '1' for r in ORDERS))
            self.assertEqual(len(self.card(picked, 'recent')['result']['rows']), 10)
            self.assertEqual(self.data(bob, board['id'], {'状态码': 5}, expect=400)['error'], '筛选条的取值要写成 {字段: 取值}')
            preview = bob.post('/api/workspace/dashboards/preview', {'spec': SPEC, 'bar': {'状态码': '2'}})[1]
            self.assertEqual(self.card(preview)['result']['value'], 0)   # the view drops 2; the pick asks for it: nothing, said as 0 and not as a gap
