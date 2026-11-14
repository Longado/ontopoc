"""The stage 6 security review (2026-11-14), one test for each finding that was fixed: what a token may do is decided by the service from the token's own scope and
expiry (M1), a derived property that reads a column kept from models is not read out to an agent (M2), asking has a budget (M3), a board shows its definition only to
its author (L1, L2), row numbers do not count the rows a person may not read (L3), wrongly typed requests are answered (L4), the key of an object is not in a URL
(L5) and a request has a size (L6)."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from unittest import mock

from ontology_poc_generator import ask_budget, mcp_server
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_access import Client
from tests.test_agent_access import AgentCase
from tests.test_dashboards import BoardCase, CARD, SPEC
from tests.test_derived_properties import GROSS
from tests.test_explorer import CUSTOMERS, ORDER_Q
from tests.test_workspace_questions import AskModel, QUESTION, cancelled


def bearer(token):
    return {'headers': {'Authorization': f'Bearer {token}'}, 'origin': None}


class TokenScopeTests(AgentCase, BoardCase):
    def test_a_read_token_reads_and_asks_but_changes_nothing_whatever_its_owner_s_role(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, admin = team['ann'], team['admin']
            board = self.make(ann, scope='everyone')
            made = self.token_for(admin, 'bob')   # Bob is a builder; no scope said
            self.assertEqual(made['scope'], 'read')
            script = Client(base)
            as_bob = bearer(made['token'])
            for path in ('/api/workspace/agent/definitions', '/api/workspace/agent/unconfirmed', '/api/workspace/explore/order', '/api/workspace/dashboards', '/api/auth/me',
                         '/api/workspace/types', f'/api/workspace/dashboards/{board["id"]}'):
                self.assertEqual(script.get(path, **as_bob)[0], 200, path)
            self.assertEqual(script.get('/api/auth/me', **as_bob)[1]['user']['token_scope'], 'read')
            reads = (('/api/workspace/ask', {'question': QUESTION}), ('/api/workspace/explore/table', {'query': ORDER_Q}), ('/api/workspace/explore/chart', {'query': ORDER_Q, 'chart': {'kind': 'number'}}),
                     ('/api/workspace/dashboards/data', {'id': board['id']}), ('/api/workspace/dashboards/preview', {'spec': SPEC}))
            for path, body in reads:
                self.assertEqual(script.post(path, body, **as_bob)[0], 200, path)
            for path, body in (('/api/workspace/dashboards', {'name': 'x', 'spec': SPEC}), ('/api/workspace/dashboards/delete', {'id': board['id']}),
                               ('/api/workspace/datasets/upload', {}), ('/api/workspace/types/views', {}), ('/api/workspace/types/confirm', {}),
                               ('/api/workspace/row-rules', {'type': 'order', 'rules': []}), ('/api/auth/tokens', {'label': 'more'})):
                status, body = script.post(path, body, **as_bob)
                self.assertEqual(status, 403, path)
            self.assertIn('只能读', script.post('/api/workspace/dashboards', {'name': 'x', 'spec': SPEC}, **as_bob)[1]['error'])
            self.assertEqual(len(ann.get('/api/workspace/dashboards')[1]['dashboards']), 1)   # nothing was made or deleted

    def test_an_admin_can_give_a_token_every_tool_but_only_by_choosing_it_and_never_for_an_admin_account(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            admin = team['admin']
            full = self.token_for(admin, 'bob', scope='all')
            self.assertEqual(full['scope'], 'all')
            made = Client(base).post('/api/workspace/dashboards', {'name': 'x', 'spec': SPEC}, **bearer(full['token']))
            self.assertEqual(made[0], 200, made[1])
            ids = {u['username']: u['id'] for u in admin.get('/api/users')[1]['users']}
            refused = admin.post('/api/users/tokens', {'user_id': ids['root'], 'label': 'x'})
            self.assertEqual(refused[0], 400)
            self.assertIn('管理员', refused[1]['error'])
            self.assertEqual(admin.post('/api/users/tokens', {'user_id': ids['bob'], 'label': 'x', 'scope': 'write'})[0], 400)
            listed = {t['id']: t for t in admin.get('/api/users/tokens')[1]['tokens']}
            self.assertEqual([(t['username'], t['scope']) for t in listed.values()], [('bob', 'all')])
            # the person's own token from the account page is theirs to scope; it was a full pass before scopes and stays one unless they ask for less
            own = team['ann'].post('/api/auth/tokens', {'label': 'mine', 'scope': 'read'})[1]
            self.assertEqual(Client(base).post('/api/workspace/dashboards', {'name': 'y', 'spec': SPEC}, **bearer(own['token']))[0], 403)

    def test_a_token_expires_after_the_days_it_was_made_for_90_unless_said_and_the_list_shows_when(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            admin = team['admin']
            default, short = self.token_for(admin, 'bob'), self.token_for(admin, 'vera', days=7)
            for made, days in ((default, 90), (short, 7)):
                self.assertAlmostEqual(datetime.fromisoformat(made['expires_at']), datetime.now(timezone.utc) + timedelta(days=days), delta=timedelta(minutes=5))
            self.assertEqual({t['username']: t['expires_at'] for t in admin.get('/api/users/tokens')[1]['tokens']}, {'bob': default['expires_at'], 'vera': short['expires_at']})
            self.assertEqual(admin.post('/api/users/tokens', {'user_id': default['user_id'], 'label': 'x', 'days': 5})[0], 400)   # 7, 30, 90 or 365
            self.assertEqual(Client(base).get('/api/auth/me', **bearer(default['token']))[0], 200)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            conn.execute('UPDATE api_token SET expires_at = ? WHERE id = ?', ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec='seconds'), default['id']))
            conn.commit()
            conn.close()
            self.assertEqual(Client(base).get('/api/auth/me', **bearer(default['token']))[0], 401)   # past its day: no credential at all

    def test_the_mcp_server_offers_what_the_token_s_scope_allows_and_its_environment_can_only_narrow_that(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            admin = team['admin']
            read, full = self.token_for(admin, 'bob')['token'], self.token_for(admin, 'bob', scope='all')['token']
            listed = lambda **kw: {t['name'] for t in self.mcp(base, calls=[], **kw)[2]['result']['tools']}
            self.assertEqual(listed(token=read, toolset=None), set(mcp_server.READ_TOOLS))
            self.assertEqual(listed(token=read, toolset='all'), set(mcp_server.READ_TOOLS))   # asking for more in its own environment gets nothing: the service would refuse the calls
            self.assertIn('build_ontology', listed(token=full, toolset=None))
            self.assertEqual(listed(token=full, toolset='read'), set(mcp_server.READ_TOOLS))
            self.assertIn('build_ontology', listed(token=None, toolset=None))   # no token: the local session's toolset, as before


class DerivedReadTests(AgentCase):
    def test_a_derived_property_that_reads_a_column_kept_from_models_is_not_read_out_even_to_the_person_s_own_agent(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.assertEqual(ann.post('/api/workspace/types/derived', GROSS)[0], 200)
            self.assertEqual(self.confirm(bob, GROSS)[0], 200)
            gross, cancelled_orders = {'type': 'order', 'name': 'gross'}, {'type': 'customer', 'name': 'cancelled_orders'}
            self.assertEqual(bob.post('/api/workspace/agent/derived', gross)[0], 200)   # until a column it reads is kept from models
            self.assertEqual(bob.post('/api/workspace/agent/derived', cancelled_orders)[0], 200)
            for column in ('金额', '状态码'):
                self.assertEqual(ann.post('/api/workspace/types/privacy', {'id': 'order', 'column': column, 'hide_values': True})[0], 200)
            for body in (gross, cancelled_orders):   # one reads the column in its expression, the other in its condition
                status, refused = bob.post('/api/workspace/agent/derived', body)
                self.assertEqual(status, 403, body)
                self.assertIn('不对模型开放', refused['error'])
            token = self.token_for(admin, 'bob')['token']
            reply = self.mcp(base, token, [('read_derived_property', gross)])[10]['result']
            self.assertTrue(reply['isError'])
            self.assertIn('不对模型开放', reply['content'][0]['text'])
            self.assertNotIn('2847', json.dumps(reply))   # not one value of 金额 x 1.13

    def test_the_key_of_an_object_travels_in_the_body_not_in_the_address(self):
        with self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            bob = team['bob']
            customer = CUSTOMERS[0]
            key = {'客户编号': customer['客户编号'], '城市': customer['城市']}
            status, one = bob.post('/api/workspace/agent/derived', {'type': 'customer', 'name': 'cancelled_orders', 'key': key})
            self.assertEqual((status, one['total']), (200, 1))
            self.assertNotEqual(bob.get('/api/workspace/agent/derived?type=customer&name=cancelled_orders')[0], 200)   # no such route any more
            self.assertEqual(bob.post('/api/workspace/agent/derived', {'type': 'customer', 'name': 'cancelled_orders', 'key': 'KH001'})[0], 400)


class AskBudgetTests(AgentCase):
    def test_asking_is_limited_for_each_token_and_for_each_person_and_the_refusal_says_when_it_frees_up(self):
        with mock.patch.object(ask_budget, 'TOKEN_LIMIT', 2), mock.patch.object(ask_budget, 'PERSON_LIMIT', 3), self.service(gateway=AskModel(cancelled())) as (base, out):
            team = self.team(base)
            self.world(team)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            first, second = self.token_for(admin, 'bob')['token'], self.token_for(admin, 'bob')['token']
            script = Client(base)
            ask = lambda token: script.post('/api/workspace/ask', {'question': QUESTION}, **bearer(token))
            self.assertEqual([ask(first)[0], ask(first)[0]], [200, 200])
            status, refused = ask(first)
            self.assertEqual(status, 429)
            self.assertIn('每小时最多 2 个', refused['error'])
            self.assertRegex(refused['error'], r'约 \d+ 分钟后再问')
            self.assertTrue(0 < int(script.last_headers['Retry-After']) <= 3600)
            self.assertEqual(ask(second)[0], 200)   # another token of his has its own count, up to what he may ask in all
            self.assertEqual(ask(second)[0], 429)
            self.assertIn('每小时最多 3 个', ask(second)[1]['error'])
            self.assertEqual(bob.post('/api/workspace/ask', {'question': QUESTION})[0], 429)   # at the page too: it is the person's budget
            self.assertEqual(ann.post('/api/workspace/ask', {'question': QUESTION})[0], 200)   # someone else's is theirs

    def test_the_hour_is_a_rolling_one_and_a_refused_ask_is_not_counted(self):
        conn = open_workspace(':memory:')
        person = {'id': 7, 'token_id': 3}
        with mock.patch.object(ask_budget, 'TOKEN_LIMIT', 2), mock.patch.object(ask_budget, 'PERSON_LIMIT', 5):
            ask_budget.take(conn, person, now=1000.0)
            ask_budget.take(conn, person, now=1100.0)
            with self.assertRaises(ask_budget.AskBudgetSpent) as spent:
                ask_budget.take(conn, person, now=1200.0)
            self.assertEqual(spent.exception.wait, 3600 - 200)   # when the first one leaves the hour
            self.assertEqual(spent.exception.status, 429)
            ask_budget.take(conn, person, now=1000.0 + 3600)   # the first has left: one more may be asked
            with self.assertRaises(ask_budget.AskBudgetSpent):
                ask_budget.take(conn, person, now=1000.0 + 3600 + 1)   # and the one before it was counted, the refused one was not
            ask_budget.take(conn, {'id': 7, 'token_id': None}, now=1200.0)   # no token: only the person's count, which is not full
