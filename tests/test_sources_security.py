"""The stage 5 security review, finding by finding (reviews/stage5-security-2026-11-14.md): what a builder may learn of datasets and pipelines kept from them (H1),
whose authority a schedule runs with (H2), where the password may be sent (M1), TLS (M2), what a builder reads of the database (M3), the limits on what one click can
ask of it (M4), a scheduled pipeline's model calls (M5), a table read into a dataset that belongs to another source (M6) and the lows (L1 to L5).
Each test names its finding. The database is the fake of test_sources; the service is real."""
import json
import socket
import sqlite3
import ssl
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

from ontology_poc_generator import source_connect, source_vault, workspace_sources
from ontology_poc_generator.source_connect import GENERIC, SourceError, check_host, describe, resolve
from ontology_poc_generator.workspace_schedules import tick
from ontology_poc_generator.workspace_store import open_workspace
from tests import test_sources as base
from tests.test_sources import COLUMNS, PASSWORD, FakeDb, SourceCase, orders

SECRET_KEY = 'A-SECRET-KEY-999'
HIDDEN_TYPE = {'english_name': 'secret_order', 'name': '机密订单', 'dataset': 'ds_hidden', 'key': ['订单号'], 'description': '只有 Ann 看得到', 'properties': [{'column': '订单号'}, {'column': '金额'}]}
SOURCE = {'name': 'shopdb', 'kind': 'postgresql', 'host': 'localhost', 'port': 15432, 'database': 'shop', 'username': 'reader', 'password': PASSWORD}


class Fixture(SourceCase):
    """Ann, Bob (builders), Vera (viewer) and the admin, a source called shopdb and its one table pulled into the dataset ds_hidden, which a type only Ann may see reads."""

    def hidden_team(self, base_url):
        team = self.people(base_url, 'ann', 'bob', 'vera', roles={'vera': 'viewer'})
        self.assertEqual(self.ask(team['admin'], 'post', '/api/workspace/sources', SOURCE)[0], 200)
        users = {u['username']: u['id'] for u in team['admin'].get('/api/users')[1]['users']}
        self.ann_id, self.bob_id = users['ann'], users['bob']
        self.assertEqual(self.pull(team['ann'], source='shopdb', name='ds_hidden', mode='update_by_key', key_columns=['订单号'])['status'], 'success')
        self.assertEqual(self.ask(team['ann'], 'post', '/api/workspace/types', HIDDEN_TYPE)[0], 200)
        self.assertEqual(self.ask(team['admin'], 'post', '/api/workspace/permissions', {'type': 'secret_order', 'visible_to': [self.ann_id]})[0], 200)
        self.assertEqual(self.ask(team['bob'], 'get', '/api/workspace/datasets/ds_hidden')[0], 404)   # kept from Bob: the premise of every test below
        return team

    def new_row(self):
        changed = orders() + [(SECRET_KEY, '2026-04-01', Decimal('5.00'), 1, date(2026, 4, 2), datetime(2026, 4, 1))]
        self.db = FakeDb({'orders': (COLUMNS, changed)})

    def said_to(self, client, *paths):
        """Everything these routes answer this person, as one string."""
        return ' '.join(json.dumps(self.ask(client, 'get', p)[1], ensure_ascii=False) for p in paths)


