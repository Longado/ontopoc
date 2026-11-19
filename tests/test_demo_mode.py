"""Demo mode: guest accounts, their limits, the ask guard, cleanup, and the seed."""
import base64
import json
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor
import http.cookiejar

from ontology_poc_generator import accounts, ask_budget, demo
from ontology_poc_generator.ontology_server import make_server
from ontology_poc_generator.workspace_store import open_workspace

GOOD = 'correct horse battery'


@contextmanager
def serving(demo_on=True):
    with tempfile.TemporaryDirectory() as out:
        conn = open_workspace(Path(out) / 'workspace.sqlite')
        accounts.create_user(conn, 'root', 'Root', 'admin', GOOD, 'test', must_change=False)
        conn.close()
        server = make_server(port=0, output_dir=Path(out), demo=demo_on)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', Path(out)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class Browser:
    def __init__(self, base):
        self.base, self.jar = base, http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def call(self, method, path, body=None):
        request = Request(self.base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': self.base, 'Accept-Language': 'en'})
        try:
            with self.opener.open(request) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)


class DemoRoutes(unittest.TestCase):
    def test_health_flag_only_when_on(self):
        with serving(True) as (base, _):
            self.assertEqual(Browser(base).call('GET', '/api/ontology/health')[1], {'ok': True, 'demo': True, 'demo_ask': False})
        with serving(False) as (base, _):
            self.assertEqual(Browser(base).call('GET', '/api/ontology/health')[1], {'ok': True})

    def test_off_is_404(self):
        with serving(False) as (base, _):
            status, body = Browser(base).call('POST', '/api/auth/demo', {})
            self.assertEqual(status, 404)
            self.assertIn('error', body)

    def test_guest_is_a_read_only_viewer(self):
        with serving(True) as (base, out):
            b = Browser(base)
            status, body = b.call('POST', '/api/auth/demo', {})
            self.assertEqual(status, 200)
            self.assertTrue(body['auth'] and body['demo'])
            user = body['user']
            self.assertEqual((user['role'], user['provider'], user['must_change']), ('viewer', 'demo', False))
            self.assertTrue(user['username'].startswith('guest-'))
            self.assertTrue(any(c.name == 'ontopoc_session' for c in b.jar))
            me = b.call('GET', '/api/auth/me')[1]
            self.assertTrue(me['demo'])
            self.assertEqual(me['user']['provider'], 'demo')
            self.assertEqual(b.call('GET', '/api/workspace/datasets')[0], 200)
            upload = {'files': [{'filename': 'x.csv', 'content_base64': base64.b64encode(b'a\n1\n').decode()}]}
            self.assertEqual(b.call('POST', '/api/workspace/datasets/upload', upload)[0], 403)
            self.assertEqual(b.call('POST', '/api/auth/password', {'current': 'x', 'new': 'y' * 14})[0], 403)
            self.assertEqual(b.call('GET', '/api/auth/tokens')[0], 403)
            self.assertEqual(b.call('POST', '/api/auth/tokens', {'label': 'x'})[0], 403)
            # no password can ever open a guest account
            status, _ = Browser(base).call('POST', '/api/auth/login', {'username': user['username'], 'password': GOOD})
            self.assertEqual(status, 401)

    def test_per_address_limit(self):
        with serving(True) as (base, _):
            codes = [Browser(base).call('POST', '/api/auth/demo', {})[0] for _ in range(6)]
            self.assertEqual(codes, [200] * 5 + [429])

    def test_total_limit(self):
        with serving(True) as (base, _), mock.patch.dict('os.environ', {'ONTOPOC_DEMO_MAX_GUESTS': '2'}):
            codes = [Browser(base).call('POST', '/api/auth/demo', {})[0] for _ in range(3)]
            self.assertEqual(codes, [200, 200, 429])


