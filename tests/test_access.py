"""The route table, and the sign-in gate in front of the real service: who may call what, the cookie, the Origin check, the first admin."""
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ontology_poc_generator import accounts, auth_http, ontology_server
from ontology_poc_generator.access import PUBLIC, SESSION, required_role, route_role
from ontology_poc_generator.auth_http import Gate
from ontology_poc_generator.workspace_store import open_workspace

GOOD = 'correct horse battery'
SOURCES = Path(ontology_server.__file__).parent


class RouteTableTests(unittest.TestCase):
    def test_every_route_the_service_has_is_in_the_table(self):
        """A route added to the service without a line in access.py is admin-only by default; this makes that a failing test instead of a surprise."""
        literals = set()
        for name in ('ontology_server.py', 'auth_http.py'):
            literals |= set(re.findall(r"""['"](/api/[A-Za-z0-9_/-]*)['"]""", (SOURCES / name).read_text(encoding='utf-8')))
        literals -= {'/api/recall', '/api/ontology', '/api/workspace', '/api/auth/', '/api/users/', '/api/workspace/', '/api/ontology/runs/', '/api/ontology/library/',
                     '/api/ontology/jobs/', '/api/workspace/datasets/'}   # prefixes the code compares against; their routes are checked below
        self.assertGreater(len(literals), 25)
        missing = sorted(p for p in literals if route_role('GET', p) is None and route_role('POST', p) is None)
        self.assertEqual(missing, [])
        for prefix in ('/api/ontology/runs/', '/api/ontology/library/', '/api/ontology/jobs/', '/api/workspace/datasets/'):
            self.assertIsNotNone(route_role('GET', prefix + 'x'), prefix)

    def test_a_route_not_in_the_table_needs_an_admin(self):
        self.assertEqual(required_role('POST', '/api/ontology/something-new'), 'admin')
        self.assertEqual(required_role('GET', '/api/anything'), 'admin')
        self.assertEqual(required_role('DELETE', '/api/workspace/datasets/x'), 'admin')   # a method the table does not list
        self.assertEqual(required_role('POST', '/api/workspace/datasets/x'), 'admin')

    def test_who_may_do_what(self):
        for method, path, role in (
                ('GET', '/api/workspace/datasets', 'viewer'), ('GET', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95', 'viewer'), ('GET', '/api/workspace/tasks', 'viewer'),
                ('GET', '/api/ontology/runs', 'viewer'), ('GET', '/api/ontology/runs/a.json/objects/x', 'viewer'), ('GET', '/api/ontology/jobs/abc', 'viewer'),
                ('POST', '/api/ontology/ask', 'viewer'),
                ('POST', '/api/workspace/datasets/upload', 'builder'), ('POST', '/api/workspace/datasets/delete', 'builder'), ('POST', '/api/ontology/build', 'builder'),
                ('POST', '/api/ontology/confirm', 'builder'), ('POST', '/api/ontology/code-meanings/withdraw', 'builder'), ('POST', '/api/ontology/pipelines/run', 'builder'),
                ('POST', '/api/ontology/review/confirm', 'builder'), ('POST', '/api/ontology/requery', 'builder'), ('POST', '/api/ontology/library/import', 'builder'),
                ('GET', '/api/users', 'admin'), ('POST', '/api/users/disable', 'admin'),
                ('POST', '/api/auth/login', PUBLIC), ('GET', '/api/ontology/health', PUBLIC), ('GET', '/api/auth/me', SESSION), ('POST', '/api/auth/tokens/revoke', SESSION)):
            self.assertEqual(required_role(method, path), role, (method, path))

    def test_a_pattern_matches_the_whole_path(self):
        self.assertEqual(required_role('GET', '/api/workspace/datasets/../../users'), 'viewer')   # no traversal on the server: it is a name, so this is a viewer read of a dataset
        self.assertEqual(required_role('POST', '/api/ontology/confirm/extra'), 'admin')
        self.assertEqual(required_role('POST', '/prefix/api/ontology/ask'), 'admin')


class Client:
    """One person's browser: keeps the cookie the service sets."""
    def __init__(self, base):
        self.base, self.cookie, self.last_headers = base, None, None

    def call(self, method, path, payload=None, origin='same', headers=None):
        head = {'Content-Type': 'application/json', **(headers or {})}
        if origin == 'same':
            origin = self.base
        if origin and method == 'POST':
            head['Origin'] = origin
        if self.cookie:
            head['Cookie'] = f'{accounts_cookie()}={self.cookie}'
        request = Request(self.base + path, data=None if payload is None and method == 'GET' else json.dumps(payload or {}).encode(), headers=head, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                status, body, self.last_headers = response.status, json.load(response), response.headers
        except HTTPError as exc:
            status, body, self.last_headers = exc.code, json.load(exc), exc.headers
        set_cookie = self.last_headers.get('Set-Cookie')
        if set_cookie:
            self.cookie = set_cookie.split(';')[0].split('=', 1)[1] or None
        return status, body

    def get(self, path, **more):
        return self.call('GET', path, **more)

    def post(self, path, payload=None, **more):
        return self.call('POST', path, payload, **more)

    def login(self, username, password=GOOD):
        return self.post('/api/auth/login', {'username': username, 'password': password})


def accounts_cookie():
    return auth_http.COOKIE


class GateTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(accounts, 'SCRYPT_N', 2 ** 10)
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextmanager
    def service(self, first_admin=True, gateway=None, **more):
        with tempfile.TemporaryDirectory() as out:
            out = Path(out)
            server = ontology_server.make_server(port=0, gateway=gateway, output_dir=out, **more)
            if first_admin:
                conn = open_workspace(out / 'workspace.sqlite')
                accounts.create_user(conn, 'root', '管理员', 'admin', GOOD, 'host', must_change=False)
                conn.close()
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            try:
                yield f'http://127.0.0.1:{server.server_port}', out
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def team(self, base):
        """An admin, a builder and a viewer, each signed in with their own client; the two new ones have changed their first password."""
        admin = Client(base)
        self.assertEqual(admin.login('root')[0], 200)
        people = {'admin': admin}
        for name, role in (('builder', 'builder'), ('viewer', 'viewer')):
            self.assertEqual(admin.post('/api/users', {'username': name, 'display_name': name.title(), 'role': role, 'password': 'first password 1'})[0], 200)
            client = Client(base)
            self.assertEqual(client.login(name, 'first password 1')[0], 200)
            self.assertEqual(client.post('/api/auth/password', {'current': 'first password 1', 'new': GOOD})[0], 200)
            people[name] = client
        return people


def table_part(name='t.csv'):
    return {'filename': name, 'content_base64': base64.b64encode('编号,数量\n1,2\n'.encode()).decode()}


class GateTests(GateTestCase):
    def test_a_stranger_gets_nothing_but_the_sign_in_page_and_a_pulse(self):
        with self.service() as (base, _):
            guest = Client(base)
            self.assertEqual(guest.get('/api/ontology/health'), (200, {'ok': True}))   # no code fingerprint, no model state
            for path in ('/api/workspace/datasets', '/api/ontology/runs', '/api/users', '/api/auth/me', '/api/nothing'):
                self.assertEqual(guest.get(path)[0], 401, path)
            self.assertEqual(guest.post('/api/workspace/datasets/upload', {'files': [table_part()]})[0], 401)

    def test_no_account_yet_means_the_service_says_how_to_make_one_and_does_nothing_else(self):
        with self.service(first_admin=False) as (base, _):
            guest = Client(base)
            status, body = guest.get('/api/workspace/datasets')
            self.assertEqual((status, body['setup']), (503, True))
            self.assertIn('create-admin', body['error'])
            self.assertEqual(guest.get('/api/ontology/health'), (200, {'ok': True}))
            self.assertEqual(guest.login('anyone', GOOD)[0], 503)   # there is no setup page to sign in to: the admin is made on the host
            self.assertEqual(guest.get('/api/auth/me')[1]['setup'], True)   # so the sign-in form can say so

    def test_signing_in_sets_a_cookie_that_javascript_cannot_read_and_other_sites_cannot_send(self):
        with self.service() as (base, out):
            admin = Client(base)
            status, body = admin.login('root')
            self.assertEqual((status, body['user']['role'], body['auth']), (200, 'admin', True))
            cookie = admin.last_headers['Set-Cookie']
            self.assertRegex(cookie, r'^ontopoc_session=[\w-]{40,}; HttpOnly; SameSite=Strict; Path=/; Max-Age=1209600$')
            self.assertNotIn('Secure', cookie)   # plain http on this machine
            self.assertEqual(admin.get('/api/auth/me')[1]['user']['username'], 'root')
            self.assertEqual(admin.get('/api/ontology/health')[1]['stale'], False)   # a signed-in person gets the whole answer
            self.assertEqual(oct(os.stat(out / 'workspace.sqlite').st_mode & 0o777), '0o600')

    def test_the_wrong_password_and_the_wrong_name_get_the_same_answer_and_the_sixth_try_waits(self):
        with self.service() as (base, _):
            guest = Client(base)
            self.assertEqual(guest.login('root', 'wrong password!!'), (401, {'error': accounts.GENERIC}))
            self.assertEqual(guest.login('nobody', 'wrong password!!'), (401, {'error': accounts.GENERIC}))
            for _ in range(4):   # five wrong passwords for root in all
                self.assertEqual(guest.login('root', 'wrong password!!')[0], 401)
            status, body = guest.login('root', GOOD)   # the sixth try is not even checked, so the right password does not get in
            self.assertEqual((status, guest.last_headers['Retry-After']), (429, '60'))
            self.assertIn('请 60 秒后再试', body['error'])

    def test_a_post_must_come_from_this_site_unless_it_carries_a_token(self):
        with self.service() as (base, _):
            admin = Client(base)
            admin.login('root')
            for origin in (None, 'http://evil.example', 'http://127.0.0.1:1', 'http://localhost:9999', 'null'):
                status, body = admin.post('/api/users', {'username': 'x', 'display_name': 'x', 'role': 'viewer', 'password': GOOD}, origin=origin)
                self.assertEqual(status, 403, origin)
            self.assertEqual(len(admin.get('/api/users')[1]['users']), 1)   # nothing was made
            _, made = admin.post('/api/auth/tokens', {'label': 'script'})
            script = Client(base)
            status, _ = script.post('/api/workspace/datasets/upload', {'files': [table_part()]}, origin=None, headers={'Authorization': f'Bearer {made["token"]}'})
            self.assertEqual(status, 200)   # a script sends no Origin; a token is not sent by a browser by itself

    def test_a_viewer_reads_a_builder_changes_data_and_only_an_admin_manages_people(self):
        with self.service() as (base, _):
            team = self.team(base)
            upload = {'who': 'ignored', 'files': [table_part()]}
            self.assertEqual(team['viewer'].get('/api/workspace/datasets')[0], 200)
            status, body = team['viewer'].post('/api/workspace/datasets/upload', upload)
            self.assertEqual((status, body['error']), (403, '你的角色不能做这个'))
            self.assertEqual(team['builder'].post('/api/workspace/datasets/upload', upload)[0], 200)
            self.assertEqual(team['viewer'].get('/api/workspace/datasets')[1]['datasets'][0]['name'], 't')
            for who in ('builder', 'viewer'):
                self.assertEqual(team[who].get('/api/users')[0], 403, who)
                self.assertEqual(team[who].post('/api/users', {'username': 'x', 'display_name': 'x', 'role': 'admin', 'password': GOOD})[0], 403, who)
                self.assertEqual(team[who].post('/api/users/update', {'id': 2, 'role': 'admin'})[0], 403, who)
            self.assertEqual(team['viewer'].post('/api/ontology/confirm', {})[0], 403)   # a definition write
            self.assertEqual(team['builder'].post('/api/ontology/no-such-thing', {})[0], 403)   # not in the table: admin only, not even a 404 to a builder
            self.assertEqual(team['admin'].post('/api/ontology/no-such-thing', {})[0], 404)

    def test_a_new_person_changes_the_first_password_before_anything_else(self):
        with self.service() as (base, _):
            admin = Client(base)
            admin.login('root')
            admin.post('/api/users', {'username': 'newbie', 'display_name': '新人', 'role': 'builder', 'password': 'first password 1'})
            newbie = Client(base)
            self.assertTrue(newbie.login('newbie', 'first password 1')[1]['user']['must_change'])
            self.assertEqual(newbie.get('/api/auth/me')[0], 200)
            status, body = newbie.get('/api/workspace/datasets')
            self.assertEqual((status, body.get('must_change')), (403, True))
            self.assertEqual(newbie.post('/api/auth/password', {'current': 'first password 1', 'new': 'first password 1'})[0], 200)   # not forbidden to keep it, but they were asked
            self.assertEqual(newbie.get('/api/workspace/datasets')[0], 200)

    def test_disabling_and_demoting_take_effect_on_the_next_request(self):
        with self.service() as (base, _):
            team = self.team(base)
            self.assertEqual(team['admin'].post('/api/users/update', {'id': 2, 'role': 'viewer'})[1]['user']['role'], 'viewer')
            self.assertEqual(team['builder'].post('/api/workspace/datasets/upload', {'files': [table_part()]})[0], 403)
            self.assertEqual(team['admin'].post('/api/users/disable', {'id': 3, 'disabled': True})[0], 200)
            self.assertEqual(team['viewer'].get('/api/workspace/datasets')[0], 401)   # the session died with the account
            self.assertEqual(Client(base).login('viewer')[0], 401)

    def test_an_admin_cannot_lock_themselves_out_or_leave_the_workspace_without_one(self):
        with self.service() as (base, _):
            admin = Client(base)
            admin.login('root')
            self.assertEqual(admin.post('/api/users/update', {'id': 1, 'role': 'viewer'})[0], 400)
            self.assertEqual(admin.post('/api/users/disable', {'id': 1, 'disabled': True})[0], 400)
            self.assertEqual(admin.post('/api/users/update', {'id': 99, 'role': 'viewer'})[0], 404)
            self.assertEqual(admin.post('/api/users/update', {'id': 1})[0], 400)
            self.assertEqual(admin.get('/api/auth/me')[1]['user']['role'], 'admin')

    def test_a_token_works_as_its_owner_but_cannot_make_tokens_or_manage_people(self):
        with self.service() as (base, _):
            team = self.team(base)
            _, made = team['builder'].post('/api/auth/tokens', {'label': 'mcp'})
            script = Client(base)
            bearer = {'headers': {'Authorization': f'Bearer {made["token"]}'}, 'origin': None}
            self.assertEqual(script.get('/api/workspace/datasets', **bearer)[0], 200)
            self.assertEqual(script.post('/api/workspace/datasets/upload', {'files': [table_part()]}, **bearer)[0], 200)
            self.assertEqual(script.get('/api/users', **bearer)[0], 403)
            self.assertEqual(script.post('/api/auth/tokens', {'label': 'more'}, **bearer)[0], 403)
            self.assertEqual(script.post('/api/auth/password', {'current': GOOD, 'new': 'another long one'}, **bearer)[0], 403)
            self.assertEqual(script.get('/api/auth/me', headers={'Authorization': 'Bearer otp_nope'})[0], 401)
            team['builder'].post('/api/auth/tokens/revoke', {'id': made['id']})
            self.assertEqual(script.get('/api/workspace/datasets', **bearer)[0], 401)
            team['admin'].post('/api/users/update', {'id': 2, 'role': 'viewer'})
            _, again = team['builder'].post('/api/auth/tokens', {'label': 'later'})
            self.assertEqual(script.post('/api/workspace/datasets/upload', {'files': [table_part('u.csv')]}, headers={'Authorization': f'Bearer {again["token"]}'}, origin=None)[0], 403)

    def test_logging_out_ends_the_session_on_the_server(self):
        with self.service() as (base, _):
            admin = Client(base)
            admin.login('root')
            stolen = admin.cookie
            self.assertEqual(admin.post('/api/auth/logout')[0], 200)
            self.assertIn('Max-Age=0', admin.last_headers['Set-Cookie'])
            replay = Client(base)
            replay.cookie = stolen
            self.assertEqual(replay.get('/api/auth/me')[0], 401)

    def test_every_sign_in_starts_a_new_session(self):
        with self.service() as (base, _):
            first, second = Client(base), Client(base)
            first.login('root')
            second.login('root')
            self.assertNotEqual(first.cookie, second.cookie)

    def test_a_request_for_another_host_name_is_refused(self):
        with self.service() as (base, _):
            guest = Client(base)
            self.assertEqual(guest.get('/api/ontology/health', headers={'Host': 'evil.example'})[0], 403)


class BehindAProxyTests(GateTestCase):
    def test_an_https_address_makes_the_cookie_secure_and_is_the_origin_a_post_must_carry(self):
        with self.service(origins=['https://onto.example.com']) as (base, _):
            admin = Client(base)
            host = {'Host': 'onto.example.com'}
            status, _ = admin.call('POST', '/api/auth/login', {'username': 'root', 'password': GOOD}, origin='https://onto.example.com', headers=host)
            self.assertEqual(status, 200)
            self.assertTrue(admin.last_headers['Set-Cookie'].endswith('; Secure'))
            self.assertEqual(admin.call('POST', '/api/users', {'username': 'x', 'display_name': 'x', 'role': 'viewer', 'password': GOOD}, origin='http://onto.example.com', headers=host)[0], 403)
            self.assertEqual(admin.call('GET', '/api/auth/me', headers=host)[0], 200)

    def test_a_plain_http_address_that_is_not_this_machine_is_refused_at_start(self):
        with tempfile.TemporaryDirectory() as out, self.assertRaises(ValueError) as caught:
            ontology_server.make_server(port=0, gateway=None, output_dir=Path(out), origins=['http://onto.example.com'])
        self.assertIn('必须用 https', str(caught.exception))
        with tempfile.TemporaryDirectory() as out, self.assertRaises(ValueError):
            ontology_server.make_server(port=0, gateway=None, output_dir=Path(out), origins=['onto.example.com'])

    def test_the_caller_is_the_address_the_proxy_saw_and_not_what_came_before_it(self):
        class Fake:
            client_address = ('127.0.0.1', 5)
            headers = {'X-Forwarded-For': '1.1.1.1, 2.2.2.2'}
        proxied = Gate(':memory:', 0, ['https://onto.example.com'])
        self.assertEqual(proxied.client(Fake()), '2.2.2.2')   # the left-hand entries are whatever the caller wrote
        self.assertEqual(Gate(':memory:', 0).client(Fake()), '127.0.0.1')   # with no proxy configured the header is ignored


class NoAuthTests(GateTestCase):
    def test_no_auth_keeps_the_old_local_behaviour_and_makes_everyone_the_local_admin(self):
        with self.service(first_admin=False, no_auth=True) as (base, _):
            guest = Client(base)
            self.assertEqual(guest.get('/api/workspace/datasets')[0], 200)
            self.assertEqual(guest.get('/api/ontology/health')[1]['stale'], False)
            status, body = guest.get('/api/auth/me')
            self.assertEqual((status, body['user']['role'], body['auth']), (200, 'admin', False))
            self.assertEqual(guest.post('/api/users', {'username': 'x'})[0], 400)
            self.assertEqual(guest.get('/api/workspace/datasets', headers={'Host': 'evil.example'})[0], 403)


if __name__ == '__main__':
    unittest.main()
