"""The workspace store keeps every imported row and records each check with the query it ran.

Expected numbers come from the planted fixtures (tests/fixtures/planted), counted by hand, not from the code under test.
"""
import base64
import json
from pathlib import Path
import sqlite3
import unittest

from ontology_poc_generator.company_ontology import build_company_ontology, verify_company_proposal
from ontology_poc_generator.company_sources import load_table_files
from ontology_poc_generator.object_rows import object_rows
from ontology_poc_generator.public_ontology import kept_attempts
from ontology_poc_generator.recognition import ModelCompletion
from ontology_poc_generator.workspace_store import (
    RowCountMismatch, check_bundle, check_key, current_dataset, import_records, open_workspace, records_sha256, element_state_writes, element_contents, set_element_states)

PLANTED = Path(__file__).parent / 'fixtures' / 'planted'


def planted_bundle() -> dict:
    return load_table_files([(p.name, p.read_bytes()) for p in sorted(PLANTED.glob('*.xlsx'))])


class WorkspaceStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = planted_bundle()

    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        self.datasets = {name: import_records(self.conn, name, s['records'], 'planted', records_sha256(s['records']))
                         for name, s in self.bundle['sources'].items()}

    def columns(self, dataset, column):
        row = self.conn.execute('SELECT inferred_type, distinct_count, missing_count, value_counts_json FROM "column" '
                                'WHERE dataset_id = ? AND name = ?', (self.datasets[dataset]['id'], column)).fetchone()
        return dict(zip(('type', 'distinct', 'missing', 'counts'), row))

    def key(self, dataset, *columns):
        return check_key(self.conn, self.datasets[dataset]['id'], list(columns))

    def test_the_shared_tables_exist_on_open(self):
        names = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertTrue({'dataset', 'column', 'element_state', 'check_result', 'log'} <= names)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO element_state(element_id, state, version) VALUES ('x', 'maybe', 1)")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO check_result(element_id, check_type, query, status) VALUES ('x', 't', 'q', 'green')")

    def test_every_row_is_stored_and_counted_by_a_query_on_what_was_written(self):
        expected = {'订单': 160, '客户': 31, '产品': 12, '售后工单': 45, '库存快照': 72, '订单承诺': 121, '交付统计': 12}
        for name, rows in expected.items():
            with self.subTest(name):
                d = self.datasets[name]
                table = self.conn.execute('SELECT table_name FROM dataset WHERE id = ?', (d['id'],)).fetchone()[0]
                self.assertEqual(self.conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0], rows)
                self.assertEqual((d['rows_in'], d['rows_stored'], d['version']), (rows, rows, 1))

    def test_a_status_code_stays_an_integer_and_keeps_its_counts(self):
        status = self.columns('订单', '状态码')
        self.assertEqual(status['type'], 'integer')
        self.assertEqual(json.loads(status['counts']), {'0': 96, '1': 48, '2': 16})
        self.assertEqual(status['distinct'], 3)

    def test_dates_months_and_decimals_are_typed_from_all_values(self):
        self.assertEqual(self.columns('订单', '下单日期')['type'], 'date')
        self.assertEqual(self.columns('库存快照', '快照月份')['type'], 'month')
        self.assertEqual(self.columns('交付统计', '交付天数P50')['type'], 'decimal')

    def test_value_counts_are_kept_only_for_columns_with_few_values(self):
        self.assertIsNone(self.columns('订单', '订单号')['counts'])   # 160 distinct
        self.assertIsNotNone(self.columns('订单', '状态码')['counts'])

    def test_type_inference(self):
        cases = {
            'yes_no': ['是', '否', '是', None], 'flags': ['Y', 'N'], 'words': ['true', 'False'], 'binary': ['0', '1', '1'],
            'mixed': ['1', '是'], 'one_flag': ['Y', 'Y'], 'wide': ['１２', '３'], 'arabic': ['٣', '٤'], 'stamp': ['2026-05-03T10:20:30', '2026-05-04'], 'padded': ['007', '010'],
            'money': ['1', '2.5'], 'bad_date': ['2026-13-45'], 'empty': [None, None], 'neg': ['-3', '4'],
        }
        records = [{k: (v[i] if i < len(v) else None) for k, v in cases.items()} for i in range(4)]
        d = import_records(self.conn, 'types', records, 't', 'sha-types')
        got = dict(self.conn.execute('SELECT name, inferred_type FROM "column" WHERE dataset_id = ?', (d['id'],)).fetchall())
        self.assertEqual(got, {'yes_no': 'boolean', 'flags': 'boolean', 'words': 'boolean', 'binary': 'integer',
                               'mixed': 'text', 'one_flag': 'text', 'wide': 'text', 'arabic': 'text', 'stamp': 'datetime', 'padded': 'text', 'money': 'decimal',
                               'bad_date': 'text', 'empty': 'text', 'neg': 'integer'})
        yes_no = self.conn.execute('SELECT distinct_count, missing_count FROM "column" WHERE dataset_id = ? AND name = ?',
                                   (d['id'], 'yes_no')).fetchone()
        self.assertEqual(yes_no, (2, 1))

    def test_duplicate_keys_are_found_with_the_query_and_row_count(self):
        r = self.key('客户', '客户编号')
        self.assertEqual((r['status'], r['rows_checked'], r['violations']), ('failed', 31, 1))
        self.assertEqual(r['samples'], [{'key': {'客户编号': 'KH012'}, 'count': 2}])
        self.assertIn('GROUP BY', r['query'])
        saved = self.conn.execute('SELECT element_id, check_type, query, rows_checked, violations, status, samples_json '
                                  'FROM check_result WHERE id = ?', (r['id'],)).fetchone()
        self.assertEqual(saved[0], 'key:客户(客户编号)')
        self.assertEqual(saved[2], r['query'])
        self.assertEqual(saved[3:6], (31, 1, 'failed'))
        self.assertEqual(json.loads(saved[6])[0]['key']['客户编号'], 'KH012')

    def test_planted_key_results(self):
        expected = [
            ('订单承诺', ('订单号',), 'failed', 121, 61), ('订单承诺', ('订单号', '承诺版本'), 'passed', 121, 0),
            ('库存快照', ('产品编号',), 'failed', 72, None), ('库存快照', ('快照月份', '产品编号'), 'passed', 72, 0),
            ('订单', ('订单号',), 'passed', 160, 0),
        ]
        for dataset, columns, status, rows, violations in expected:
            with self.subTest(dataset=dataset, columns=columns):
                r = self.key(dataset, *columns)
                self.assertEqual((r['status'], r['rows_checked']), (status, rows))
                if violations is not None:
                    self.assertEqual(r['violations'], violations)

    def test_a_key_over_columns_that_do_not_exist_is_refused(self):
        with self.assertRaises(ValueError):
            self.key('客户', '没有这列')

    def test_rows_without_a_key_value_fail_the_key_and_are_stored_apart_from_duplicates(self):
        d = import_records(self.conn, 'gaps', [{'k': 'a'}, {'k': None}, {'k': None}], 't', 'sha-gaps')
        r = check_key(self.conn, d['id'], ['k'])
        self.assertEqual((r['status'], r['violations'], r['null_key_rows']), ('failed', 0, 2))
        saved = self.conn.execute('SELECT null_key_rows, status FROM check_result WHERE id = ?', (r['id'],)).fetchone()
        self.assertEqual(saved, (2, 'failed'))

    def test_a_partly_empty_composite_key_and_an_empty_string_fail_too(self):
        d = import_records(self.conn, 'half', [{'a': 'x', 'b': None}, {'a': 'x', 'b': None}, {'a': 'y', 'b': '1'}], 't', 'sha-half')
        self.assertEqual(check_key(self.conn, d['id'], ['a', 'b'])['null_key_rows'], 2)
        blank = import_records(self.conn, 'blank', [{'k': ''}, {'k': 'a'}], 't', 'sha-blank')
        self.assertEqual((check_key(self.conn, blank['id'], ['k'])['status']), 'failed')

    def test_a_check_is_tied_to_the_dataset_version_it_ran_on(self):
        r = self.key('客户', '客户编号')
        self.assertEqual(self.conn.execute('SELECT dataset_id FROM check_result WHERE id = ?', (r['id'],)).fetchone()[0],
                         self.datasets['客户']['id'])

    def test_case_only_duplicate_column_names_are_stored_apart(self):
        d = import_records(self.conn, 'cased', [{'A': '1', 'a': '2'}], 't', 'sha-cased')
        names = [r[0] for r in self.conn.execute('SELECT name FROM "column" WHERE dataset_id = ? ORDER BY position', (d['id'],))]
        self.assertEqual(names, ['A', 'a_2'])

    def test_a_column_read_from_a_table_that_describes_something_else_is_checked_for_values_not_uniqueness(self):
        records = [{'ticket': 'T1', 'engineer': 'E1', 'note': 'x'}, {'ticket': 'T2', 'engineer': 'E1', 'note': 'y'},
                   {'ticket': 'T3', 'engineer': 'E2', 'note': 'z'}, {'ticket': 'T4', 'engineer': None, 'note': 'w'}]
        bundle = {'sources': {'tickets': {'records': records}}, 'file': {'name': 't.xlsx'}}
        ontology = lambda engineer_attrs: {'object_types': [
            {'key': 'ticket', 'label': '工单', 'populated_from': [pop('tickets', 'id', 'ticket')], 'attributes': attrs('tickets', 'note')},
            {'key': 'engineer', 'label': '工程师', 'populated_from': [pop('tickets', 'id', 'engineer')], 'attributes': engineer_attrs}],
            'relations': [], 'ignored_fields': [], 'open_questions': []}
        keys = {k['object_type']: k for k in check_bundle(self.conn, ontology([]), bundle, 't')['keys']}
        self.assertEqual((keys['ticket']['check_type'], keys['ticket']['status']), ('key_unique', 'passed'))
        self.assertEqual((keys['engineer']['check_type'], keys['engineer']['status'], keys['engineer']['distinct'],
                          keys['engineer']['null_key_rows']), ('key_distinct', 'passed', 2, 1))
        # the same column with attributes read from that table is the table's own object: uniqueness applies and fails
        own = {k['object_type']: k for k in check_bundle(self.conn, ontology(attrs('tickets', 'note')), bundle, 't')['keys']}
        self.assertEqual((own['engineer']['check_type'], own['engineer']['status']), ('key_unique', 'failed'))

    def test_importing_the_same_file_again_adds_no_version(self):
        s = self.bundle['sources']['客户']
        again = import_records(self.conn, '客户', s['records'], 'planted', records_sha256(s['records']))
        self.assertEqual((again['id'], again['version']), (self.datasets['客户']['id'], 1))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM dataset WHERE name = '客户'").fetchone()[0], 1)

    def test_changed_content_is_version_two_and_version_one_keeps_its_rows(self):
        records = self.bundle['sources']['产品']['records']
        changed = [*records[:-1]]
        v2 = import_records(self.conn, '产品', changed, 'planted', records_sha256(changed))
        self.assertEqual((v2['version'], v2['rows_stored']), (2, 11))
        v1 = self.datasets['产品']
        counts = [self.conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                  for t in (r[0] for r in self.conn.execute('SELECT table_name FROM dataset WHERE name = ? ORDER BY version', ('产品',)))]
        self.assertEqual(counts, [12, 11])
        self.assertEqual(v1['version'], 1)

    def test_rows_in_counts_the_file_and_dropped_rows_are_recorded_with_their_reason(self):
        d = import_records(self.conn, 'file', [{'a': '1'}, {'a': '2'}], 't', 'sha-file', rows_in=5, dropped={'blank': 2, 'title': 1})
        self.assertEqual((d['rows_in'], d['rows_stored'], json.loads(d['dropped_json'])), (5, 2, {'blank': 2, 'title': 1}))

    def test_rows_that_do_not_add_up_to_the_file_are_an_error(self):
        with self.assertRaises(RowCountMismatch) as caught:
            import_records(self.conn, 'file', [{'a': '1'}, {'a': '2'}], 't', 'sha-file', rows_in=5, dropped={'blank': 1})
        self.assertIn('file', str(caught.exception))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM dataset WHERE name = 'file'").fetchone()[0], 0)

    def test_the_latest_upload_is_the_current_version_even_when_it_is_old_content(self):
        a, b = [{'x': '1'}], [{'x': '2'}]
        v1 = import_records(self.conn, 'cur', a, 't', records_sha256(a))
        v2 = import_records(self.conn, 'cur', b, 't', records_sha256(b))
        self.assertEqual(current_dataset(self.conn, 'cur')['id'], v2['id'])
        again = import_records(self.conn, 'cur', a, 't', records_sha256(a))
        self.assertEqual((again['id'], again['reused']), (v1['id'], True))
        self.assertEqual(current_dataset(self.conn, 'cur')['version'], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM dataset WHERE name = 'cur'").fetchone()[0], 2)

    def test_an_import_writes_a_log_row(self):
        row = self.conn.execute("SELECT who, element_id, change FROM log WHERE element_id = 'dataset:订单'").fetchone()
        self.assertEqual(row[1], 'dataset:订单')
        self.assertIn('160', row[2])

    def test_a_row_count_that_does_not_match_what_was_written_is_an_error_and_leaves_nothing_behind(self):
        class Lying(list):
            def __iter__(self):
                return iter(list.__getitem__(self, slice(0, 1)))   # claims 2 rows, hands over 1
        with self.assertRaises(RowCountMismatch) as caught:
            import_records(self.conn, 'liar', Lying([{'a': '1'}, {'a': '2'}]), 't', 'sha-liar')
        self.assertIn('liar', str(caught.exception))
        self.assertIn('2', str(caught.exception))   # rows read
        self.assertIn('1', str(caught.exception))   # rows stored
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM dataset WHERE name = 'liar'").fetchone()[0], 0)

    def test_the_workspace_is_a_file_that_a_later_open_reads_again(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            path = Path(out) / 'workspace.sqlite'
            conn = open_workspace(path)
            import_records(conn, 'a', [{'x': '1'}], 't', 'sha-a')
            conn.close()
            again = open_workspace(path)
            self.addCleanup(again.close)
            self.assertEqual(again.execute('SELECT name, rows_stored FROM dataset').fetchall(), [('a', 1)])

    def test_a_file_made_before_ids_were_never_reused_is_rebuilt_and_loses_no_row_but_the_orphans(self):
        import tempfile
        with tempfile.TemporaryDirectory() as out:
            path = Path(out) / 'workspace.sqlite'
            conn = open_workspace(path)
            a = import_records(conn, 'a', [{'x': '1'}], 't', 'sha-a')
            check_key(conn, a['id'], ['x'])
            conn.execute("INSERT INTO check_result(element_id, check_type, query, status, dataset_id) VALUES ('key:gone(x)', 'key_unique', 'q', 'passed', 99)")
            conn.execute('DROP TABLE dataset')   # the tables as an older build made them: no AUTOINCREMENT
            conn.execute('DROP TABLE check_result')
            conn.execute('CREATE TABLE dataset (id INTEGER PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL, origin TEXT, file_sha256 TEXT NOT NULL, rows_in INTEGER NOT NULL,'
                         ' rows_stored INTEGER NOT NULL, table_name TEXT NOT NULL, imported_at TEXT NOT NULL, dropped_json TEXT, who TEXT, mode TEXT, changes_json TEXT, UNIQUE (name, version))')
            conn.execute('CREATE TABLE check_result (id INTEGER PRIMARY KEY, element_id TEXT NOT NULL, check_type TEXT NOT NULL, query TEXT NOT NULL, rows_checked INTEGER, violations INTEGER,'
                         " samples_json TEXT, dataset_id INTEGER, null_key_rows INTEGER, status TEXT NOT NULL, checked_at TEXT NOT NULL DEFAULT '')")
            conn.execute("INSERT INTO dataset(id, name, version, file_sha256, rows_in, rows_stored, table_name, imported_at) VALUES (5, 'a', 1, 's', 1, 1, 'ds_1', 'now')")
            conn.execute("INSERT INTO check_result(element_id, check_type, query, status, dataset_id) VALUES ('key:a(x)', 'key_unique', 'q', 'passed', 5)")
            conn.execute("INSERT INTO check_result(element_id, check_type, query, status, dataset_id) VALUES ('key:gone(x)', 'key_unique', 'q', 'passed', 99)")
            conn.close()
            again = open_workspace(path)
            self.addCleanup(again.close)
            self.assertEqual(again.execute('SELECT id, name FROM dataset').fetchall(), [(5, 'a')])
            self.assertEqual(again.execute('SELECT element_id FROM check_result').fetchall(), [('key:a(x)',)])   # the one whose dataset is gone is dropped
            again.execute("DELETE FROM dataset WHERE id = 5")
            self.assertEqual(import_records(again, 'b', [{'x': '1'}], 't', 'sha-b')['id'], 6)   # 5 is never given out again
            open_workspace(path).close()   # a rebuilt file opens again without another rebuild


class ElementStateTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)

    def row(self, element_id):
        cursor = self.conn.execute('SELECT * FROM element_state WHERE element_id = ?', (element_id,))
        found = cursor.fetchone()
        return dict(zip([c[0] for c in cursor.description], found)) if found else None

    def test_a_recheck_by_someone_else_leaves_whose_confirmation_it_was(self):
        from ontology_poc_generator.actor import set_actor
        self.addCleanup(set_actor, None)
        set_actor({'id': 3, 'display_name': 'Bob'})
        set_element_states(self.conn, [('view:k:v', 'confirmed', None, 'Bob', {'kind': 'filter'})])
        set_actor({'id': 2, 'display_name': 'Ann'})   # Ann's upload moves the data: the view is checked again, still Bob's confirmation
        set_element_states(self.conn, [('view:k:v', 'checked', None, 'Bob', {'kind': 'filter'})])
        row = self.row('view:k:v')
        self.assertEqual((row['state'], row['confirmed_by'], row['confirmed_by_user_id']), ('checked', 'Bob', 3))
        self.assertEqual(self.conn.execute("SELECT user_id FROM log WHERE element_id = 'view:k:v' ORDER BY rowid DESC").fetchone()[0], 3)

    def test_a_confirmation_keeps_state_evidence_person_time_and_version(self):
        set_element_states(self.conn, [('object_type:k:customer', 'confirmed', 'check_result:3', '王工')])
        row = self.row('object_type:k:customer')
        self.assertEqual((row['state'], row['evidence_ref'], row['confirmed_by'], row['version']), ('confirmed', 'check_result:3', '王工', 1))
        self.assertRegex(row['confirmed_at'], r'^\d{4}-\d{2}-\d{2}T')
        log = self.conn.execute("SELECT who, change FROM log WHERE element_id = 'object_type:k:customer'").fetchall()
        self.assertEqual(log, [('王工', 'confirmed')])

    def test_the_same_judgement_again_changes_nothing_and_a_changed_one_is_the_next_version(self):
        change = ('relation:k:r1', 'confirmed', None, '王工')
        set_element_states(self.conn, [change])
        first = self.row('relation:k:r1')
        set_element_states(self.conn, [change])
        self.assertEqual(self.row('relation:k:r1'), first)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM log WHERE element_id = 'relation:k:r1'").fetchone()[0], 1)
        set_element_states(self.conn, [('relation:k:r1', 'rejected', None, '李经理')])
        later = self.row('relation:k:r1')
        self.assertEqual((later['state'], later['confirmed_by'], later['version']), ('rejected', '李经理', 2))
        before = json.loads(self.conn.execute("SELECT before_json FROM log WHERE element_id = 'relation:k:r1' ORDER BY rowid DESC").fetchone()[0])
        self.assertEqual(before['state'], 'confirmed')

    def test_a_confirmation_without_a_name_is_kept_unsigned(self):
        set_element_states(self.conn, [('object_type:k:a', 'confirmed', None, None)])
        self.assertIsNone(self.row('object_type:k:a')['confirmed_by'])

    def two_checks_of_the_same_content(self):
        records = [{'k': '1'}, {'k': '1'}, {'k': '2'}]
        d = import_records(self.conn, 'a', records, 't', records_sha256(records))
        return check_key(self.conn, d['id'], ['k'])['id'], check_key(self.conn, d['id'], ['k'])['id']

    def test_the_same_evidence_found_again_is_the_same_judgement(self):
        first, again = self.two_checks_of_the_same_content()   # a re-upload runs the check again: new row, same finding
        set_element_states(self.conn, [('object_type:k:a', 'confirmed', f'check_result:{first}', '王工')])
        set_element_states(self.conn, [('object_type:k:a', 'confirmed', f'check_result:{again}', '王工')])
        row = self.row('object_type:k:a')
        self.assertEqual((row['version'], row['evidence_ref']), (1, f'check_result:{first}'))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM log WHERE element_id = 'object_type:k:a'").fetchone()[0], 1)

    def test_a_different_finding_is_the_next_version(self):
        first, _ = self.two_checks_of_the_same_content()
        records = [{'k': '1'}, {'k': '2'}]
        other = check_key(self.conn, import_records(self.conn, 'b', records, 't', records_sha256(records))['id'], ['k'])['id']
        set_element_states(self.conn, [('object_type:k:a', 'confirmed', f'check_result:{first}', '王工')])
        set_element_states(self.conn, [('object_type:k:a', 'confirmed', f'check_result:{other}', '王工')])
        self.assertEqual(self.row('object_type:k:a')['version'], 2)

    def test_evidence_from_an_older_run_does_not_replace_newer_evidence(self):
        old, new = self.two_checks_of_the_same_content()
        records = [{'k': '1'}, {'k': '2'}]
        older = check_key(self.conn, import_records(self.conn, 'b', records, 't', records_sha256(records))['id'], ['k'])['id']
        self.conn.execute("UPDATE check_result SET checked_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (older,))
        self.conn.execute("UPDATE check_result SET checked_at = '2026-02-01T00:00:00+00:00' WHERE id = ?", (new,))
        set_element_states(self.conn, [('object_type:k:a', 'confirmed', f'check_result:{new}', '王工')])
        set_element_states(self.conn, [('object_type:k:a', 'confirmed', f'check_result:{older}', '李经理')])   # an old run saved late
        row = self.row('object_type:k:a')
        self.assertEqual((row['evidence_ref'], row['confirmed_by'], row['version']), (f'check_result:{new}', '李经理', 2))

    def test_nothing_is_kept_when_what_the_writes_wait_for_fails(self):
        with self.assertRaises(RuntimeError):
            with element_state_writes(self.conn, [('object_type:k:a', 'confirmed', None, '王工')]) as rows:
                self.assertEqual(rows['object_type:k:a']['version'], 1)
                raise RuntimeError('the run file could not be written')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM element_state').fetchone()[0], 0)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM log').fetchone()[0], 0)

    def test_a_definition_is_kept_with_the_state_and_a_changed_one_is_the_next_version(self):
        enum = {'values': [{'value': '2', 'label': '已取消', 'description': ''}]}
        confirm = lambda content, who='王工': set_element_states(self.conn, [('property:k:订单.状态码', 'confirmed', 'open_item:code_meaning:订单.状态码', who, content)])
        confirm(enum)
        confirm(enum)
        self.assertEqual(self.row('property:k:订单.状态码')['version'], 1)
        confirm({'values': [{'value': '2', 'label': '作废', 'description': ''}]})
        self.assertEqual(self.row('property:k:订单.状态码')['version'], 2)
        self.assertEqual(element_contents(self.conn, 'property:k:'), {'订单.状态码': {'values': [{'value': '2', 'label': '作废', 'description': ''}],
                                                                                    'confirmed_by': '王工', 'confirmed_at': self.row('property:k:订单.状态码')['confirmed_at'], 'version': 2}})

    def test_an_open_item_as_evidence_is_kept_as_written(self):
        set_element_states(self.conn, [('property:k:a.b', 'confirmed', 'open_item:x', '王工', {'values': []})])
        self.assertEqual(self.row('property:k:a.b')['evidence_ref'], 'open_item:x')

    def test_one_bad_state_writes_none_of_the_batch(self):
        with self.assertRaises(sqlite3.IntegrityError):
            set_element_states(self.conn, [('object_type:k:a', 'confirmed', None, None), ('object_type:k:b', 'maybe', None, None)])
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM element_state').fetchone()[0], 0)


