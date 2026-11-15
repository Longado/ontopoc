"""Live sources and schedules, against a fake database (no network): a table arrives typed and says where it came from; a scheduled pull that shifts the codes
sends what was confirmed on them back to "needs another look"; the password is in no page, log or error; a source with datasets cannot be deleted; a schedule that
is still running is not started again. The connection is a stand-in for the driver's: source_connect.OPENERS is replaced for the length of a test."""
import base64
import json
import ssl
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from ontology_poc_generator import accounts, ontology_server, source_connect, source_vault
from ontology_poc_generator.source_connect import Connection, SourceError, check_host, describe, records_of, resolve, scrub, text_of
from ontology_poc_generator.workspace_schedules import next_slot, slot_at_or_before
from ontology_poc_generator.workspace_sources import claimed
from ontology_poc_generator.workspace_store import open_workspace
from tests.test_access import GOOD
from tests.test_two_person import SigningTestCase

PASSWORD = 'hunter2-Secret!'
MEANINGS = [{'value': '0', 'label': '已交付'}, {'value': '1', 'label': '生产中'}, {'value': '2', 'label': '已取消'}]
ORDER_TYPE = {'english_name': 'order', 'name': '订单', 'dataset': '订单', 'key': ['订单号'], 'description': '客户下的一张订单',
              'properties': [{'column': '订单号'}, {'column': '金额'}, {'column': '状态码', 'enum': True}], 'enums': {'状态码': MEANINGS}}
COLUMNS = ['订单号', '下单日期', '金额', '状态码', '发货日', '更新时间']


def orders(codes=(0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2)) -> list[tuple]:
    """Twelve orders as a database hands them over: the date is a varchar, the money a decimal, the ship date a real date and the update time one with a zone."""
    return [(f'A{i:03d}', f'2026-01-{i + 1:02d}', Decimal(f'{100 + i}.50'), code, date(2026, 2, i + 1), datetime(2026, 3, 1, 8, i, tzinfo=timezone(timedelta(hours=8))))
            for i, code in enumerate(codes)]


class FakeDb(Connection):
    """A database of a few tables held in memory."""

    def __init__(self, tables: dict, writes=(False, '')):
        self.data, self.can_write, self.closed = tables, writes, 0

    def tables(self):
        return [{'name': n, 'kind': '表', 'rows': len(rows), 'approx': True, 'supported': True, 'note': None} for n, (_, rows) in self.data.items()]

    def writes(self):
        return self.can_write

    def read(self, table, limit):
        if table not in self.data:
            raise SourceError(f'数据源里没有“{table}”这张表，或这个账号读不了它')
        columns, rows = self.data[table]
        return list(columns), list(rows)[:limit]

    def close(self):
        self.closed += 1


