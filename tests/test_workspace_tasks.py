"""The task list: modelling jobs the service recorded and dataset uploads, newest first."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import urlopen

from ontology_poc_generator.workspace_datasets import upload
from ontology_poc_generator.workspace_store import open_workspace
from ontology_poc_generator.workspace_tasks import job_tasks, list_tasks
from tests.test_document_server import DocumentModel
from tests.test_ontology_ask_server import call
from tests.test_ontology_jobs import wait
from tests.test_ontology_server import CSV, OntologyServerTests
from tests.test_workspace_datasets import part, planted, table_csv, order


def job_file(directory, job_id, state, events, error=None):
    (directory / f'{job_id}.json').write_text(json.dumps({'state': state, 'events': events, 'error': error, 'saved_as': None}), encoding='utf-8')


class JobTaskTests(unittest.TestCase):
    def test_each_job_file_is_a_task_with_its_file_state_and_times(self):
        with tempfile.TemporaryDirectory() as out:
            jobs = Path(out)
            read = lambda at, name: {'stage': 'read', 'detail': {'file': name, 'kind': 'table'}, 'at': at}
            job_file(jobs, 'a' * 12, 'done', [read('2026-11-13T10:00:00+00:00', '订单.xlsx'), {'stage': 'done', 'detail': {}, 'at': '2026-11-13T10:01:30+00:00'}])
            job_file(jobs, 'b' * 12, 'failed', [read('2026-11-13T11:00:00+00:00', '客户.xlsx'), {'stage': 'failed', 'detail': {}, 'at': '2026-11-13T11:00:05+00:00'}], '建模时出错：x')
            job_file(jobs, 'c' * 12, 'running', [read('2026-11-13T12:00:00+00:00', '产品.xlsx')])
            job_file(jobs, 'd' * 12, 'running', [read('2026-11-13T13:00:00+00:00', '库存.xlsx')])
            (jobs / ('e' * 12 + '.json')).write_text('{"state": "do', encoding='utf-8')   # cut short by a crash
            (jobs / ('f' * 12 + '.json.part')).write_text('{}', encoding='utf-8')
            (jobs / ('g' * 12 + '.json')).write_text('[]', encoding='utf-8')   # not the shape the service writes
            (jobs / ('h' * 12 + '.json')).write_text('{"events": []}', encoding='utf-8')   # no state
            found, unreadable = job_tasks(jobs, {'c' * 12})
            got = {t['title']: t for t in found}
        self.assertEqual(sorted(got), ['产品.xlsx', '客户.xlsx', '库存.xlsx', '订单.xlsx'])
        self.assertEqual((got['订单.xlsx']['state'], got['订单.xlsx']['at'], got['订单.xlsx']['ended_at']), ('done', '2026-11-13T10:00:00+00:00', '2026-11-13T10:01:30+00:00'))
        self.assertEqual((got['客户.xlsx']['state'], got['客户.xlsx']['error']), ('failed', '建模时出错：x'))
        self.assertEqual((got['产品.xlsx']['state'], got['产品.xlsx']['ended_at']), ('running', None))
        self.assertEqual(got['库存.xlsx']['state'], 'interrupted')   # running on disk, not in this process
        self.assertEqual(unreadable, 3)   # the cut-short file, the list and the one without a state; the .part file is not a record

    def test_newest_first_by_start_time(self):
        with tempfile.TemporaryDirectory() as out:
            for i, at in enumerate(('2026-11-13T10:00:00+00:00', '2026-11-13T12:00:00+00:00', '2026-11-13T11:00:00+00:00')):
                job_file(Path(out), str(i) * 12, 'done', [{'stage': 'read', 'detail': {'file': f'f{i}'}, 'at': at}])
            conn = open_workspace(':memory:')
            self.addCleanup(conn.close)
            self.assertEqual([t['title'] for t in list_tasks(conn, Path(out), set())[0]], ['f1', 'f2', 'f0'])

    def test_no_jobs_directory_is_no_jobs(self):
        self.assertEqual(job_tasks(Path('/no/such/dir'), set()), ([], 0))


class UploadTaskTests(unittest.TestCase):
    def test_uploads_and_skipped_updates_are_tasks_but_older_run_imports_are_not(self):
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        from ontology_poc_generator.workspace_store import import_records
        import_records(conn, '旧', [{'a': '1'}], 'run', 'sha-old')   # as a run's build made it: no mode
        upload(conn, [planted('订单')], '小林')
        rows = [order('DD20260001')]
        upload(conn, [part('x.csv', table_csv(rows), target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')   # changes row 1
        upload(conn, [part('x.csv', table_csv(rows), target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')   # the same again: nothing to do
        tasks, _ = list_tasks(conn, Path('/no/such/dir'), set())
        self.assertEqual(sorted((t['mode'], t['created_version']) for t in tasks), [('new', True), ('update_by_key', False), ('update_by_key', True)])
        self.assertEqual(sorted(t['version'] for t in tasks if t['created_version']), [1, 2])
        self.assertNotIn('旧', {t['title'] for t in tasks})

    def test_a_name_the_old_screen_creates_first_is_a_new_dataset_in_tasks(self):
        from ontology_poc_generator.workspace_store import check_bundle
        conn = open_workspace(':memory:')
        self.addCleanup(conn.close)
        check_bundle(conn, {'object_types': []}, {'sources': {'新表': {'records': [{'a': '1'}], 'rows_read': 1, 'dropped_rows': {}}}}, '建模运行', relations=False)
        tasks, _ = list_tasks(conn, Path('/no/such/dir'), set())
        self.assertEqual([(t['title'], t['mode'], t['version']) for t in tasks], [('新表', 'new', 1)])


class TaskEndpointTests(unittest.TestCase):
    def test_a_modelling_job_and_an_upload_appear_in_one_list(self):
        with OntologyServerTests().server(gateway=DocumentModel()) as (base, _):
            _, started = call(base, '/api/ontology/jobs', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            wait(base, started['job_id'])
            status, body = call(base, '/api/workspace/datasets/upload', {'who': '小林', 'files': [planted('客户')]})
            self.assertEqual(status, 200, body)
            with urlopen(base + '/api/workspace/tasks') as response:
                tasks = json.load(response)['tasks']
        by_kind = {t['kind']: t for t in tasks if t['title'] != 'orders' or t['kind'] == 'draft'}   # all land in the same second, so their order is not asserted here
        self.assertEqual(sorted((t['kind'], t['title'], t['state']) for t in tasks), [('draft', 'orders.csv', 'done'), ('upload', 'orders', 'done'), ('upload', '客户', 'done')])   # orders: the dataset the job's build made first
        self.assertEqual((by_kind['upload']['who'], by_kind['draft']['id']), ('小林', started['job_id']))


if __name__ == '__main__':
    unittest.main()