class HiddenDatasetTests(Fixture):
    def test_h1_a_builder_reads_neither_the_name_nor_the_keys_of_a_dataset_kept_from_them_in_any_list_or_log(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            ann, bob = team['ann'], team['bob']
            self.new_row()
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/schedules', {'name': 'A', 'kind': 'source', 'target': 'shopdb', 'cadence': 'hourly', 'minute': 0, 'tz': 'UTC'})[0], 200)
            run = self.ask(ann, 'post', '/api/workspace/sources/refresh', {'dataset': 'ds_hidden'})[1]['run']
            self.assertIn(SECRET_KEY, json.dumps(run))   # Ann, who may see it, does read the key
            seen = self.said_to(bob, '/api/workspace/sources', '/api/workspace/sources/shopdb', '/api/workspace/sources/shopdb/tables', '/api/workspace/sources/shopdb/runs',
                                '/api/workspace/schedules', '/api/workspace/schedules/1/runs')
            self.assertNotIn(SECRET_KEY, seen)
            self.assertNotIn('ds_hidden', seen)
            self.assertNotIn('机密订单', seen)
            tables = self.ask(bob, 'get', '/api/workspace/sources/shopdb/tables')[1]['tables']
            self.assertEqual([(t['name'], t['dataset'], t['hidden']) for t in tables], [('orders', None, True)])   # the table is there, read as something Bob may not see
            self.assertEqual(self.ask(bob, 'get', '/api/workspace/sources/shopdb')[1]['tables'], [])
            self.assertIn('ds_hidden', self.said_to(ann, '/api/workspace/sources/shopdb'))
            self.assertIn(SECRET_KEY, self.said_to(team['admin'], '/api/workspace/sources/shopdb/runs'))   # and so does the admin

    def test_h1_a_builder_cannot_pull_the_table_of_a_hidden_dataset_and_is_not_told_its_name(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            status, body = self.ask(team['bob'], 'post', '/api/workspace/sources/pull', {'source': 'shopdb', 'table': 'orders', 'name': 'mine'})
            self.assertEqual(status, 400)
            self.assertNotIn('ds_hidden', body['error'])
            status, body = self.ask(team['bob'], 'post', '/api/workspace/sources/refresh', {'dataset': 'ds_hidden'})
            self.assertEqual(status, 400)
            self.assertEqual(body['error'], self.ask(team['bob'], 'post', '/api/workspace/sources/refresh', {'dataset': 'no_such'})[1]['error'])   # the same words for a dataset that is not there

    def test_h1_who_may_see_the_run_details_of_a_dataset_they_can_see_gets_the_keys_but_not_the_names_of_the_definitions_it_sent_back(self):
        with self.service() as (base_url, out):
            team = self.team(base_url)
            ann, bob = team['ann'], team['bob']
            self.pull(ann)
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/types', base.ORDER_TYPE)[0], 200)
            for column in ('状态码', None):
                self.assertEqual(self.confirm(bob, column)[0], 200)
            self.db = FakeDb({'orders': (COLUMNS, orders(codes=(1, 2, 3, 1, 2, 3, 1, 2, 3, 1, 2, 3)))})
            run = self.ask(ann, 'post', '/api/workspace/sources/refresh', {'dataset': '订单'})[1]['run']
            self.assertEqual(run['detail']['flagged_count'], 2)
            self.assertNotIn('flagged', run['detail'])   # a builder is told how many, not which (a definition's name may be one they may not see)
            as_admin = self.ask(team['admin'], 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/runs')[1]['runs'][0]
            self.assertEqual(sorted(as_admin['detail']['flagged']), ['enum:order:状态码', 'objtype:order'])


class ScheduleAuthorityTests(Fixture):
    def make(self, client, **more):
        return self.ask(client, 'post', '/api/workspace/schedules', {'name': 'S', 'kind': 'source', 'target': 'shopdb', 'cadence': 'hourly', 'minute': 0, 'tz': 'UTC', **more})

    def test_h2_a_builder_cannot_schedule_a_table_whose_dataset_is_kept_from_them(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            status, body = self.make(team['bob'], scope=['orders'])
            self.assertEqual(status, 400)
            self.assertNotIn('ds_hidden', json.dumps(body))
            nothing = self.make(team['bob'], name='T', scope=['no_such_table'])
            self.assertEqual((nothing[0], nothing[1]['error']), (status, body['error']))   # a table that is not there and one kept from them read alike
            self.assertEqual(self.make(team['ann'], name='U', scope=['orders'])[0], 200)

    def test_h2_a_builder_cannot_schedule_a_pipeline_kept_from_them_and_cannot_tell_it_from_one_that_is_not_there(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            ann, bob = team['ann'], team['bob']
            spec = {'steps': [{'id': 'o', 'type': 'input', 'dataset': 'ds_hidden'}, {'id': 'out', 'type': 'output', 'from': 'o', 'name': 'copy_hidden', 'key': {'columns': ['订单号']}}]}
            self.assertEqual(self.ask(ann, 'post', '/api/workspace/pipelines', {'name': 'p_hidden', 'description': 'x', 'spec': spec})[0], 200)
            self.assertEqual(self.ask(bob, 'get', '/api/workspace/pipelines/p_hidden')[0], 404)
            kept = self.make(bob, kind='pipeline', target='p_hidden', cadence='daily', time='08:00')
            gone = self.make(bob, kind='pipeline', target='p_none', cadence='daily', time='08:00')
            self.assertEqual((kept[0], kept[1]), (gone[0], gone[1]))
            self.assertEqual(kept[0], 404)

    def test_h2_only_the_person_who_made_a_schedule_or_an_admin_can_change_switch_off_or_delete_it(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            made = self.make(bob, name='bobs')[1]
            self.assertEqual(made['mine'], True)
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/schedules')[1]['schedules'][0]['mine'], False)
            for path, payload in (('/update', {'id': made['id'], 'enabled': False}), ('/update', {'id': made['id'], 'cadence': 'daily', 'time': '09:00'}), ('/delete', {'id': made['id']})):
                self.assertEqual(self.ask(ann, 'post', '/api/workspace/schedules' + path, payload)[0], 403, path)
            self.assertEqual(self.ask(bob, 'post', '/api/workspace/schedules/update', {'id': made['id'], 'enabled': False})[0], 200)
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/schedules/update', {'id': made['id'], 'enabled': True})[0], 200)
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/schedules/delete', {'id': made['id']})[0], 200)

    def test_h2_a_schedule_runs_as_the_person_who_made_it_and_the_record_says_who(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            ann = team['ann']
            self.new_row()
            self.make(ann, name='Anns')
            this_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            runs = self.server.run_schedules(this_hour + timedelta(hours=2))
            self.assertEqual([(r['status'], r['who']) for r in runs], [('success', '定时：Anns（Ann）')])
            schedule = self.ask(ann, 'get', '/api/workspace/schedules')[1]['schedules'][0]
            self.assertEqual(schedule['last_change']['by'], '定时：Anns（Ann）')
            self.assertEqual(schedule['created_by'], 'Ann')

    def test_h2_a_schedule_whose_maker_has_lost_sight_of_the_dataset_is_skipped_with_a_reason_and_writes_nothing(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/permissions', {'type': 'secret_order', 'visible_to': [self.ann_id, self.bob_id]})[0], 200)
            self.assertEqual(self.make(bob, name='Bobs')[0], 200)
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/permissions', {'type': 'secret_order', 'visible_to': [self.ann_id]})[0], 200)   # Bob is kept from it again
            self.new_row()
            this_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            runs = self.server.run_schedules(this_hour + timedelta(hours=2))
            self.assertEqual([r['status'] for r in runs], ['skipped'])
            self.assertIn('看不到', runs[0]['error'])
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/datasets/ds_hidden')[1]['version'], 1)   # nothing was written

    def test_h2_a_schedule_whose_maker_is_disabled_or_no_longer_builds_is_skipped(self):
        with self.service() as (base_url, out):
            team = self.hidden_team(base_url)
            ann, bob, admin = team['ann'], team['bob'], team['admin']
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/permissions', {'type': 'secret_order', 'visible_to': [self.ann_id, self.bob_id]})[0], 200)
            made = self.make(bob, name='Bobs')[1]
            self.ask(admin, 'post', '/api/users/disable', {'id': self.bob_id, 'disabled': True})
            self.new_row()
            this_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            runs = self.server.run_schedules(this_hour + timedelta(hours=2))
            self.assertEqual([(r['status'], '停用' in r['error']) for r in runs], [('skipped', True)])
            self.ask(admin, 'post', '/api/users/disable', {'id': self.bob_id, 'disabled': False})
            self.ask(admin, 'post', '/api/users/update', {'id': self.bob_id, 'role': 'viewer'})
            runs = self.server.run_schedules(this_hour + timedelta(hours=3))
            self.assertEqual([r['status'] for r in runs], ['skipped'])
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/datasets/ds_hidden')[1]['version'], 1)


class ConnectionSettingsTests(SourceCase):
    def update(self, client, **more):
        return self.ask(client, 'post', '/api/workspace/sources/update', {'name': '订单库', 'host': 'localhost', 'port': 15432, 'database': 'shop', 'username': 'reader', **more})

    def test_m1_changing_where_the_password_goes_needs_the_password_again(self):
        with self.service() as (base_url, out):
            admin = self.team(base_url)['admin']
            for change in ({'host': 'attacker.example'}, {'port': 15433}, {'database': 'other'}, {'username': 'someone'}):
                status, body = self.update(admin, **change)
                self.assertEqual(status, 400, change)
                self.assertIn('密码', body['error'])
            self.assertEqual(self.ask(admin, 'get', '/api/workspace/sources')[1]['sources'][0]['host'], 'localhost')   # nothing changed
            self.assertEqual(self.update(admin, host='db.example.com', password='a new one')[0], 200)
            self.assertEqual(self.update(admin, host='db.example.com')[0], 200)   # the same address again, no change, no password asked
            self.assertEqual(self.update(admin, host='db.example.com', tls='none')[0], 200)   # the encryption setting does not send the password anywhere new

    def test_m2_a_source_names_whether_its_connection_is_encrypted_and_the_driver_is_told(self):
        with self.service() as (base_url, out):
            team = self.team(base_url)
            admin, ann = team['admin'], team['ann']
            fields = {'kind': 'postgresql', 'database': 'd', 'username': 'u', 'password': 'p'}
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/sources', {**fields, 'name': 'near', 'host': 'localhost'})[1]['tls'], 'none')   # a database on this machine: a local tool
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/sources', {**fields, 'name': 'far', 'host': 'db.example.com'})[1]['tls'], 'required')   # anywhere else: encrypted unless said otherwise
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/sources', {**fields, 'name': 'bad', 'host': 'db.example.com', 'tls': 'maybe'})[0], 400)
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/sources', {**fields, 'name': 'secure', 'host': 'localhost', 'tls': 'required'})[1]['tls'], 'required')
            self.assertEqual({s['name']: s['tls'] for s in self.ask(ann, 'get', '/api/workspace/sources')[1]['sources']}, {'订单库': 'none', 'near': 'none', 'far': 'required', 'secure': 'required'})
            self.ask(admin, 'post', '/api/workspace/sources/test', {'name': 'near'})
            self.assertEqual(self.opened[-1][6], 'none')
            self.ask(admin, 'post', '/api/workspace/sources/test', {'name': 'secure'})
            self.assertEqual(self.opened[-1][6], 'required')

    def test_m2_the_connection_checks_the_certificate_and_the_name_and_says_so_when_it_cannot(self):
        context = source_connect._tls_context()
        self.assertEqual((context.verify_mode, context.check_hostname), (ssl.CERT_REQUIRED, True))
        failure = ssl.SSLCertVerificationError(1, 'certificate verify failed')
        failure.verify_message = 'self-signed certificate'
        text = describe(_wrapped(failure), 'pw')
        self.assertIn('TLS 证书验证没通过', text)
        self.assertIn('self-signed', text)
        self.assertIn('不支持 TLS', describe(Exception('Server refuses SSL'), 'pw'))
        with self.assertRaises(SourceError):
            source_connect.connect('postgresql', 'localhost', 5432, 'd', 'u', 'p', 'sometimes')

    def test_m2_the_drivers_get_the_checked_address_dialled_and_the_name_for_the_certificate_and_a_context_that_verifies(self):
        class Raw:
            def __init__(self, **kwargs):
                self.kwargs, self.statements, self.autocommit = kwargs, [], False
                self.connected_with = None

            def connect(self, sock=None):
                self.connected_with = sock

            def cursor(self, *a):
                raw = self

                class Cursor:
                    description = None

                    def execute(self, sql):
                        raw.statements.append(sql)

                    def close(self):
                        pass
                return Cursor()

        made = []

        def fake_connect(**kwargs):
            made.append(Raw(**kwargs))
            return made[-1]
        driver = mock.Mock(connect=fake_connect)
        sock = object()
        with mock.patch.object(source_connect, '_driver', return_value=driver), mock.patch.object(source_connect, '_dial', return_value=sock) as dial, \
                mock.patch.object(source_connect.importlib, 'import_module', return_value=mock.Mock()):
            source_connect.Postgres.open('db.example.com', '10.0.0.5', 5432, 'd', 'u', 'p', 'required')
            source_connect.Postgres.open('db.example.com', '10.0.0.5', 5432, 'd', 'u', 'p', 'none')
            source_connect.MySql.open('db.example.com', '10.0.0.5', 3306, 'd', 'u', 'p', 'required')
            source_connect.MySql.open('db.example.com', '10.0.0.5', 3306, 'd', 'u', 'p', 'none')
        self.assertEqual([c.args for c in dial.call_args_list], [('10.0.0.5', 5432), ('10.0.0.5', 5432), ('10.0.0.5', 3306), ('10.0.0.5', 3306)])
        pg_on, pg_off, my_on, my_off = made
        self.assertEqual((pg_on.kwargs['host'], pg_on.kwargs['sock']), ('db.example.com', sock))
        self.assertIsInstance(pg_on.kwargs['ssl_context'], ssl.SSLContext)
        self.assertIs(pg_off.kwargs['ssl_context'], False)
        self.assertIsInstance(my_on.kwargs['ssl'], ssl.SSLContext)
        self.assertEqual((my_on.kwargs['host'], my_on.connected_with), ('db.example.com', sock))
        self.assertIs(my_off.kwargs['ssl_disabled'], True)
        self.assertIn('SET SESSION TRANSACTION READ ONLY', my_on.statements)
        self.assertIn(f'SET SESSION max_execution_time = {source_connect.STATEMENT_SECONDS * 1000}', my_on.statements)   # the server stops a long SELECT, not only the socket
        self.assertIn(f'SET statement_timeout = {source_connect.STATEMENT_SECONDS * 1000}', pg_on.statements)

    def test_m3_a_builder_reads_a_status_word_and_a_general_reason_where_an_admin_reads_the_database_s_own_words(self):
        with self.service() as (base_url, out):
            team = self.team(base_url)
            admin, ann = team['admin'], team['ann']
            self.update(admin, host='db-internal-7.corp.example', password=PASSWORD)
            real = socket.getaddrinfo

            def lookup(host, *more, **named):   # the name of the database is not found; the test's own requests to the service are
                if host == 'db-internal-7.corp.example':
                    raise socket.gaierror
                return real(host, *more, **named)
            with mock.patch.object(source_connect.socket, 'getaddrinfo', side_effect=lookup):
                tested = self.ask(admin, 'post', '/api/workspace/sources/test', {'name': '订单库'})[1]
                self.assertIn('找不到这个主机名', tested['note'])
                self.assertNotIn('db-internal-7', tested['note'])   # not even the admin is told the host twice
                listed = self.ask(ann, 'get', '/api/workspace/sources')[1]['sources'][0]
                self.assertEqual((listed['status'], listed['status_note']), ('failed', GENERIC))
                status, body = self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')
                self.assertEqual((status, body['error']), (502, GENERIC))
                run = self.pull(ann)
                self.assertEqual((run['status'], run['error']), ('failed', GENERIC))
                admin_run = self.ask(admin, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/runs')[1]['runs'][0]
                self.assertIn('找不到这个主机名', admin_run['error'])
            self.update(admin, host='localhost', password=PASSWORD)
            self.db = None
            tested = self.ask(admin, 'post', '/api/workspace/sources/test', {'name': '订单库'})[1]
            self.assertIn('***', tested['note'])   # what the driver said, scrubbed, for the admin
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/sources')[1]['sources'][0]['status_note'], GENERIC)
            self.assertEqual(sum(PASSWORD in s for s in self.said), 0)

    def test_m3_the_resolver_names_no_host_and_marks_its_error_for_everyone_else_as_general(self):
        with mock.patch.object(source_connect.socket, 'getaddrinfo', side_effect=socket.gaierror):
            with self.assertRaises(SourceError) as caught:
                resolve('db-internal-7.corp.example', 5432)
        self.assertNotIn('db-internal-7', str(caught.exception))
        self.assertEqual(caught.exception.public, GENERIC)


def _wrapped(cause):
    error = Exception('wrapped')
    error.__cause__ = cause
    return error


class LimitTests(SourceCase):
    def test_m4_the_table_list_is_the_databases_estimate_labelled_so_cached_for_ten_minutes_and_not_asked_for_twice_at_once(self):
        with self.service() as (base_url, out):
            team = self.team(base_url)
            admin, ann = team['admin'], team['ann']
            self.db = FakeDb({'orders': (COLUMNS, orders())})
            counted = []
            real = self.db.tables
            self.db.tables = lambda: counted.append(1) or real()
            first = self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')[1]['tables']
            self.assertEqual((first[0]['rows'], first[0]['approx']), (12, True))
            for _ in range(3):
                self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')
            self.assertEqual(len(counted), 1)   # a builder's clicks do not each ask the database
            self.ask(admin, 'post', '/api/workspace/sources/test', {'name': '订单库'})
            self.assertEqual(len(counted), 2)   # a test is a fresh look
            with mock.patch.object(workspace_sources, 'TABLE_CACHE_SECONDS', -1):   # ten minutes later, as far as the cache can tell
                self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')
            self.assertEqual(len(counted), 3)   # and ten minutes later it is asked again
            self.ask(admin, 'post', '/api/workspace/sources/update', {'name': '订单库', 'host': 'localhost', 'port': 15432, 'database': 'shop', 'username': 'reader', 'tls': 'none'})
            self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')
            self.assertEqual(len(counted), 4)   # a changed connection is not answered from what the old one said

    def test_m4_a_second_request_for_the_list_while_one_runs_is_answered_from_the_cache_or_asked_to_wait(self):
        with self.service() as (base_url, out):
            ann = self.team(base_url)['ann']
            with workspace_sources.claimed(('source', '订单库', '')):
                status, body = self.ask(ann, 'get', '/api/workspace/sources/%E8%AE%A2%E5%8D%95%E5%BA%93/tables')
            self.assertEqual(status, 502)
            self.assertIn('稍等', body['error'])

    def test_m4_a_pull_over_the_byte_cap_is_refused_while_it_is_read_and_the_statement_is_closed(self):
        closed = []

        class Wide(source_connect._Sql):
            def __init__(self):
                super().__init__(None, '')

            def _listed(self):
                return [{'name': 't', 'parts': ('t',), 'kind': 'TABLE', 'rows': None}]

            def _quoted(self, parts):
                return parts[0]

            def _batches(self, sql):
                def batches():
                    try:
                        while True:
                            yield [('x' * 1_000_000,)] * 50
                    finally:
                        closed.append(True)
                return ['c'], batches()

        with mock.patch.object(source_connect, 'MAX_PULL_BYTES', 120 * 1024 * 1024):
            with self.assertRaises(SourceError) as caught:
                Wide().read('t', 10 ** 6)
        self.assertIn('MB', str(caught.exception))
        self.assertEqual(closed, [True])

    def test_m4_the_table_list_has_a_short_time_limit_of_its_own_and_gives_the_normal_one_back(self):
        class Probe(source_connect._Sql):
            def __init__(self):
                super().__init__(None, '')
                self.limits = []

            def _within(self, seconds):
                self.limits.append(seconds)

            def _listed(self):
                self.limits.append('listed')
                return []
        probe = Probe()
        probe.tables()
        self.assertEqual(probe.limits, [source_connect.LIST_SECONDS, 'listed', source_connect.STATEMENT_SECONDS])

    def test_m4_a_postgres_listing_estimates_from_the_catalogue_and_does_not_count_every_table(self):
        statements = []

        class Raw:
            def cursor(self):
                class Cursor:
                    description = [('a',)]

                    def execute(self, sql):
                        statements.append(sql)

                    def fetchall(self):
                        return [('public', 'orders', 'BASE TABLE', 1200), ('public', 'fresh', 'BASE TABLE', -1), ('public', 'v', 'VIEW', 0)]

                    def close(self):
                        pass
                return Cursor()
        found = source_connect.Postgres(Raw(), '').tables()
        self.assertEqual([(t['name'], t['rows'], t['approx']) for t in found], [('public.orders', 1200, True), ('public.fresh', None, True), ('public.v', None, True)])
        self.assertFalse(any('COUNT(' in s.upper() for s in statements))


class ScheduledAiTests(SourceCase):
    """M5: a scheduled run of a pipeline with an AI step goes the way a manual run goes: the model is asked first, outside the lock, at most the cap, and then the run
    writes from what is kept."""

    def setUp(self):
        super().setUp()
        from tests import test_pipeline_llm as llm_tests
        self.llm = llm_tests

    def confirmed_ai_pipeline(self, ann, bob):
        ll = self.llm
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': ll.TABLES})[0], 200)
        self.assertEqual(self.ask(ann, 'post', ll.PIPELINES, {'name': '工单分类', 'description': 'x', 'spec': ll.TICKET_SPEC})[0], 200)
        self.assertEqual(self.ask(ann, 'post', ll.PIPELINES + '/run', {'id': '工单分类'})[1]['status'], 'success')
        trial = ann.post(ll.PIPELINES + '/llm/trial', {'id': '工单分类', 'step': 'c', 'mode': 'sample', 'n': 20, 'seed': 3})[1]
        ann.post(ll.PIPELINES + '/llm/label', {'id': '工单分类', 'step': 'c', 'labels': [{'fields': t['fields'], 'expected': ll.keyword_answer(t['fields']['问题描述'])} for t in trial['trials']]})
        self.assertTrue(ann.post(ll.PIPELINES + '/llm/review', {'id': '工单分类', 'step': 'c'})[1]['passed'])
        shown = bob.get(ll.PIPELINES + '/%E5%B7%A5%E5%8D%95%E5%88%86%E7%B1%BB')[1]
        self.assertEqual(bob.post(ll.PIPELINES + '/confirm', {'id': '工单分类', 'version': shown['version'], 'seen': {'inputs': shown['inputs_now']}})[0], 200)

    def more_tickets(self, ann, n):
        import csv
        import io
        import base64
        rows = [dict(r) for r in self.llm.TICKETS]
        rows += [{**rows[0], '工单号': f'NEW{i}', '问题描述': f'新的问题描述 {i}：发热严重'} for i in range(n)]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        part = {'filename': '售后工单.csv', 'content_base64': base64.b64encode(out.getvalue().encode('utf-8')).decode(), 'target': '售后工单', 'mode': 'overwrite'}
        self.assertEqual(ann.post('/api/workspace/datasets/upload', {'files': [part]})[0], 200)

    def test_m5_a_scheduled_run_asks_the_model_only_for_the_new_rows_and_not_while_it_holds_the_lock_others_need(self):
        class Waits(self.llm.RowModel):
            def __init__(self):
                super().__init__()
                self.asking, self.let_go = threading.Event(), threading.Event()

            def complete_json(self, **more):
                self.asking.set()
                self.let_go.wait(30)
                return super().complete_json(**more)

        model = Waits()
        model.let_go.set()
        with self.service(gateway=model) as (base_url, out):
            team = self.people(base_url, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirmed_ai_pipeline(ann, bob)
            asked = len(model.requests)
            status, made = self.ask(ann, 'post', '/api/workspace/schedules', {'name': '分类跟着跑', 'kind': 'pipeline', 'target': '工单分类', 'cadence': 'upstream', 'tz': 'UTC'})
            self.assertEqual(status, 200, made)
            self.more_tickets(ann, 3)
            model.let_go.clear()
            model.asking.clear()
            done = {}
            worker = threading.Thread(target=lambda: done.update(runs=self.server.run_schedules()))
            worker.start()
            try:
                self.assertTrue(model.asking.wait(30))
                status, body = bob.post('/api/workspace/types', {'english_name': 'ticket', 'name': '售后工单', 'dataset': '售后工单', 'key': ['工单号'], 'properties': [{'column': '问题描述'}]})
                self.assertEqual((status, model.let_go.is_set()), (200, False), body)   # a write the lock would hold up goes through while the model is still answering
            finally:
                model.let_go.set()
                worker.join(60)
            self.assertEqual([(r['status'], r['reason']) for r in done['runs']], [('success', 'upstream')])
            self.assertEqual(len(model.requests) - asked, 3)   # only the new descriptions were asked: the kept answers served the rest

    def test_m5_a_scheduled_run_over_the_call_cap_is_refused_before_the_model_is_called(self):
        model = self.llm.RowModel()
        with self.service(gateway=model) as (base_url, out):
            team = self.people(base_url, 'ann', 'bob')
            ann, bob = team['ann'], team['bob']
            self.confirmed_ai_pipeline(ann, bob)
            self.ask(ann, 'post', '/api/workspace/schedules', {'name': '分类跟着跑', 'kind': 'pipeline', 'target': '工单分类', 'cadence': 'upstream', 'tz': 'UTC'})
            self.more_tickets(ann, 5)
            asked = len(model.requests)
            with mock.patch('ontology_poc_generator.pipeline_llm.MAX_RUN_CALLS', 2):
                runs = self.server.run_schedules()
            self.assertEqual([r['status'] for r in runs], ['failed'])
            self.assertIn('最多 2 次', runs[0]['error'])
            self.assertEqual(len(model.requests), asked)


class PullIntegrityTests(Fixture):
    def test_m6_a_second_source_cannot_write_into_a_dataset_bound_to_another_and_is_told_before_anything_is_written(self):
        with self.service() as (base_url, out):
            team = self.team(base_url)
            admin, ann = team['admin'], team['ann']
            self.pull(ann)
            self.assertEqual(self.ask(admin, 'post', '/api/workspace/sources', {**SOURCE, 'name': 'second'})[0], 200)
            before = self.ask(ann, 'get', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95')[1]['versions']
            status, body = self.ask(ann, 'post', '/api/workspace/sources/pull', {'source': 'second', 'table': 'orders', 'name': '订单', 'mode': 'overwrite'})
            self.assertEqual(status, 400, body)
            self.assertIn('已经从另一张表读来', body['error'])
            self.assertNotIn('订单库', body['error'])   # the other source is not named
            self.assertEqual(self.ask(ann, 'get', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95')[1]['versions'], before)   # no version was written
            self.assertEqual(sqlite3.connect(out / 'workspace.sqlite').execute("SELECT status FROM refresh_run WHERE target = 'second'").fetchall(), [])

    def test_m6_a_binding_that_cannot_be_written_takes_the_version_back_and_is_an_error_in_words_not_a_dropped_connection(self):
        with self.service() as (base_url, out):
            team = self.team(base_url)
            ann = team['ann']
            with mock.patch.object(workspace_sources, '_bound_elsewhere', return_value=None):   # the check before is beaten by another pull that lands in between
                self.pull(ann)
                self.assertEqual(self.ask(team['admin'], 'post', '/api/workspace/sources', {**SOURCE, 'name': 'second'})[0], 200)
                status, body = self.ask(ann, 'post', '/api/workspace/sources/pull', {'source': 'second', 'table': 'orders', 'name': '订单', 'mode': 'overwrite'})
            self.assertEqual(status, 200, body)
            self.assertEqual(body['run']['status'], 'failed')
            self.assertIn('另一张表', body['run']['error'])
            self.assertEqual(len(self.ask(ann, 'get', '/api/workspace/datasets/%E8%AE%A2%E5%8D%95')[1]['versions']), 1)   # rolled back with the binding

    def test_m6_an_error_nobody_expected_is_a_reply_in_json_and_leaves_no_run_marked_running(self):
        with self.service() as (base_url, out):
            ann = self.team(base_url)['ann']
            with mock.patch.object(workspace_sources, 'apply_upload', side_effect=sqlite3.OperationalError('disk I/O error')):
                status, body = self.ask(ann, 'post', '/api/workspace/sources/pull', {'source': '订单库', 'table': 'orders', 'name': '订单'})
            self.assertEqual(status, 200, body)
            self.assertEqual(body['run']['status'], 'failed')
            self.assertNotIn('disk I/O', body['run']['error'])
            self.assertEqual(sqlite3.connect(out / 'workspace.sqlite').execute("SELECT COUNT(*) FROM refresh_run WHERE status = 'running'").fetchone()[0], 0)
            with mock.patch('ontology_poc_generator.sources_http.list_sources', side_effect=RuntimeError('boom')):
                status, body = self.ask(ann, 'get', '/api/workspace/sources')
            self.assertEqual((status, 'boom' in json.dumps(body)), (500, False))

    def test_m6_two_sources_with_the_same_name_made_at_once_are_a_refusal_in_words(self):
        with self.service() as (base_url, out):
            admin = self.team(base_url)['admin']
            with mock.patch.object(workspace_sources, '_name_taken', return_value=False):
                status, body = self.ask(admin, 'post', '/api/workspace/sources', SOURCE | {'name': '订单库'})
            self.assertEqual(status, 400)
            self.assertIn('已经有叫', body['error'])


class LowTests(SourceCase):
    def test_l1_the_guard_unwraps_the_ipv4_address_a_nat64_6to4_or_compatible_address_carries_and_knows_two_more_clouds(self):
        for host in ('64:ff9b::a9fe:a9fe', '64:ff9b::169.254.169.254', '2002:a9fe:a9fe::', '2002:a9fe:a9fe:1::5', '::a9fe:a9fe', '168.63.129.16', '192.0.0.192', '::ffff:168.63.129.16'):
            with self.assertRaises(SourceError, msg=host):
                check_host(host)
        for host in ('64:ff9b::0a00:0005', '2002:0a00:0005::', '::1', '10.0.0.5', '::'):
            check_host(host)   # the same wrappings around an address that is allowed stay allowed

    def test_l2_a_postgres_table_whose_schema_or_name_has_a_dot_or_a_quote_is_listed_and_refused_not_guessed(self):
        class Raw:
            def cursor(self):
                class Cursor:
                    description = [('a',)]

                    def execute(self, sql):
                        self.sql = sql

                    def fetchall(self):
                        return [('a.b', 'c', 'BASE TABLE', 1), ('a', 'b.c', 'BASE TABLE', 1), ('a', 'we"ird', 'BASE TABLE', 1), ('a', 'plain', 'BASE TABLE', 1)]

                    def close(self):
                        pass
                return Cursor()
        postgres = source_connect.Postgres(Raw(), '')
        found = postgres.tables()
        self.assertEqual([(t['name'], t['supported']) for t in found], [('a.b.c', False), ('a.b.c', False), ('a.we"ird', False), ('a.plain', True)])
        self.assertIn('不支持', found[0]['note'])
        with self.assertRaises(SourceError):
            postgres.read('a.b.c', 10)

    def test_l3_the_delete_guard_reads_the_bindings_inside_the_transaction_that_deletes(self):
        with self.service() as (base_url, out):
            team = self.team(base_url)
            self.pull(team['ann'])
            conn = open_workspace(out / 'workspace.sqlite')
            with mock.patch.object(workspace_sources, '_bound', return_value=[]):   # what a read made before the transaction would have said
                with self.assertRaises(ValueError) as caught:
                    workspace_sources.delete_source(conn, '订单库', 'x')
            self.assertIn('「订单」', str(caught.exception))
            conn.close()

    def test_l4_the_key_is_made_whole_or_not_at_all_and_a_key_file_left_open_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source_vault.seal(directory, 'x')
            self.assertEqual([p.name for p in directory.iterdir()], [source_vault.KEY_FILE])   # no temporary file left behind
            key = directory / source_vault.KEY_FILE
            key.chmod(0o644)
            self.assertEqual(source_vault.unseal(directory, source_vault.seal(directory, 'again')), 'again')
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            results = []
            with tempfile.TemporaryDirectory() as second:
                threads = [threading.Thread(target=lambda: results.append(source_vault.seal(Path(second), 'x'))) for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                self.assertEqual({source_vault.unseal(Path(second), r) for r in results}, {'x'})   # eight first callers, one key

    def test_l5_one_schedule_that_cannot_be_worked_out_does_not_stop_the_ones_after_it(self):
        with self.service() as (base_url, out):
            ann = self.team(base_url)['ann']
            self.pull(ann)
            for name in ('a-good', 'z-good'):
                self.assertEqual(self.ask(ann, 'post', '/api/workspace/schedules', {'name': name, 'kind': 'source', 'target': '订单库', 'cadence': 'hourly', 'minute': 0, 'tz': 'UTC'})[0], 200)
            conn = sqlite3.connect(out / 'workspace.sqlite')
            conn.execute("UPDATE schedule SET tz = 'Not/AZone' WHERE name = 'a-good'")
            conn.commit()
            conn.close()
            self.db = FakeDb({'orders': (COLUMNS, orders(codes=(1,) * 12))})
            this_hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
            runs = self.server.run_schedules(this_hour + timedelta(hours=2))
            self.assertEqual([(r['status'], r['who'].startswith('定时：z-good')) for r in runs], [('success', True)])


if __name__ == '__main__':
    unittest.main()