class ObjectRowsCollapseTests(unittest.TestCase):
    def test_a_repeated_identity_is_shown_not_hidden(self):
        bundle = planted_bundle()
        ontology = {'object_types': [{'key': 'customer', 'label': '客户',
                                      'populated_from': [{'source': '客户', 'identity': {'customer_id': '客户编号'}}],
                                      'attributes': []}], 'relations': [], 'ignored_fields': [], 'open_questions': []}
        page = object_rows(ontology, bundle, 'customer')
        self.assertEqual((page['objects'], page['total']), (30, 31))   # 30 customers; 31 rows listed, KH012 on both of its rows
        self.assertEqual(page['identity_repeats'], [{'source': '客户', 'rows': 31, 'identities': 30, 'repeated': 1, 'examples': ['KH012'], 'rule': None}])


    def test_a_table_that_only_mentions_the_object_does_not_count_its_repeats(self):
        page = object_rows(PLANTED_DRAFT, planted_bundle(), 'customer')   # 160 orders name 31 customers: that is not a broken key
        self.assertEqual([r['source'] for r in page['identity_repeats']], ['客户'])


def pop(source, key, column):
    return {'source': source, 'identity': {key: column}}


def attrs(source, *paths):
    return [{'source': source, 'path': p} for p in paths]


