"""The stage 6 security review (2026-11-14), one test for each finding that was fixed: what a token may do is decided by the service from the token's own scope and
expiry (M1), a derived property that reads a column kept from models is not read out to an agent (M2), asking has a budget (M3), a board shows its definition only to
its author (L1, L2), row numbers do not count the rows a person may not read (L3), wrongly typed requests are answered (L4), the key of an object is not in a URL
(L5) and a request has a size (L6)."""
from datetime import datetime, timedelta, timezone
import sqlite3

from ontology_poc_generator import mcp_server
from tests.test_access import Client
from tests.test_agent_access import AgentCase
from tests.test_dashboards import BoardCase, CARD, SPEC
from tests.test_explorer import ORDER_Q
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
