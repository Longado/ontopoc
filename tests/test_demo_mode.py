"""Demo mode: guest accounts, their limits, the ask guard, cleanup, and the seed."""
import base64
import json
import sqlite3
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
    def __init__(self, base, lang='en'):
        self.base, self.lang, self.jar = base, lang, http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.jar))

    def call(self, method, path, body=None):
        request = Request(self.base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json', 'Origin': self.base, 'Accept-Language': self.lang})
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

    def test_hourly_limit_across_addresses(self):
        conn = open_workspace(':memory:')
        with mock.patch.dict('os.environ', {'ONTOPOC_DEMO_GUESTS_PER_HOUR': '3'}):
            for i in range(3):
                demo.create_guest(conn, f'10.0.0.{i}')
            with self.assertRaises(accounts.AccountError) as caught:
                demo.create_guest(conn, '10.0.0.9')
            self.assertEqual(caught.exception.status, 429)
            self.assertIsNotNone(demo.create_guest(conn, '10.0.0.9', now=__import__('time').time() + 3601))

    def test_ipv6_counts_by_its_64(self):
        self.assertEqual(demo.address_key('2001:db8:1:2::5'), demo.address_key('2001:db8:1:2:ffff::9'))
        self.assertNotEqual(demo.address_key('2001:db8:1:2::5'), demo.address_key('2001:db8:1:3::5'))
        self.assertEqual(demo.address_key('::ffff:10.1.2.3'), '10.1.2.3')
        self.assertEqual(demo.address_key('203.0.113.7'), '203.0.113.7')
        conn = open_workspace(':memory:')
        for i in range(5):
            demo.create_guest(conn, f'2001:db8:1:2::{i + 1}')
        with self.assertRaises(accounts.AccountError):
            demo.create_guest(conn, '2001:db8:1:2::abcd')

    def test_total_limit(self):
        with serving(True) as (base, _), mock.patch.dict('os.environ', {'ONTOPOC_DEMO_MAX_GUESTS': '2'}):
            codes = [Browser(base).call('POST', '/api/auth/demo', {})[0] for _ in range(3)]
            self.assertEqual(codes, [200, 200, 429])


class GuestInput(unittest.TestCase):
    """What a guest can send: small bodies only, and a wrong one is answered, never dropped."""

    def test_wrong_bodies_are_answered_400(self):
        with serving(True) as (base, _):
            b = Browser(base)
            self.assertEqual(b.call('POST', '/api/auth/demo', {})[0], 200)
            for path in ('/api/workspace/ask', '/api/workspace/query', '/api/workspace/query/text', '/api/workspace/notices/read'):
                status, body = b.call('POST', path, [])
                self.assertEqual(status, 400, path)
                self.assertIn('error', body)

    def test_a_number_no_table_can_hold_is_answered_400(self):
        with serving(True) as (base, _):
            b = Browser(base)
            self.assertEqual(b.call('POST', '/api/auth/demo', {})[0], 200)
            for path, body in (('/api/workspace/notices/read', {'ids': [10 ** 30]}), ('/api/workspace/dashboards/data', {'id': 10 ** 30})):
                status, answer = b.call('POST', path, body)
                self.assertEqual(status, 400, path)
                self.assertIn('error', answer)

    def test_large_bodies_are_refused(self):
        with serving(True) as (base, _):
            b = Browser(base)
            self.assertEqual(b.call('POST', '/api/auth/demo', {})[0], 200)
            for path in ('/api/workspace/ask', '/api/workspace/query', '/api/workspace/query/text', '/api/workspace/notices/read'):
                self.assertEqual(b.call('POST', path, {'question': 'x' * 100_000})[0], 413, path)

    def test_an_absurd_answer_id_is_404(self):
        with serving(True) as (base, _):
            b = Browser(base)
            self.assertEqual(b.call('POST', '/api/auth/demo', {})[0], 200)
            self.assertEqual(b.call('GET', '/api/workspace/ask/' + '9' * 23)[0], 404)

    def test_guest_health_has_no_code_fingerprint(self):
        with serving(True) as (base, _):
            b = Browser(base)
            self.assertEqual(b.call('POST', '/api/auth/demo', {})[0], 200)
            self.assertEqual(b.call('GET', '/api/ontology/health')[1], {'model_ready': False, 'demo': True, 'demo_ask': False})
            admin = Browser(base)
            self.assertEqual(admin.call('POST', '/api/auth/login', {'username': 'root', 'password': GOOD})[0], 200)
            self.assertIn('running', admin.call('GET', '/api/ontology/health')[1])


class MemberInput(unittest.TestCase):
    def test_get_with_a_number_no_table_can_hold_is_answered_400(self):
        with serving(False) as (base, _):
            b = Browser(base)
            self.assertEqual(b.call('POST', '/api/auth/login', {'username': 'root', 'password': GOOD})[0], 200)
            big = '9' * 23
            for digits in (big, '9' * 5000):   # more than sqlite holds; more than Python turns into a number at all
                for path in (f'/api/workspace/assistant/turns/{digits}', f'/api/workspace/groups?dataset=x&version={digits}', f'/api/workspace/pipelines/x/runs/{digits}',
                             f'/api/workspace/pipelines/x/versions?from={digits}&to=1', f'/api/workspace/ask/{digits}'):
                    status, body = b.call('GET', path)
                    self.assertIn(status, (400, 404), path[:60])   # answered, never a dropped connection
                    self.assertIn('error', body)
                status, body = b.call('POST', f'/api/workspace/assistant/turns/{digits}/delete', {})
                self.assertIn(status, (400, 404))


class FeedbackAddress(unittest.TestCase):
    def test_public_health_carries_a_configured_address_only(self):
        with serving(True) as (base, _):
            self.assertNotIn('feedback_url', Browser(base).call('GET', '/api/ontology/health')[1])
            with mock.patch.dict('os.environ', {'ONTOPOC_FEEDBACK_URL': 'https://example.com/ask'}):
                self.assertEqual(Browser(base).call('GET', '/api/ontology/health')[1], {'ok': True, 'demo': True, 'demo_ask': False, 'feedback_url': 'https://example.com/ask'})
            for unusable in ('javascript:alert(1)', 'https://user:secret@example.com/ask', 'https://example.com/a b', 'https://'):
                with mock.patch.dict('os.environ', {'ONTOPOC_FEEDBACK_URL': unusable}):
                    self.assertNotIn('feedback_url', Browser(base).call('GET', '/api/ontology/health')[1], unusable)
        with serving(False) as (base, _), mock.patch.dict('os.environ', {'ONTOPOC_FEEDBACK_URL': 'https://example.com/ask'}):
            self.assertEqual(Browser(base).call('GET', '/api/ontology/health')[1], {'ok': True})   # not a demo: a stranger learns only that the service is up


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
            conn.execute('CREATE TABLE IF NOT EXISTS dashboard_last (dashboard_id INTEGER NOT NULL, component_id TEXT NOT NULL, reader INTEGER NOT NULL, picks TEXT NOT NULL, '
                         'result_json TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (dashboard_id, component_id, reader, picks))')
            conn.execute("INSERT INTO dashboard_last(dashboard_id, component_id, reader, picks, result_json, at) VALUES (1, 'c1', ?, '{}', '{}', 'now')", (g['id'],))
        conn.execute('UPDATE user SET created_at = ? WHERE id = ?', ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec='seconds'), old['id']))
        self.assertEqual(demo.cleanup(conn, datetime.now(timezone.utc)), 1)
        ids = [u['id'] for u in accounts.list_users(conn)]
        self.assertIn(new['id'], ids)
        self.assertNotIn(old['id'], ids)
        for table, col in (('session', 'user_id'), ('notice', 'user_id'), ('demo_guest', 'user_id'), ('dashboard_last', 'reader')):
            self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} = ?', (old['id'],)).fetchone()[0], 0, table)
            self.assertEqual(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {col} = ?', (new['id'],)).fetchone()[0], 1, table)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM ask_budget').fetchone()[0], 1)
        self.assertEqual(accounts.list_users(conn)[0]['username'], 'root')

    def test_a_deleted_guests_id_is_never_given_out_again(self):
        conn = open_workspace(':memory:')
        accounts.create_user(conn, 'root', 'Root', 'admin', GOOD, 'test', must_change=False)
        old = demo.create_guest(conn, '1.1.1.1')
        conn.execute('UPDATE user SET created_at = ? WHERE id = ?', ((datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(timespec='seconds'), old['id']))
        self.assertEqual(demo.cleanup(conn, datetime.now(timezone.utc)), 1)
        self.assertGreater(demo.create_guest(conn, '2.2.2.2')['id'], old['id'])


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
            self.assertTrue((target / demo.READY).is_file())   # written last: the entrypoint seeds again when it is missing
            with self.assertRaises(SystemExit):
                demo.seed(target)
            with self.assertRaises(SystemExit):
                demo.seed(Path(tmp), force_fresh=True)   # not a demo folder (no marker): refuses to wipe
            demo.seed(target, force_fresh=True)

    def test_a_seed_that_stops_early_can_be_started_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'demo'
            with self.assertRaises(BaseException):
                demo.seed(target, admin_name='demo-builder')   # the second account's name is taken: the seed stops after the first
            self.assertTrue((target / demo.MARKER).is_file())   # the folder is already marked as this seed's, so --force-fresh may wipe it
            self.assertFalse((target / demo.READY).exists())
            demo.seed(target, force_fresh=True)
            self.assertTrue((target / demo.READY).is_file())

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

    def test_no_model_ask_is_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'demo'
            demo.seed(target)
            server = make_server(port=0, gateway=None, output_dir=target, demo=True)
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            try:
                guest = Browser(f'http://127.0.0.1:{server.server_port}')
                self.assertEqual(guest.call('POST', '/api/auth/demo', {})[0], 200)
                for _ in range(2):
                    self.assertEqual(guest.call('POST', '/api/workspace/ask', {'question': 'How many orders are there?'})[0], 503)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
            conn = open_workspace(target / 'workspace.sqlite')
            try:
                has = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'ask_budget'").fetchone()
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM ask_budget').fetchone()[0] if has else 0, 0)   # the guest's hour and the demo's day are both untouched
            finally:
                conn.close()

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


@contextmanager
def seeded():
    """A demo workspace built by the seed, served in demo mode without a model: (base address, admin password, folder)."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / 'demo'
        result = demo.seed(target)
        server = make_server(port=0, gateway=None, output_dir=target, demo=True)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', result['password'], target
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def signed_in(base, password, name='demo-admin', lang='zh-CN'):
    admin = Browser(base, lang)
    assert admin.call('POST', '/api/auth/login', {'username': name, 'password': password})[0] == 200
    return admin


def a_guest(base, lang='zh-CN'):
    guest = Browser(base, lang)
    assert guest.call('POST', '/api/auth/demo', {})[0] == 200
    return guest


class DemoStory(unittest.TestCase):
    """What a first-time visitor meets: one answer on the board, and one definition that waits for a second look, named with who it waits for and nothing else."""

    @classmethod
    def setUpClass(cls):
        cls._seeded = seeded()
        cls.base, cls.password, cls.folder = cls._seeded.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._seeded.__exit__(None, None, None)

    def test_the_view_says_what_it_counts_with_all_its_conditions_together(self):
        admin = signed_in(self.base, self.password)
        view = admin.call('GET', '/api/workspace/types/order/views')[1]['views'][0]
        self.assertEqual(view['caliber'], 'status_code 不是 0（New）、4（Cancelled）、5（Refunded）：算进 1 Paid、2 Shipped、3 Delivered')   # not "不是 0（New）：算进 … 4 Cancelled、5 Refunded"

    def test_a_guest_sees_the_customer_type_waiting_and_for_whom_and_nothing_of_why(self):
        guest = a_guest(self.base)
        listed = {t['id']: t for t in guest.call('GET', '/api/workspace/types')[1]['types']}
        self.assertEqual(listed['order']['state'], 'confirmed')
        customer = listed['customer']
        self.assertEqual((customer['name'], customer['state'], customer['waiting'], customer['waiting_for'], customer['rows'], customer['dataset']),
                         ('Customer', 'needs_look', True, ['demo-admin'], None, None))
        reason = signed_in(self.base, self.password).call('GET', '/api/workspace/types/customer')[1]['reason']
        self.assertTrue(reason)   # the admin reads why it waits; the guest does not
        self.assertNotIn(reason, json.dumps(customer, ensure_ascii=False))

    def test_a_guests_question_on_a_waiting_type_is_refused_before_the_model_saying_only_that_it_waits(self):
        """Until the owner decides D9 a viewer is told only that the answer waits for a confirmation: not the type, not who (VIEWERS_TOLD_WHAT_WAITS turns names on)."""
        admin = signed_in(self.base, self.password)
        detail = admin.call('GET', '/api/workspace/types/customer')[1]
        secrets = [detail['reason'], 'C012', '不唯一', 'customers_update', '41']   # why it waits quotes the data: its keys, counts and file
        guest = a_guest(self.base)
        for question in ('按 Customer 城市看有效订单金额', 'Valid order amount by customer city'):
            status, body = guest.call('POST', '/api/workspace/ask', {'question': question})   # no model on this server: the refusal does not need one
            self.assertEqual(status, 200, body)
            self.assertEqual((body['status'], body['refusal']['kind']), ('refused', 'unsettled'), question)
            [line] = body['refusal']['definitions']
            self.assertEqual((line['kind'], line['state'], line['waiting']), ('type', 'needs_look', True))
            self.assertLessEqual(set(line), {'kind', 'state', 'waiting', 'text'})
            said = json.dumps({k: body[k] for k in ('reason', 'refusal', 'steps', 'definitions', 'types', 'datasets')}, ensure_ascii=False)
            for secret in secrets:
                self.assertNotIn(secret, said, question)
            self.assertNotRegex(said, r'\d', question)   # no count, no key, no version
            for word in ('Customer', 'customer', 'demo-admin'):
                self.assertNotIn(word, said, question)
            self.assertTrue('再确认' in body['reason'] or 'confirm' in body['reason'], body['reason'])
            again = guest.call('GET', f'/api/workspace/ask/{body["id"]}')[1]   # reopened from the history, it still says the same, and no more
            self.assertNotIn('withheld', again)
            self.assertEqual(again['refusal'], body['refusal'])

    def keep(self, guest, question, record):
        """A saved question of this guest's, written as the service keeps one."""
        uid = guest.call('GET', '/api/auth/me')[1]['user']['id']
        conn = sqlite3.connect(self.folder / 'workspace.sqlite')
        try:
            cur = conn.execute('INSERT INTO qa_question(user_id, asked_by, question, asked_at, status, answer_json, definitions_json, dataset_versions_json, types_json) '
                               "VALUES (?, 'guest', ?, '2026-11-20T00:00:00+00:00', ?, ?, ?, '{}', ?)",
                               (uid, question, record['status'], json.dumps(record, ensure_ascii=False), json.dumps(record['definitions']), json.dumps(record['types'])))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def test_a_guest_reopening_an_old_answer_on_a_type_that_now_waits_is_told_only_that_it_waits(self):
        reason = signed_in(self.base, self.password).call('GET', '/api/workspace/types/customer')[1]['reason']
        guest = a_guest(self.base)
        # asked while Customer was confirmed; an upload has since sent it back for a second look
        answered = self.keep(guest, 'How many customers?', {'status': 'answered', 'reason': None, 'answer': {'total': 40}, 'types': [{'id': 'customer', 'name': 'Customer'}],
                                                            'definitions': [{'id': 'objtype:customer', 'version': 1, 'name': 'Customer'}], 'datasets': {}, 'steps': [],
                                                            'named': ['objtype:customer']})
        # a refusal kept while its asker could read why (a builder since made a viewer): the reasons in it are not this guest's now
        builders = self.keep(guest, 'Customer by city', {'status': 'refused', 'reason': f'Not answered: {reason}', 'types': [], 'definitions': [], 'datasets': {}, 'steps': [],
                                                         'refusal': {'kind': 'unsettled', 'definitions': [{'id': 'objtype:customer', 'kind': 'type', 'name': 'Customer', 'state': 'needs_look',
                                                                                                           'reason': reason, 'who_can_confirm': ['demo-admin'], 'text': reason}]},
                                                         'named': ['objtype:customer']})
        for qid in (answered, builders):
            status, body = guest.call('GET', f'/api/workspace/ask/{qid}')
            self.assertEqual(status, 200, body)
            said = json.dumps(body, ensure_ascii=False)
            self.assertIn('withheld', body, said)
            for secret in (reason, 'C012', '41', 'not unique', '不唯一'):
                self.assertNotIn(secret, said, qid)
            self.assertNotIn('changed', body)
            self.assertNotIn('answer', body)
            for word in ('Customer', 'demo-admin'):   # what a fresh question says: only that it waits (D9 not widened)
                self.assertNotIn(word, json.dumps({k: body[k] for k in ('reason', 'withheld')}, ensure_ascii=False), qid)

    def test_the_board_still_answers_while_the_customer_type_waits(self):
        guest = a_guest(self.base)
        board = guest.call('GET', '/api/workspace/dashboards')[1]['dashboards'][0]
        body = guest.call('POST', '/api/workspace/dashboards/data', {'id': board['id'], 'bar': {}})[1]
        by_id = {c['id']: c for c in body['components']}
        self.assertTrue(all(c['status'] == 'ok' for c in by_id.values()), body)
        self.assertEqual([by_id[k]['result']['value'] for k in ('valid_amount', 'valid_count', 'all_amount')], [119810, 107, 162960])


class DemoRefusalLimits(unittest.TestCase):
    def test_a_type_nobody_ever_confirmed_is_not_named_to_a_guest(self):
        with seeded() as (base, password, _):
            admin = signed_in(base, password)
            status, body = admin.call('POST', '/api/workspace/types', {'english_name': 'sale', 'name': '销售单', 'dataset': 'orders', 'key': ['order_id'],
                                                                         'properties': [{'column': 'order_id'}, {'column': 'amount'}]})
            self.assertEqual(status, 200, body)
            guest = a_guest(base)
            status, body = guest.call('POST', '/api/workspace/ask', {'question': '销售单一共有多少？'})
            self.assertEqual(status, 503, body)   # on to the model (there is none here): nothing said of a type the guest may not see


if __name__ == '__main__':
    unittest.main()