PLANTED_DRAFT = {
    'reasoning': 'r', 'open_questions': [], 'ignored_fields': [],
    'object_types': [
        {'key': 'customer', 'label': '客户', 'rationale': 'r',
         'populated_from': [pop('客户', 'customer_id', '客户编号'), pop('订单', 'customer_id', '客户编号')],
         'attributes': attrs('客户', '客户名称', '行业', '城市', '客户等级')},
        {'key': 'product', 'label': '产品', 'rationale': 'r',
         'populated_from': [pop('产品', 'product_id', '产品编号'), pop('订单', 'product_id', '产品编号'),
                            pop('库存快照', 'product_id', '产品编号'), pop('交付统计', 'product_id', '产品编号')],
         'attributes': attrs('产品', '产品名称', '品类', '单价') + attrs('库存快照', '快照月份', '库存数量')
         + attrs('交付统计', '订单数', '交付天数P50')},
        {'key': 'order', 'label': '订单', 'rationale': 'r',
         'populated_from': [pop('订单', 'order_id', '订单号'), pop('订单承诺', 'order_id', '订单号'),
                            pop('售后工单', 'order_id', '订单号')],
         'attributes': attrs('订单', '数量', '金额', '下单日期', '状态码', '交付天数')
         + attrs('订单承诺', '承诺版本', '承诺数量', '承诺交付日期')},
        {'key': 'ticket', 'label': '售后工单', 'rationale': 'r', 'populated_from': [pop('售后工单', 'ticket_id', '工单号')],
         'attributes': attrs('售后工单', '问题类型', '问题描述', '创建日期', '处理状态')},
        {'key': 'engineer', 'label': '工程师', 'rationale': 'r', 'populated_from': [pop('售后工单', 'engineer_id', '负责工程师')],
         'attributes': []},
    ],
    'relations': [],
}