class AskGuard(unittest.TestCase):
    def setUp(self):
        self.conn = open_workspace(':memory:')

    def guest(self, n):
        return {'id': n, 'provider': 'demo'}

    def test_guest_hourly_limit(self):
        for i in range(ask_budget.GUEST_LIMIT):
            ask_budget.take(self.conn, self.guest(1), now=1000 + i)
        with self.assertRaises(ask_budget.AskBudgetSpent) as caught:
            ask_budget.take(self.conn, self.guest(1), now=1100)
        self.assertEqual(caught.exception.status, 429)
        ask_budget.take(self.conn, self.guest(2), now=1100)   # another guest is not affected
        ask_budget.take(self.conn, self.guest(1), now=1000 + 3601)   # the hour passed

    def test_daily_cap_across_guests(self):
        with mock.patch.dict('os.environ', {'ONTOPOC_DEMO_DAILY_ASKS': '15'}):
            for i in range(15):
                ask_budget.take(self.conn, self.guest(i // 5), now=1000 + i)
            with self.assertRaises(ask_budget.AskBudgetSpent) as caught:
                ask_budget.take(self.conn, self.guest(9), now=5000)
            self.assertIsInstance(caught.exception, ask_budget.DemoSpent)
            ask_budget.take(self.conn, {'id': 50, 'provider': 'local'}, now=5000)   # a real person is not counted against the demo
            ask_budget.take(self.conn, self.guest(9), now=1000 + 86400 + 100)   # a day later


class Cleanup(unittest.TestCase):
    def test_old_guests_go_new_stay(self):
        conn = open_workspace(':memory:')
        accounts.create_user(conn, 'root', 'Root', 'admin', GOOD, 'test', must_change=False)
        old = demo.create_guest(conn, '1.1.1.1')
        new = demo.create_guest(conn, '2.2.2.2')
        for g in (old, new):
            accounts.start_session(conn, g['id'])
            conn.execute("INSERT INTO notice(user_id, at, action_name, text) VALUES (?, 'now', 'a', 't')", (g['id'],))
            conn.execute('CREATE TABLE IF NOT EXISTS ask_budget (who TEXT NOT NULL, at REAL NOT NULL)')
            conn.execute('INSERT INTO ask_budget(who, at) VALUES (?, 1)', (f'user:{g["id"]}',))
        conn.execute('UPDATE user SET created_at = ? WHERE id = ?', ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec='seconds'), old['id']))
        self.assertEqual(demo.cleanup(conn, datetime.now(timezone.utc)), 1)
        ids = [u['id'] for u in accounts.list_users(conn)]
        self.assertIn(new['id'], ids)
        self.assertNotIn(old['id'], ids)
        for table, col in (('session', 'user_id'), ('notice', 'user_id'), ('demo_guest', 'user_id')):
            self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} = ?', (old['id'],)).fetchone()[0], 0, table)
            self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} = ?', (new['id'],)).fetchone()[0], 1, table)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM ask_budget').fetchone()[0], 1)
        self.assertEqual(accounts.list_users(conn)[0]['username'], 'root')


class Seed(unittest.TestCase):
    def test_seed_builds_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'demo'
            result = demo.seed(target)
            conn = open_workspace(target / 'workspace.sqlite')
            try:
                self.assertEqual(accounts.user_count(conn), 2)
                self.assertEqual(sorted(r[0] for r in conn.execute('SELECT DISTINCT name FROM dataset')), ['customers', 'orders'])
            finally:
                conn.close()
            self.assertEqual(sorted(result['types']), ['customer', 'order'])
            with self.assertRaises(SystemExit):
                demo.seed(target)
            with self.assertRaises(SystemExit):
                demo.seed(Path(tmp), force_fresh=True)   # not a demo folder (no marker): refuses to wipe
            demo.seed(target, force_fresh=True)

    def test_guest_opens_the_seeded_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'demo'
            demo.seed(target)
            server = make_server(port=0, gateway=None, output_dir=target, demo=True)
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            try:
                guest = Browser(f'http://127.0.0.1:{server.server_port}')
                self.assertEqual(guest.call('GET', '/api/ontology/health')[1], {'ok': True, 'demo': True, 'demo_ask': False})
                self.assertEqual(guest.call('POST', '/api/auth/demo', {})[0], 200)   # a guest made after the seed
                boards = guest.call('GET', '/api/workspace/dashboards')[1]['dashboards']
                self.assertEqual([b['name'] for b in boards], ['Orders overview'])
                status, body = guest.call('POST', '/api/workspace/dashboards/data', {'id': boards[0]['id'], 'bar': {}})
                self.assertEqual(status, 200, body)
                by_id = {c['id']: c for c in body['components']}
                self.assertTrue(all(c['status'] == 'ok' for c in by_id.values()), body)
                self.assertEqual([by_id[k]['result']['value'] for k in ('valid_amount', 'valid_count', 'all_amount')], [119810, 107, 162960])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_health_demo_ask_follows_the_gateway(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(port=0, gateway=object(), output_dir=Path(tmp), demo=True)
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            try:
                self.assertTrue(Browser(f'http://127.0.0.1:{server.server_port}').call('GET', '/api/ontology/health')[1]['demo_ask'])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