class VaultTests(unittest.TestCase):
    def test_a_sealed_password_opens_with_the_key_beside_it_and_not_otherwise(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            sealed = source_vault.seal(Path(one), PASSWORD)
            self.assertNotIn(PASSWORD, sealed)
            self.assertNotEqual(sealed, source_vault.seal(Path(one), PASSWORD))   # a fresh nonce each time
            self.assertEqual(source_vault.unseal(Path(one), sealed), PASSWORD)
            self.assertEqual((Path(one) / source_vault.KEY_FILE).stat().st_mode & 0o777, 0o600)
            with self.assertRaises(source_vault.VaultError):
                source_vault.unseal(Path(two), sealed)   # another directory has another key
            tampered = sealed[:-6] + ('AAAAAA' if not sealed.endswith('AAAAAA') else 'BBBBBB')
            with self.assertRaises(source_vault.VaultError):
                source_vault.unseal(Path(one), tampered)


class GuardTests(unittest.TestCase):
    def test_metadata_and_link_local_addresses_are_refused_and_localhost_is_not(self):
        for host in ('169.254.169.254', '169.254.0.1', 'fd00:ec2::254', '[fd00:ec2::254]', 'fe80::1', '::ffff:169.254.169.254', 'metadata.google.internal', 'Metadata.Google.Internal.', '100.100.100.200'):
            with self.assertRaises(SourceError, msg=host):
                check_host(host)
        for host in ('localhost', '127.0.0.1', '10.0.0.5', 'db.example.com'):
            check_host(host)
        self.assertIn(resolve('localhost', 5432), ('127.0.0.1', '::1'))
        with self.assertRaises(SourceError):
            resolve('2852039166', 5432)   # 169.254.169.254 written as one number: only what the name resolves to shows it

    def test_a_name_that_resolves_to_a_blocked_address_is_refused_at_connect_time(self):
        answer = [(2, 1, 6, '', ('169.254.169.254', 5432))]
        with mock.patch.object(source_connect.socket, 'getaddrinfo', return_value=answer), self.assertRaises(SourceError):
            source_connect.connect('postgresql', 'db.example.com', 5432, 'd', 'u', 'p')

    def test_a_missing_driver_is_named_and_the_service_still_runs(self):
        with mock.patch.object(source_connect.importlib, 'import_module', side_effect=ImportError('no module')):
            with self.assertRaises(SourceError) as caught:
                source_connect.connect('postgresql', 'localhost', 5432, 'd', 'u', 'p')
        self.assertIn('pg8000', str(caught.exception))

    def test_a_missing_driver_says_the_server_cannot_reach_that_kind_yet_and_what_an_operator_installs(self):
        for kind, package, label in (('postgresql', 'pg8000', 'PostgreSQL'), ('mysql', 'PyMySQL', 'MySQL')):
            with mock.patch.object(source_connect.importlib, 'import_module', side_effect=ImportError('no module')):
                with self.assertRaises(SourceError) as caught:
                    source_connect.connect(kind, 'localhost', 5432, 'd', 'u', 'p')
            text = str(caught.exception)
            self.assertIn(f'这台服务器还连不了 {label}', text)
            self.assertIn("pip install 'ontopoc[sources]'", text)
            self.assertIn(package, text)
            self.assertIn('运维', text)
            self.assertEqual(caught.exception.public, text)   # the same words for a builder: there is nothing of the database in them

    def test_a_wrong_host_is_still_reported_as_a_wrong_host_when_the_driver_is_missing(self):
        with mock.patch.object(source_connect.importlib, 'import_module', side_effect=ImportError('no module')), \
                mock.patch.object(source_connect.socket, 'getaddrinfo', side_effect=source_connect.socket.gaierror('no such host')):
            with self.assertRaises(SourceError) as caught:
                source_connect.connect('postgresql', 'no-such-host.invalid', 5432, 'd', 'u', 'p')
        self.assertIn('找不到这个主机名', str(caught.exception))
        self.assertNotIn('pip install', str(caught.exception))

    def test_saving_refuses_a_number_or_a_name_that_resolves_to_a_blocked_address_and_leaves_an_unknown_name_to_the_test(self):
        blocked = [(2, 1, 6, '', ('169.254.169.254', 5432))]
        with mock.patch.object(source_connect.socket, 'getaddrinfo', return_value=blocked):
            for host in ('2852039166', '0xa9fea9fe', '169.254.169.254.nip.io', 'db.example.com'):
                with self.assertRaises(SourceError, msg=host) as caught:
                    source_connect.screen_host(host, 5432)
                self.assertIn('元数据', str(caught.exception))
        with mock.patch.object(source_connect.socket, 'getaddrinfo', side_effect=source_connect.socket.gaierror('no such host')):
            source_connect.screen_host('db-not-yet-in-dns.example.com', 5432)   # not an error: the address may be made later, and the test says so
        source_connect.screen_host('localhost', 5432)


class ScrubTests(unittest.TestCase):
    def test_a_driver_error_loses_the_password_wherever_it_is(self):
        pg = Exception({'S': 'FATAL', 'C': 'XX000', 'M': f'could not parse "postgresql://u:{PASSWORD}@h/d"'})
        self.assertNotIn(PASSWORD, describe(pg, PASSWORD))
        self.assertIn('***', describe(pg, PASSWORD))
        self.assertEqual(describe(Exception({'C': '28P01', 'M': f'password authentication failed {PASSWORD}'}), PASSWORD), '用户名或密码不对，或这个账号不让从这台机器登录')
        self.assertNotIn(PASSWORD, describe(Exception(1064, f"syntax near '{PASSWORD}'"), PASSWORD))
        self.assertNotIn(PASSWORD, describe(RuntimeError(f'dsn host=h password={PASSWORD}'), PASSWORD))
        self.assertEqual(scrub('a b ab', 'a'), '*** b ab')   # a one-letter password is hidden where it stands alone, not inside other words

    def test_what_pymysql_really_raises_is_named_for_what_happened(self):
        """Shapes seen against a live MySQL 8: PyMySQL wraps a failed certificate check in its own (2003, ...) error with the ssl error as the implicit context (not
        __cause__), and a refused dial is the OS error (61, 'Connection refused'), whose args also look like (number, text)."""
        try:
            try:
                refused = ssl.SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain')
                refused.verify_message = 'self-signed certificate in certificate chain'   # the field a real handshake failure fills in
                raise refused
            except ssl.SSLError:
                raise Exception(2003, "Can't connect to MySQL server on 'h' ([SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed)")
        except Exception as wrapped:
            text = describe(wrapped, PASSWORD)
        self.assertIn('TLS 证书验证没通过', text)
        self.assertIn('self-signed certificate', text)
        self.assertEqual(describe(ConnectionRefusedError(61, 'Connection refused'), PASSWORD), '连接被对方拒绝：地址或端口不对，或数据库没有在听')

    def test_connect_keeps_nothing_of_the_drivers_own_exception(self):
        def refusing(host, address, port, database, user, password, tls):
            raise Exception(f'bad dsn password={password}')
        with mock.patch.dict(source_connect.OPENERS, {'postgresql': refusing}):
            with self.assertRaises(SourceError) as caught:
                source_connect.connect('postgresql', 'localhost', 5432, 'd', 'u', PASSWORD)
        self.assertNotIn(PASSWORD, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)   # a traceback printed later does not show the driver's text either


class ValueTests(unittest.TestCase):
    def test_cells_become_the_text_the_workspace_types_from(self):
        self.assertEqual([text_of(v) for v in (Decimal('1E+2'), Decimal('12.50'), 3, 0.00001, True, None, date(2026, 1, 5), datetime(2026, 1, 5, 8, 30),
                                               datetime(2026, 1, 5, 8, 30, tzinfo=timezone(timedelta(hours=8))), {'b': 1, 'a': '中'})],
                         ['100', '12.50', '3', '0.00001', 'true', None, '2026-01-05', '2026-01-05 08:30:00', '2026-01-05 00:30:00', '{"a": "中", "b": 1}'])

    def test_a_mysql_time_is_written_as_the_clock_reading_it_is(self):
        """PyMySQL hands a TIME over as a timedelta, and MySQL's TIME runs from -838:59:59 to 838:59:59: str(timedelta) would write '-1 day, 22:30:00' and '34 days, 22:59:59'."""
        self.assertEqual([text_of(v) for v in (timedelta(hours=10, minutes=11, seconds=12), -timedelta(hours=1, minutes=30), timedelta(hours=838, minutes=59, seconds=59),
                                               timedelta(seconds=1, microseconds=500000), timedelta(0))],
                         ['10:11:12', '-01:30:00', '838:59:59', '00:00:01.500000', '00:00:00'])

    def test_closing_a_capped_mysql_read_leaves_nothing_for_the_driver_to_drain(self):
        """A pull stopped by the byte cap drops the connection with rows still unread; PyMySQL must not then try to read the rest off the closed socket when the cursor is
        collected (it printed a traceback to the service's log each time)."""
        result = mock.Mock(unbuffered_active=True)
        cursor = mock.Mock(description=[('id',)], _result=result)
        cursor.fetchmany.return_value = [(1,)]
        raw = mock.Mock()
        raw.cursor.return_value = cursor
        live = source_connect.MySql(raw, PASSWORD)
        live._cursors = mock.Mock()
        columns, batches = live._batches('SELECT 1')
        next(batches)
        batches.close()
        raw.close.assert_called_once()
        self.assertFalse(result.unbuffered_active)

    def test_a_column_of_bytes_is_left_out_and_named(self):
        records, left_out = records_of(['id', 'photo'], [(1, b'\x00'), (2, None)])
        self.assertEqual((records, left_out), ([{'id': '1'}, {'id': '2'}], ['photo']))


class ClockTests(unittest.TestCase):
    TAIPEI = 'Asia/Taipei'

    def s(self, **fields):
        return {'cadence': 'daily', 'minute': 30, 'hour': 8, 'weekday': None, 'tz': self.TAIPEI, **fields}

    def test_the_latest_slot_is_in_the_schedules_time_zone(self):
        now = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)   # 09:00 in Taipei
        self.assertEqual(slot_at_or_before(self.s(), now), datetime(2026, 11, 14, 0, 30, tzinfo=timezone.utc))   # 08:30 Taipei today
        self.assertEqual(slot_at_or_before(self.s(hour=9, minute=30), now), datetime(2026, 11, 13, 1, 30, tzinfo=timezone.utc))   # 09:30 has not come: yesterday's
        self.assertEqual(slot_at_or_before(self.s(cadence='hourly', hour=None, minute=15), now), datetime(2026, 11, 14, 0, 15, tzinfo=timezone.utc))
        saturday = slot_at_or_before(self.s(cadence='weekly', weekday=5, hour=7, minute=0), now)   # 2026-11-14 is a Saturday: 07:00 Taipei today
        self.assertEqual(saturday, datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(slot_at_or_before(self.s(cadence='weekly', weekday=4, hour=7, minute=0), now), datetime(2026, 11, 12, 23, 0, tzinfo=timezone.utc))   # Friday's

    def test_the_next_slot_is_the_one_after_now(self):
        now = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(next_slot(self.s(), now), datetime(2026, 11, 14, 0, 30, tzinfo=timezone.utc) + timedelta(days=1))
        self.assertEqual(next_slot(self.s(cadence='hourly', hour=None, minute=15), now), datetime(2026, 11, 14, 1, 15, tzinfo=timezone.utc))


class SourceCase(SigningTestCase):
    """What the service tests below share: a fake database, the service with its server, and what was said to whom."""

    @contextmanager
    def service(self, first_admin=True, gateway=None, **more):
        """The service with its server kept, so a test can run the schedules at a time of its own."""
        with tempfile.TemporaryDirectory() as out:
            out = Path(out)
            server = ontology_server.make_server(port=0, gateway=gateway, output_dir=out, **more)
            conn = open_workspace(out / 'workspace.sqlite')
            accounts.create_user(conn, 'root', '管理员', 'admin', GOOD, 'host', must_change=False)
            conn.close()
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
            thread.start()
            self.server = server
            try:
                yield f'http://127.0.0.1:{server.server_port}', out
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def setUp(self):
        super().setUp()
        self.db = FakeDb({'orders': (COLUMNS, orders())})
        self.opened = []
        patcher = mock.patch.dict(source_connect.OPENERS, {'postgresql': self.open_db, 'mysql': self.open_db})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.said = []   # everything the service answered, to look for the password in

    def open_db(self, host, address, port, database, user, password, tls):
        self.opened.append((address, port, database, user, password, host, tls))
        if self.db is None:
            raise Exception(f'FATAL: connection to {address} with password={password} failed')
        return self.db

    def ask(self, client, method, path, payload=None):
        status, body = getattr(client, method)(path, payload) if method == 'post' else client.get(path)
        self.said.append(json.dumps(body, ensure_ascii=False))
        return status, body

    def team(self, base):
        team = self.people(base, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        status, body = self.ask(team['admin'], 'post', '/api/workspace/sources', {'name': '订单库', 'kind': 'postgresql', 'host': 'localhost', 'port': 15432, 'database': 'shop',
                                                                              'username': 'reader', 'password': PASSWORD})
        self.assertEqual(status, 200, body)
        return team

    def pull(self, client, **more):
        status, body = self.ask(client, 'post', '/api/workspace/sources/pull', {'source': '订单库', 'table': 'orders', 'name': '订单', **more})
        self.assertEqual(status, 200, body)
        return body['run']

    def detail(self, client, name='order'):
        status, body = self.ask(client, 'get', f'/api/workspace/types/{name}')
        self.assertEqual(status, 200, body)
        return body

    def meanings(self, detail):
        return next(p for p in detail['properties'] if p['column'] == '状态码')['meanings']

    def confirm(self, client, column=None):
        shown = self.meanings(self.detail(client)) if column else self.detail(client)
        return self.ask(client, 'post', '/api/workspace/types/confirm', {'id': 'order', 'version': shown['version'], 'seen': shown['seen'], **({'column': column} if column else {})})

    def dump(self, out) -> bytes:
        """Every byte of the workspace file and of everything else the service wrote: the password must be in none of it."""
        conn = sqlite3.connect(out / 'workspace.sqlite')
        conn.execute('PRAGMA wal_checkpoint(FULL)')
        conn.close()
        return b''.join(p.read_bytes() for p in sorted(out.rglob('*')) if p.is_file() and p.name != source_vault.KEY_FILE)



class SourceServerTests(SourceCase):
    def test_a_table_with_varchar_dates_and_decimal_money_arrives_typed_and_says_where_it_came_from(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann = team['ann']
            status, body = self.ask(team['admin'], 'post', '/api/workspace/sources/test', {'name': '订单库'})
            self.assertEqual((status, body['status'], body['tables']), (200, 'ok', [{'name': 'orders', 'kind': '表', 'rows': 12, 'approx': True, 'supported': True, 'note': None, 'dataset': None, 'hidden': False}]))
            self.assertEqual(self.opened[-1][:4], ('127.0.0.1', 15432, 'shop', 'reader'))   # the address that was checked is the one that was dialled
            self.assertEqual(self.opened[-1][4], PASSWORD)   # the sealed password comes back whole to the driver
            run = self.pull(ann)
            self.assertEqual((run['status'], run['rows'], run['dataset'], run['version'], run['changed'], run['who'], run['reason']), ('success', 12, '订单', 1, True, 'Ann', 'manual'))
            self.assertTrue(run['started_at'] and run['finished_at'])
            status, page = self.ask(ann, 'get', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95')
            self.assertEqual(status, 200)
            kinds = {c['name']: c['type'] for c in page['columns']}
            self.assertEqual(kinds, {'订单号': 'text', '下单日期': 'date', '金额': 'decimal', '状态码': 'integer', '发货日': 'date', '更新时间': 'datetime'})
            self.assertEqual(page['origin'], 'source:订单库/orders')
            self.assertEqual(page['versions'][0]['source'], {'name': '订单库', 'table': 'orders', 'left_out': []})
            self.assertTrue(page['version_at'])   # 拉取于 T
            self.assertEqual(page['preview']['rows'][0][1:], ['2026-01-01', '100.50', '0', '2026-02-01', '2026-03-01 00:00:00'])   # +08:00 read as UTC
            status, listed = self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')
            self.assertEqual([(t['name'], t['dataset']) for t in listed['tables']], [('orders', '订单')])

    def test_the_password_is_in_no_page_error_log_or_file(self):
        with self.service() as (base, out):
            team = self.team(base)
            admin, ann = team['admin'], team['ann']
            self.ask(admin, 'post', '/api/workspace/sources/test', {'name': '订单库'})
            self.pull(ann)
            self.db = None   # now every connection fails, and the driver's own message holds the password
            status, tested = self.ask(admin, 'post', '/api/workspace/sources/test', {'name': '订单库'})
            self.assertEqual((status, tested['status']), (200, 'failed'))
            self.assertIn('***', tested['note'])
            run = self.pull(ann)
            self.assertEqual(run['status'], 'failed')
            self.assertEqual(run['error'], source_connect.GENERIC)   # a builder reads the general reason; the database's words (scrubbed) are the admin's
            self.assertIn('***', self.ask(admin, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/runs')[1]['runs'][0]['error'])
            status, body = self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')
            self.assertEqual((status, body['error']), (502, source_connect.GENERIC))
            self.ask(admin, 'get', '/api/workspace/sources')
            self.ask(admin, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93')
            self.ask(admin, 'get', '/api/workspace/schedules')
            self.ask(admin, 'post', '/api/workspace/sources/update', {'name': '订单库', 'host': 'localhost', 'port': 15432, 'database': 'shop', 'username': 'reader', 'password': PASSWORD + '2'})
            self.assertEqual(sum(PASSWORD in s for s in self.said), 0)
            self.assertNotIn(PASSWORD.encode(), self.dump(out))
            self.assertNotIn((PASSWORD + '2').encode(), self.dump(out))
            self.assertEqual(self.ask(admin, 'get', '/api/workspace/sources')[1]['sources'][0]['has_password'], True)
            self.assertNotIn('secret', self.said[-1])

    def test_only_an_admin_sets_a_source_up_or_sees_where_it_is_and_a_viewer_sees_nothing(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, vera = team['ann'], team['vera']
            new = {'name': 'x', 'kind': 'mysql', 'host': 'db', 'database': 'd', 'username': 'u', 'password': 'p'}
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/sources', new)[0], 403)
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/sources/test', {'name': '订单库'})[0], 403)
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/sources/delete', {'name': '订单库'})[0], 403)
            self.assertEqual(self.ask(vera, 'get', '/api/workspace/sources')[0], 403)
            self.assertEqual(self.ask(vera, 'post', '/api/workspace/sources/pull', {'source': '订单库', 'table': 'orders'})[0], 403)
            builder_view = self.ask(ann, 'get', '/api/workspace/sources')[1]['sources'][0]
            self.assertEqual(sorted(builder_view), ['can_write', 'kind', 'kind_label', 'name', 'status', 'status_at', 'status_label', 'status_note', 'tables', 'tls'])   # no host, port, database or account
            admin_view = self.ask(team['admin'], 'get', '/api/workspace/sources')[1]['sources'][0]
            self.assertEqual((admin_view['host'], admin_view['port'], admin_view['database'], admin_view['username'], admin_view['local']), ('localhost', 15432, 'shop', 'reader', True))

    def test_a_source_that_points_at_a_metadata_address_is_not_saved_and_a_host_with_a_scheme_is_not_either(self):
        with self.service() as (base, out):
            admin = self.people(base)['admin']
            base_fields = {'name': 'x', 'kind': 'postgresql', 'port': 5432, 'database': 'd', 'username': 'u', 'password': 'p'}
            for host in ('169.254.169.254', 'metadata.google.internal', 'fd00:ec2::254'):
                status, body = self.ask(admin, 'post', '/api/workspace/sources', {**base_fields, 'host': host})
                self.assertEqual(status, 400, host)
                self.assertIn('元数据', body['error'])
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/sources', {**base_fields, 'host': 'postgres://u:p@db/d'})[0], 400)
            self.assertEqual(self.ask(admin, 'get', '/api/workspace/sources')[1], {'sources': []})

    def test_the_test_warns_when_the_account_can_write(self):
        with self.service() as (base, out):
            admin = self.team(base)['admin']
            self.db = FakeDb({'orders': (COLUMNS, orders())}, writes=(True, '能改某些表的数据'))
            status, body = self.ask(admin, 'post', '/api/workspace/sources/test', {'name': '订单库'})
            self.assertEqual((body['status'], body['can_write']), ('ok', True))
            self.assertIn('不是只读的', body['note'])
            self.assertTrue(self.ask(admin, 'get', '/api/workspace/sources')[1]['sources'][0]['can_write'])

    def test_a_scheduled_pull_that_shifts_the_status_codes_sends_the_confirmed_meanings_back_for_another_look(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.pull(ann)
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/types', ORDER_TYPE)[0], 200)
            for column in ('状态码', None):
                status, body = self.confirm(bob, column)
                self.assertEqual(status, 200, body)
            self.assertEqual(self.meanings(self.detail(bob))['state'], 'confirmed')
            start = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
            status, made = self.ask(ann, 'post', '/api/workspace/schedules', {'name': '订单每小时', 'kind': 'source', 'target': '订单库', 'cadence': 'hourly', 'minute': 0, 'tz': 'Asia/Taipei'})
            self.assertEqual(status, 200, made)
            self.assertEqual((made['when'], made['targets'], made['latest_run'], made['last_change']), ('每小时的第 0 分（Asia/Taipei）', ['订单'], None, None))
            self.assertEqual(self.server.run_schedules(datetime.now(timezone.utc)), [])   # made just now: nothing to run before its next slot
            self.db = FakeDb({'orders': (COLUMNS, orders(codes=(1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3)))})   # 0 is gone, 3 is new: the codes shifted by one
            this_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)   # the schedule's slots are on the hour: stay clear of the edge of one
            runs = self.server.run_schedules(this_hour + timedelta(hours=1, minutes=1))
            self.assertEqual([(r['status'], r['reason'], r['who'], r['changed'], r['version']) for r in runs], [('success', 'schedule', '定时：订单每小时（Ann）', True, 2)])
            self.assertEqual(runs[0]['detail']['flagged_count'], 2)   # the meanings and the type that reads them
            detail = self.detail(bob)
            self.assertEqual((self.meanings(detail)['state'], detail['state']), ('needs_look', 'needs_look'))
            self.assertIn('新出现 3', self.meanings(detail)['reason'])
            self.assertIn('定时：订单每小时', self.meanings(detail)['reason'])   # the version says who pulled it
            conn = sqlite3.connect(out / 'workspace.sqlite')
            self.assertEqual(conn.execute("SELECT cause FROM element_state WHERE element_id LIKE 'enum:%'").fetchall(), [('data',)])   # shown as 数据变了
            conn.close()
            status, schedule = self.ask(ann, 'get', '/api/workspace/schedules')
            only = schedule['schedules'][0]
            self.assertEqual((only['latest_run']['status'], only['last_change']['by'], only['last_change']['version']), ('success', '定时：订单每小时（Ann）', 2))
            self.assertEqual(self.server.run_schedules(this_hour + timedelta(hours=1, minutes=30)), [])   # the same slot is not acted on twice

    def test_a_pull_of_data_that_did_not_change_writes_no_version_and_says_so(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.pull(ann)
            status, body = self.ask(ann, 'post', '/api/workspace/sources/refresh', {'dataset': '订单'})
            self.assertEqual(status, 200, body)
            self.assertEqual((body['run']['status'], body['run']['changed'], body['run']['version']), ('success', False, 1))
            self.assertEqual(len(self.ask(ann, 'get', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95')[1]['versions']), 1)

    def test_a_name_that_is_taken_needs_a_mode_and_update_by_key_changes_only_the_rows_that_differ(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.pull(ann)
            status, body = self.ask(ann, 'post', '/api/workspace/sources/pull', {'source': '订单库', 'table': 'orders', 'name': '订单'})
            self.assertEqual(status, 200)
            self.assertEqual(body['run']['status'], 'success')   # the table is already read as this dataset: this is a refresh
            self.db = FakeDb({'orders': (COLUMNS, orders()), 'extra': (['k', 'v'], [('1', 'a')])})
            status, body = self.ask(ann, 'post', '/api/workspace/sources/pull', {'source': '订单库', 'table': 'extra', 'name': '订单'})
            self.assertEqual(status, 400)
            self.assertIn('已经从另一张表读来', body['error'])   # a dataset that is the reading of one table is not written by another
            upload = {'filename': '手工表.csv', 'content_base64': base64.b64encode('k,v\n1,a\n'.encode()).decode()}
            uploaded = ann.post('/api/workspace/datasets/upload', {'files': [upload]})
            self.assertEqual(uploaded[0], 200, uploaded[1])
            status, body = self.ask(ann, 'post', '/api/workspace/sources/pull', {'source': '订单库', 'table': 'extra', 'name': '手工表'})
            self.assertEqual(status, 400)
            self.assertIn('已经有叫“手工表”的数据集', body['error'])   # one that is not: the mode (update by key or overwrite) is asked for, never guessed
            changed = orders()
            changed[0] = (*changed[0][:2], Decimal('999.00'), *changed[0][3:])
            self.db = FakeDb({'orders': (COLUMNS, changed + [('A999', '2026-04-01', Decimal('5.00'), 1, date(2026, 4, 2), datetime(2026, 4, 1))])})
            status, body = self.ask(ann, 'post', '/api/workspace/sources/pull', {'source': '订单库', 'table': 'orders', 'mode': 'update_by_key', 'key_columns': ['订单号']})
            self.assertEqual(body['run']['status'], 'success', body)
            self.assertEqual((body['run']['detail']['changes']['changed'], body['run']['detail']['changes']['added']), (1, 1))
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95')[1]['rows'], 13)

    def test_a_source_with_a_dataset_cannot_be_deleted_until_the_dataset_is_gone_and_its_schedules_go_with_it(self):
        with self.service() as (base, out):
            team = self.team(base)
            admin, ann = team['admin'], team['ann']
            self.pull(ann)
            self.ask(ann, 'post', '/api/workspace/schedules', {'name': '每天', 'kind': 'source', 'target': '订单库', 'cadence': 'daily', 'time': '08:30', 'tz': 'Asia/Taipei'})
            status, body = self.ask(admin, 'post', '/api/workspace/sources/delete', {'name': '订单库'})
            self.assertEqual(status, 409)
            self.assertIn('「订单」', body['error'])
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/datasets/delete', {'name': '订单'})[0], 200)
            status, body = self.ask(admin, 'post', '/api/workspace/sources/delete', {'name': '订单库'})
            self.assertEqual((status, body), (200, {'name': '订单库', 'schedules': 1}))
            self.assertEqual(self.ask(admin, 'get', '/api/workspace/schedules')[1], {'schedules': []})

    def test_a_pull_still_running_is_not_started_again_by_a_schedule_and_is_refused_by_hand(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.pull(ann)
            self.ask(ann, 'post', '/api/workspace/schedules', {'name': '每小时', 'kind': 'source', 'target': '订单库', 'cadence': 'hourly', 'minute': 0, 'tz': 'UTC'})
            with claimed(('source', '订单库', 'orders')):
                runs = self.server.run_schedules(datetime.now(timezone.utc) + timedelta(hours=2))
                self.assertEqual([(r['status'], r['error']) for r in runs], [('skipped', '上一次拉取还没结束，这次跳过')])
                status, body = self.ask(ann, 'post', '/api/workspace/sources/refresh', {'dataset': '订单'})
                self.assertEqual((status, '正在拉取' in body['error']), (400, True))

    def test_a_failed_scheduled_pull_is_logged_once_and_not_retried_every_minute(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            self.pull(ann)
            self.ask(ann, 'post', '/api/workspace/schedules', {'name': '每小时', 'kind': 'source', 'target': '订单库', 'cadence': 'hourly', 'minute': 0, 'tz': 'UTC'})
            self.db = None
            later = datetime.now(timezone.utc) + timedelta(hours=2)
            self.assertEqual([r['status'] for r in self.server.run_schedules(later)], ['failed'])
            self.assertEqual(self.server.run_schedules(later + timedelta(minutes=1)), [])
            runs = self.ask(ann, 'get', '/api/workspace/schedules/1/runs')[1]['runs']
            self.assertEqual([(r['status'], PASSWORD in str(r)) for r in runs], [('failed', False)])

    def test_a_schedule_is_made_for_what_exists_and_only_a_pipeline_can_wait_for_its_upstream(self):
        with self.service() as (base, out):
            ann = self.team(base)['ann']
            def make(**more):
                return self.ask(ann, 'post', '/api/workspace/schedules', {'name': 's', 'kind': 'source', 'target': '订单库', 'cadence': 'hourly', 'minute': 0, 'tz': 'UTC', **more})
            self.pull(ann)
            self.assertIn('上游', make(cadence='upstream')[1]['error'])
            self.assertEqual(make(tz='Mars/Base')[0], 400)
            self.assertEqual(make(minute=60)[0], 400)
            self.assertEqual(make(cadence='daily', time='25:00')[0], 400)
            self.assertEqual(make(scope=['nothing'])[0], 400)
            self.assertEqual(make(kind='pipeline', target='没有这条')[0], 404)   # a pipeline that is not there and one kept from the person read alike
            self.assertEqual(make()[0], 200)
            self.assertEqual(make()[0], 400)   # the name is taken
            status, off = self.ask(ann, 'post', '/api/workspace/schedules/update', {'id': 1, 'enabled': False})
            self.assertEqual((status, off['enabled'], off['next_at']), (200, False, None))
            self.assertEqual(self.server.run_schedules(datetime.now(timezone.utc) + timedelta(hours=5)), [])   # switched off


class PipelineScheduleTests(SourceCase):
    """A confirmed pipeline run again when the dataset it reads has a new version."""
    SPEC = {'steps': [{'id': 'o', 'type': 'input', 'dataset': '订单'}, {'id': 'out', 'type': 'output', 'from': 'o', 'name': '订单副本', 'key': {'columns': ['订单号']}}]}

    def put_forward(self, ann):
        status, body = self.ask(ann, 'post', '/api/workspace/pipelines', {'name': '订单副本', 'description': '订单原样复制', 'spec': self.SPEC})
        self.assertEqual(status, 200, body)

    def confirm_pipeline(self, bob):
        shown = self.ask(bob, 'get', '/api/workspace/pipelines/%E8%AE%A2%E5%8D%95%E5%89%AF%E6%9C%AC')[1]
        status, body = self.ask(bob, 'post', '/api/workspace/pipelines/confirm', {'id': '订单副本', 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})
        self.assertEqual(status, 200, body)

    def test_a_pipeline_waits_for_its_upstream_runs_after_a_new_version_and_not_before(self):
        with self.service() as (base, out):
            team = self.team(base)
            ann, bob = team['ann'], team['bob']
            self.pull(ann)
            self.put_forward(ann)
            status, body = self.ask(ann, 'post', '/api/workspace/schedules', {'name': '订单副本跟着跑', 'kind': 'pipeline', 'target': '订单副本', 'cadence': 'upstream', 'tz': 'UTC'})
            self.assertEqual(status, 400)   # not confirmed yet: it would write with nobody having looked
            self.assertIn('只有已确认的管道', body['error'])
            self.confirm_pipeline(bob)
            status, made = self.ask(ann, 'post', '/api/workspace/schedules', {'name': '订单副本跟着跑', 'kind': 'pipeline', 'target': '订单副本', 'cadence': 'upstream', 'tz': 'UTC'})
            self.assertEqual((status, made['when'], made['targets']), (200, '上游更新时', ['订单副本']))
            self.assertEqual(self.server.run_schedules(), [])   # nothing new upstream yet
            self.db = FakeDb({'orders': (COLUMNS, orders(codes=(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)))})
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/sources/refresh', {'dataset': '订单'})[1]['run']['version'], 2)
            runs = self.server.run_schedules()
            self.assertEqual([(r['status'], r['reason'], r['kind'], r['dataset'], r['changed']) for r in runs], [('success', 'upstream', 'pipeline', '订单副本', True)])
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95%E5%89%AF%E6%9C%AC')[1]['version'], 1)
            self.assertEqual(self.server.run_schedules(), [])   # the same input versions are not run twice
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/pipelines/%E8%AE%A2%E5%8D%95%E5%89%AF%E6%9C%AC/runs')[1]['runs'][0]['who'], '定时：订单副本跟着跑（Ann）')


if __name__ == '__main__':
    unittest.main()