def better_draft() -> dict:
    """The planted draft after the model is told the snapshot and commitment keys repeat: each gets its own object type."""
    draft = json.loads(json.dumps(PLANTED_DRAFT))
    types = {t['key']: t for t in draft['object_types']}
    types['product']['populated_from'] = [p for p in types['product']['populated_from'] if p['source'] != '库存快照']
    types['product']['attributes'] = [a for a in types['product']['attributes'] if a['source'] != '库存快照']
    types['order']['populated_from'] = [p for p in types['order']['populated_from'] if p['source'] != '订单承诺']
    types['order']['attributes'] = [a for a in types['order']['attributes'] if a['source'] != '订单承诺']
    draft['object_types'] += [
        {'key': 'stock_snapshot', 'label': '库存快照', 'rationale': 'r', 'attributes': attrs('库存快照', '库存数量'),
         'populated_from': [{'source': '库存快照', 'identity': {'month': '快照月份', 'product_id': '产品编号'}}]},
        {'key': 'commitment', 'label': '订单承诺', 'rationale': 'r', 'attributes': attrs('订单承诺', '承诺数量', '承诺交付日期'),
         'populated_from': [{'source': '订单承诺', 'identity': {'order_id': '订单号', 'version': '承诺版本'}}]}]
    return draft


class DraftsModel:
    """Answers the first draft, and the second one once it is told what the code found wrong; keeps what it was asked.
    (An upload also starts extra runs in parallel, so the answer cannot depend on the order of calls.)"""
    def __init__(self, *drafts):
        self.drafts, self.prompts = list(drafts), []

    def complete_json(self, *, system_prompt, user_prompt):
        self.prompts.append(user_prompt)
        draft = self.drafts[-1 if 'errors_found_by_code' in user_prompt else 0]
        return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(draft, ensure_ascii=False))


PlantedDraftModel = lambda: DraftsModel(PLANTED_DRAFT)


class ServerDataChecksTests(unittest.TestCase):
    files = [{'filename': p.name, 'content_base64': base64.b64encode(p.read_bytes()).decode()} for p in sorted(PLANTED.glob('*.xlsx'))]

    def build(self, model):
        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        server = OntologyServerTests().server(gateway=model)
        base, out = server.__enter__()
        self.addCleanup(server.__exit__, None, None, None)
        return base, out, lambda: call(base, '/api/ontology/build', {'files': self.files})

    def test_seven_uploaded_tables_come_back_with_their_counts_and_key_checks(self):
        base, out, upload = self.build(PlantedDraftModel())
        status, run = upload()
        self.assertEqual(status, 200, run)
        self.assertEqual(run['ontology']['status'], 'auto_built_verified', run['ontology'].get('attempts'))
        checks = {(c['object_type'], c['dataset']): c for c in run['data_checks']['keys']}
        customer = checks['customer', '客户']
        self.assertEqual((customer['status'], customer['check_type'], customer['violations'], customer['key_columns']),
                         ('failed', 'key_unique', 1, ['客户编号']))
        self.assertEqual(customer['samples'][0]['key'], {'客户编号': 'KH012'})
        self.assertEqual(customer['null_key_rows'], 0)
        self.assertEqual((checks['order', '订单承诺']['status'], checks['order', '订单承诺']['violations']), ('failed', 61))
        self.assertEqual(checks['order', '订单']['status'], 'passed')
        self.assertEqual(checks['order', '订单']['rows_checked'], 160)
        self.assertEqual(checks['ticket', '售后工单']['status'], 'passed')
        self.assertNotIn('role', customer)
        # many orders per customer is not a broken key: that table describes orders, so its customer column is read as values
        self.assertEqual((checks['customer', '订单']['check_type'], checks['customer', '订单']['status']), ('key_distinct', 'passed'))
        # engineers come from a column of the tickets: five or so people, not forty-five tickets
        engineer = checks['engineer', '售后工单']
        self.assertEqual((engineer['check_type'], engineer['status']), ('key_distinct', 'passed'))
        tables = {t['dataset']: t for t in run['data_checks']['tables']}
        self.assertEqual({n: (t['rows_in'], t['rows_stored']) for n, t in tables.items()},
                         {'订单': (160, 160), '客户': (31, 31), '产品': (12, 12), '售后工单': (45, 45), '库存快照': (72, 72),
                          '订单承诺': (121, 121), '交付统计': (12, 12)})
        conn = open_workspace(out / 'workspace.sqlite')
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT rows_stored FROM dataset WHERE name = '库存快照'").fetchone()[0], 72)
        _, again = upload()
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM dataset').fetchone()[0], 7)   # same files: no new versions
        strip = lambda checks: [{k: v for k, v in c.items() if k != 'check_id'} for c in checks]   # each run records new checks
        self.assertEqual(strip(again['data_checks']['keys']), strip(run['data_checks']['keys']))

    def test_a_failed_key_is_sent_back_to_the_model_and_a_better_key_ends_the_failure(self):
        model = DraftsModel(PLANTED_DRAFT, better_draft())
        _, _, upload = self.build(model)
        status, run = upload()
        self.assertEqual(status, 200, run)
        retry = next(p for p in model.prompts if 'errors_found_by_code' in p)
        self.assertIn('key not unique in 库存快照', retry)
        self.assertIn('key not unique in 订单承诺', retry)
        self.assertEqual(run['ontology']['status'], 'auto_built_verified', run['ontology']['attempts'])
        keys = {(c['object_type'], c['dataset']): c['status'] for c in run['data_checks']['keys']}
        self.assertEqual(keys['stock_snapshot', '库存快照'], 'passed')
        self.assertEqual(keys['commitment', '订单承诺'], 'passed')

    def test_a_key_that_stays_broken_after_the_retry_is_reported_not_blocking(self):
        _, _, upload = self.build(PlantedDraftModel())   # KH012 really is twice in the customer table
        status, run = upload()
        self.assertEqual(run['ontology']['status'], 'auto_built_verified')
        self.assertEqual(run['ontology']['attempts'][-1]['errors'][0]['code'], 'key_not_unique')

    def test_the_data_sends_the_model_back_at_most_once(self):
        model = DraftsModel(PLANTED_DRAFT, better_draft())   # the retry fixes two keys; the customer key can never be fixed
        run = build_company_ontology(planted_bundle(), model)
        self.assertEqual(len(model.prompts), 2)
        self.assertEqual([a.get('data_retry') for a in run['attempts']], [None, True])

    def test_a_retry_that_fails_verification_keeps_the_verified_draft(self):
        broken = json.loads(json.dumps(PLANTED_DRAFT))
        broken['object_types'][0]['attributes'].append({'source': '客户', 'path': '没有这一列'})
        run = build_company_ontology(planted_bundle(), DraftsModel(PLANTED_DRAFT, broken))
        self.assertEqual(run['status'], 'auto_built_verified', run['attempts'])
        self.assertEqual(run['verification']['errors'], [])
        self.assertEqual({t['key'] for t in run['object_types']}, {t['key'] for t in PLANTED_DRAFT['object_types']})
        self.assertEqual([a.get('discarded') for a in run['attempts']], [None, True])

    def test_a_retry_with_more_key_errors_does_not_replace_the_earlier_draft(self):
        run = build_company_ontology(planted_bundle(), DraftsModel(better_draft(), PLANTED_DRAFT))   # 1 key error, then 3
        self.assertEqual([a.get('discarded') for a in run['attempts']], [None, True])
        self.assertEqual({t['key'] for t in run['object_types']}, {t['key'] for t in better_draft()['object_types']})
        self.assertEqual(len(kept_attempts(run)), 1)

    def test_a_retry_that_hides_the_repeated_customer_by_a_city_and_drops_the_relation_is_dropped(self):
        """What a real model did on the planted tables: 客户编号 repeats (KH012), so the customer identity became 客户编号 + 城市, which
        makes the key check pass, and the orders (which have no city) stopped naming customers, so the relation went."""
        relation = {'key': 'order_customer', 'from': 'order', 'to': 'customer', 'source': '订单', 'label': '下单', 'meaning': '订单属于客户',
                    'from_identity': {'order_id': '订单号'}, 'to_identity': {'customer_id': '客户编号'}}
        first = {**better_draft(), 'relations': [relation]}        # the snapshot and commitment keys are already right: only the customer's repeat is left
        gamed = better_draft()
        customer = next(t for t in gamed['object_types'] if t['key'] == 'customer')
        customer['populated_from'] = [{'source': '客户', 'identity': {'customer_id': '客户编号', 'city': '城市'}}]
        customer['attributes'] = [a for a in customer['attributes'] if a['path'] != '城市']
        gamed['ignored_fields'] = [{'source': '订单', 'path': '客户编号', 'reason': 'r'}]
        self.assertEqual(verify_company_proposal(gamed, planted_bundle())['errors'], [])        # it passes verification, and its key check passes: only the guard stops it
        model = DraftsModel(first, gamed)
        run = build_company_ontology(planted_bundle(), model)
        self.assertEqual(len(model.prompts), 2)
        self.assertEqual([a.get('discarded') for a in run['attempts']], [None, True])
        self.assertEqual(run['attempts'][-1]['errors'], [])
        self.assertEqual(run['attempts'][-1]['discarded_because'], ['customer：识别列加了「城市」，它不是时间或版本列', 'order 和 customer 之间的关系「order_customer」没有了'])
        self.assertEqual([r['key'] for r in run['relations']], ['order_customer'])
        self.assertEqual(next(t for t in run['object_types'] if t['key'] == 'customer')['populated_from'][0]['identity'], {'customer_id': '客户编号'})
        retry = next(p for p in model.prompts if 'errors_found_by_code' in p)
        self.assertIn('keep this key', retry)                       # the retry is told a repeat in master data is a data problem
        self.assertIn('versions, snapshots, months', retry)

    def test_a_time_or_version_column_in_the_identity_is_what_a_retry_may_add(self):
        from ontology_poc_generator.public_ontology import key_retry_problems
        sources = {n: s['records'] for n, s in planted_bundle()['sources'].items()}
        self.assertEqual(key_retry_problems(PLANTED_DRAFT, better_draft(), sources), [])          # 快照月份 and 承诺版本 are new types' own columns
        month = json.loads(json.dumps(PLANTED_DRAFT))
        month['object_types'][1]['populated_from'][2]['identity']['month'] = '快照月份'          # 库存快照 read by product + month
        self.assertEqual(key_retry_problems(PLANTED_DRAFT, month, sources), [])
        version = json.loads(json.dumps(PLANTED_DRAFT))
        version['object_types'][2]['populated_from'][1]['identity']['version'] = '承诺版本'
        self.assertEqual(key_retry_problems(PLANTED_DRAFT, version, sources), [])

    def test_renaming_the_customer_type_or_dropping_it_does_not_start_a_clean_record(self):
        from ontology_poc_generator.public_ontology import key_retry_problems
        sources = {n: s['records'] for n, s in planted_bundle()['sources'].items()}
        renamed = better_draft()
        customer = next(t for t in renamed['object_types'] if t['key'] == 'customer')
        customer['key'] = 'customer_city'
        customer['populated_from'] = [{'source': '客户', 'identity': {'customer_id': '客户编号', 'city': '城市'}}]
        self.assertEqual(key_retry_problems(better_draft(), renamed, sources), ['customer_city：识别列加了「城市」，它不是时间或版本列'])
        dropped = better_draft()
        dropped['object_types'] = [t for t in dropped['object_types'] if t['key'] != 'customer']
        self.assertEqual(key_retry_problems(better_draft(), dropped, sources), ['客户：「客户」表不再用来建任何对象'])

    def test_a_retry_that_changes_nothing_is_dropped_too(self):
        run = build_company_ontology(planted_bundle(), DraftsModel(PLANTED_DRAFT))   # the same draft again: 3 key errors, then 3
        self.assertEqual([a.get('discarded') for a in run['attempts']], [None, True])

    def test_stability_re_runs_do_not_send_the_model_back_for_the_data(self):
        model = DraftsModel(PLANTED_DRAFT, better_draft())
        run = build_company_ontology(planted_bundle(), model, retry_for_data=False)
        self.assertEqual(len(model.prompts), 1)
        self.assertEqual(len(run['attempts']), 1)

    def test_the_call_limit_message_names_the_data_retry_instead_of_blaming_the_draft(self):
        broken = json.loads(json.dumps(PLANTED_DRAFT))
        broken['object_types'][0]['attributes'].append({'source': '客户', 'path': '没有这一列'})
        replies = {'first': broken, 'fields_fixed': PLANTED_DRAFT, 'keys_sent_back': better_draft()}

        class ByErrors:
            def complete_json(self, *, system_prompt, user_prompt):
                if 'errors_found_by_code' not in user_prompt:
                    draft = replies['first']
                else:
                    draft = replies['keys_sent_back' if 'key not unique' in user_prompt else 'fields_fixed']
                return ModelCompletion(provider='fake', model='deepseek-flash', content=json.dumps(draft, ensure_ascii=False))

        from tests.test_ontology_ask_server import call
        from tests.test_ontology_server import OntologyServerTests
        with OntologyServerTests().server(gateway=ByErrors()) as (base, _):
            status, run = call(base, '/api/ontology/build', {'files': self.files, 'purpose': '哪些订单被取消？'})
        self.assertEqual(status, 200, run)
        self.assertEqual(len(run['ontology']['attempts']), 3)
        message = run['evaluation']['asked'][0]['error']
        self.assertIn('其中 1 次是按数据检查结果重试', message)
        self.assertNotIn('用满', message)

    def confirm(self, base, run, types, signer='王工'):
        from tests.test_ontology_ask_server import call
        return call(base, '/api/ontology/confirm', {'saved_as': run['saved_as'], 'confirmed_by': signer,
                                                   'decisions': {'types': {k: {'verdict': v} for k, v in types.items()}, 'relations': {}}})

    def test_a_confirmation_is_written_as_element_state_with_the_key_checks_as_evidence_and_the_person(self):
        base, out, upload = self.build(PlantedDraftModel())
        _, run = upload()
        status, saved = self.confirm(base, run, {'customer': 'ok', 'order': 'ok', 'engineer': 'wrong'})
        self.assertEqual(status, 200, saved)
        conn = open_workspace(out / 'workspace.sqlite')
        self.addCleanup(conn.close)
        prefix = f"object_type:{run['file']['sha256']}:"
        rows = {r[0][len(prefix):]: r[1:] for r in conn.execute('SELECT element_id, state, evidence_ref, confirmed_by, version FROM element_state')}
        self.assertEqual(set(rows), {'customer', 'order', 'engineer'})
        self.assertEqual((rows['customer'][0], rows['customer'][2], rows['customer'][3]), ('confirmed', '王工', 1))
        self.assertEqual(rows['engineer'][0], 'rejected')
        # the evidence is the stored check rows of that object's identity columns, not a copy of their text
        refs = [int(r.split(':')[1]) for r in rows['customer'][1].split(',')]
        checked = {conn.execute('SELECT element_id, status FROM check_result WHERE id = ?', (i,)).fetchone() for i in refs}
        self.assertEqual(checked, {('key:客户(客户编号)', 'failed'), ('key:订单(客户编号)', 'passed')})
        # the run the page gets carries the same, so the page can show it after a reload
        shown = saved['confirmation']['elements']['types:customer']
        self.assertEqual((shown['state'], shown['confirmed_by'], shown['version'], shown['evidence_ref']), ('confirmed', '王工', 1, rows['customer'][1]))

    def test_saving_the_same_confirmation_again_keeps_the_version_and_a_changed_verdict_is_the_next_version(self):
        base, out, upload = self.build(PlantedDraftModel())
        _, run = upload()
        self.confirm(base, run, {'customer': 'ok', 'order': 'ok'})
        self.confirm(base, run, {'customer': 'ok', 'order': 'wrong'})
        _, saved = self.confirm(base, run, {'customer': 'ok', 'order': 'wrong'})
        elements = saved['confirmation']['elements']
        self.assertEqual((elements['types:customer']['version'], elements['types:order']['version'], elements['types:order']['state']),
                         (1, 2, 'rejected'))

    def test_taking_a_judgement_back_returns_the_element_to_proposed_with_a_log_row(self):
        base, out, upload = self.build(PlantedDraftModel())
        _, run = upload()
        self.confirm(base, run, {'customer': 'ok', 'order': 'ok'})
        status, saved = self.confirm(base, run, {'order': 'ok'})   # customer's verdict was clicked off
        self.assertEqual(status, 200, saved)
        elements = saved['confirmation']['elements']
        self.assertEqual((elements['types:customer']['state'], elements['types:customer']['version']), ('proposed', 2))
        conn = open_workspace(out / 'workspace.sqlite')
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("SELECT state, evidence_ref FROM element_state WHERE element_id LIKE '%:customer'").fetchone(), ('proposed', None))
        self.assertEqual(conn.execute("SELECT change FROM log WHERE element_id LIKE '%:customer' ORDER BY rowid").fetchall(), [('confirmed',), ('proposed',)])

    def test_the_same_judgement_after_uploading_the_same_files_again_keeps_the_version(self):
        base, out, upload = self.build(PlantedDraftModel())
        _, first = upload()
        self.confirm(base, first, {'customer': 'ok', 'order': 'ok'})
        _, second = upload()   # same content: new check rows, same findings
        self.assertNotEqual(second['saved_as'], first['saved_as'])
        _, saved = self.confirm(base, second, {'customer': 'ok', 'order': 'ok'})
        self.assertEqual({e['version'] for e in saved['confirmation']['elements'].values()}, {1})

    def test_a_confirmation_that_cannot_be_written_to_the_run_says_so_and_leaves_no_state(self):
        from unittest import mock
        from ontology_poc_generator import ontology_server
        base, out, upload = self.build(PlantedDraftModel())
        _, run = upload()
        with mock.patch.object(ontology_server.os, 'replace', side_effect=PermissionError('read-only')):   # the run file is replaced whole: this is where it fails
            status, body = self.confirm(base, run, {'customer': 'ok'})
        self.assertEqual(status, 500)
        self.assertIn('确认没有保存', body['error'])
        conn = open_workspace(out / 'workspace.sqlite')
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM element_state').fetchone()[0], 0)

    def test_tables_are_checked_even_when_the_draft_fails_the_model_checks(self):
        broken = json.loads(json.dumps(PLANTED_DRAFT))
        broken['object_types'][0]['attributes'].append({'source': '客户', 'path': '没有这一列'})
        _, _, upload = self.build(DraftsModel(broken))
        status, run = upload()
        self.assertEqual(status, 200, run)
        self.assertNotEqual(run['ontology']['status'], 'auto_built_verified')
        self.assertEqual(len(run['data_checks']['tables']), 7)
        keys = {(c['object_type'], c['dataset']): c for c in run['data_checks']['keys']}
        self.assertEqual(keys['customer', '客户']['violations'], 1)

    def test_a_data_check_that_crashes_is_shown_and_the_upload_still_succeeds(self):
        from unittest import mock
        _, _, upload = self.build(PlantedDraftModel())
        with mock.patch('ontology_poc_generator.ontology_server.check_bundle', side_effect=sqlite3.OperationalError('disk I/O error')):
            status, run = upload()
        self.assertEqual(status, 200, run)
        self.assertEqual(run['ontology']['status'], 'auto_built_verified')
        self.assertIn('disk I/O error', run['data_checks']['error'])

    def test_a_table_that_cannot_be_stored_is_named_with_rows_read_and_stored_and_the_others_still_are(self):
        class Lying(list):
            def __iter__(self):
                return iter(list.__getitem__(self, slice(0, 1)))
        bundle = {'file': {'name': 'f'}, 'sources': {'a': {'records': Lying([{'k': '1'}, {'k': '2'}])}, 'b': {'records': [{'k': '1'}]}}}
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        tables = {t['dataset']: t for t in check_bundle(conn, {'object_types': []}, bundle, 'f')['tables']}
        self.assertEqual(tables['a']['status'], 'error')
        self.assertIn('a', tables['a']['error'])
        self.assertEqual(tables['b']['rows_stored'], 1)


if __name__ == '__main__':
    unittest.main()
