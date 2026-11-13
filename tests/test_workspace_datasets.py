"""Datasets of the workspace: uploading, updating by key, overwriting, versions and previews, on the planted tables.

Expected counts are set by hand from tests/fixtures/planted (订单 has 160 rows, 客户 31, 产品 12) and from the rows each test builds.
"""
import base64
import csv
import io
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ontology_poc_generator.workspace_datasets import dataset_detail, list_datasets, upload
from ontology_poc_generator.workspace_store import merge_by_key, open_workspace
from tests.test_ontology_server import OntologyServerTests

PLANTED = Path(__file__).parent / 'fixtures' / 'planted'
ORDER_COLUMNS = ['订单号', '客户编号', '产品编号', '数量', '金额', '下单日期', '状态码', '交付天数']


def part(filename, data, **more):
    return {'filename': filename, 'content_base64': base64.b64encode(data).decode(), **more}


def planted(name, **more):
    return part(f'{name}.xlsx', (PLANTED / f'{name}.xlsx').read_bytes(), **more)


def table_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(ORDER_COLUMNS)
    writer.writerows(rows)
    return out.getvalue().encode('utf-8')


def order(number, customer='KH001', amount='100', status='0'):
    return [number, customer, 'CP01', '1', amount, '2026-06-01', status, '10']


def uploaded_all(conn, who='小林'):
    return upload(conn, [planted(p.stem) for p in sorted(PLANTED.glob('*.xlsx'))], who)


class MergeByKeyTests(unittest.TestCase):
    CURRENT = [{'id': 'a', 'v': '1'}, {'id': 'b', 'v': '2'}, {'id': 'c', 'v': '3'}]

    def test_changes_additions_and_untouched_rows_are_counted_and_nothing_is_deleted(self):
        rows, counts = merge_by_key(self.CURRENT, [{'id': 'a', 'v': '1'}, {'id': 'b', 'v': '9'}, {'id': 'd', 'v': '4'}], ['id'])
        self.assertEqual(counts, {'changed': 1, 'added': 1, 'unchanged': 1})
        self.assertEqual([(r['id'], r['v']) for r in rows], [('a', '1'), ('b', '9'), ('c', '3'), ('d', '4')])
        self.assertEqual(self.CURRENT[1], {'id': 'b', 'v': '2'})   # the input is not changed

    def test_a_column_only_the_file_has_is_added_and_one_it_lacks_keeps_its_values(self):
        rows, counts = merge_by_key(self.CURRENT, [{'id': 'a', 'note': 'x'}], ['id'])
        self.assertEqual(counts, {'changed': 1, 'added': 0, 'unchanged': 0})
        self.assertEqual(rows[0], {'id': 'a', 'v': '1', 'note': 'x'})
        self.assertEqual(rows[1], {'id': 'b', 'v': '2', 'note': None})

    def test_what_cannot_be_matched_without_guessing_is_refused(self):
        for incoming, key, words in [
            ([{'v': '1'}], ['id'], '没有主键列“id”'),
            ([{'id': 'a', 'v': '1'}], ['nope'], '没有主键列“nope”'),
            ([{'id': None, 'v': '1'}], ['id'], '主键是空的'),
            ([{'id': 'a', 'v': '1'}, {'id': 'a', 'v': '2'}], ['id'], '出现了 2 行'),
        ]:
            with self.subTest(words), self.assertRaisesRegex(ValueError, words):
                merge_by_key(self.CURRENT, incoming, key)
        with self.assertRaisesRegex(ValueError, '有 2 行'):
            merge_by_key([{'id': 'a', 'v': '1'}, {'id': 'a', 'v': '2'}], [{'id': 'a', 'v': '3'}], ['id'])


class DatasetStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)

    def test_a_new_name_makes_a_dataset_and_a_page_with_typed_columns_and_a_preview(self):
        results = upload(self.conn, [planted('订单')], '小林')
        self.assertEqual([(r['name'], r['mode'], r['version'], r['rows']) for r in results], [('订单', 'new', 1, 160)])
        listed = list_datasets(self.conn)
        self.assertEqual([(d['name'], d['rows'], d['columns'], d['version'], d['who'], d['used_by']) for d in listed], [('订单', 160, 8, 1, '小林', 0)])
        page = dataset_detail(self.conn, '订单')
        types = {c['name']: c['type'] for c in page['columns']}
        self.assertEqual((types['状态码'], types['下单日期'], types['金额']), ('integer', 'date', 'integer'))
        self.assertEqual(len(page['preview']['rows']), 50)
        self.assertEqual(page['preview']['rows'][0][0], 'DD20260001')
        self.assertEqual(page['preview']['total'], 160)
        keys = {c['name']: c['possible_key'] for c in page['columns']}
        self.assertTrue(keys['订单号'])
        self.assertFalse(keys['状态码'])
        self.assertEqual({c['name']: c['fill_rate'] for c in page['columns']}['订单号'], 1.0)

    def test_all_seven_planted_tables_upload_with_no_run(self):
        uploaded_all(self.conn)
        self.assertEqual({d['name']: d['rows'] for d in list_datasets(self.conn)},
                         {'订单': 160, '客户': 31, '产品': 12, '售后工单': 45, '库存快照': 72, '订单承诺': 121, '交付统计': 12})

    def test_update_by_key_changes_two_adds_three_and_deletes_nothing(self):
        upload(self.conn, [planted('订单')], '小林')
        first = dataset_detail(self.conn, '订单')['preview']['rows']
        rows = [order('DD20260001', amount='9999'), order('DD20260002', customer='KH002'),   # changed
                ['DD20260003', *dataset_detail(self.conn, '订单')['preview']['rows'][2][1:]],   # as it is
                order('DD20269001'), order('DD20269002'), order('DD20269003')]
        [r] = upload(self.conn, [part('订单-六月.csv', table_csv(rows), target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')
        self.assertEqual((r['name'], r['version'], r['rows'], r['created_version']), ('订单', 2, 163, True))
        self.assertEqual({k: r['changes'][k] for k in ('changed', 'added', 'unchanged')}, {'changed': 2, 'added': 3, 'unchanged': 1})
        self.assertEqual((r['key_check']['status'], r['key_check']['rows_checked']), ('passed', 163))
        page = dataset_detail(self.conn, '订单')
        self.assertEqual(page['rows'], 163)
        self.assertEqual(page['preview']['rows'][0][4], '9999')
        self.assertEqual(page['preview']['rows'][1][1], 'KH002')
        self.assertEqual([r[0] for r in page['preview']['rows']][2:5], ['DD20260003', 'DD20260004', 'DD20260005'])   # the rows it did not mention are still there
        self.assertEqual([(v['version'], v['who'], v['mode'], v['changed'], v['added'], v['unchanged'], v['current']) for v in page['versions']],
                         [(2, '小王', 'update_by_key', 2, 3, 1, True), (1, '小林', 'new', 0, 160, 0, False)])
        self.assertEqual(page['key_checks'][0]['columns'], ['订单号'])
        self.assertEqual(len(list_datasets(self.conn)), 1)
        self.assertEqual(first[0][4], '2520')

    def test_an_older_version_can_be_previewed_while_the_new_one_is_current(self):
        upload(self.conn, [planted('订单')], '小林')
        upload(self.conn, [part('x.csv', table_csv([order('DD20260001', amount='9999')]), target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')
        old, new = dataset_detail(self.conn, '订单', 1), dataset_detail(self.conn, '订单')
        self.assertEqual((old['version'], old['current_version'], old['preview']['rows'][0][4]), (1, 2, '2520'))
        self.assertEqual((new['version'], new['preview']['rows'][0][4]), (2, '9999'))
        self.assertIsNone(dataset_detail(self.conn, '订单', 3))

    def test_an_update_that_changes_nothing_makes_no_new_version(self):
        upload(self.conn, [planted('订单')], '小林')
        same = dataset_detail(self.conn, '订单')['preview']['rows'][:2]
        [r] = upload(self.conn, [part('x.csv', table_csv(same), target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')
        self.assertEqual((r['created_version'], r['version'], r['changes']['unchanged']), (False, 1, 2))
        self.assertEqual(len(dataset_detail(self.conn, '订单')['versions']), 1)

    def test_overwrite_replaces_every_row_as_a_new_version(self):
        upload(self.conn, [planted('订单')], '小林')
        [r] = upload(self.conn, [part('订单.csv', table_csv([order('A1'), order('A2')]), target='订单', mode='overwrite')], '小王')
        self.assertEqual((r['mode'], r['version'], r['rows'], r['changes']), ('overwrite', 2, 2, {'replaced_rows': 160}))
        page = dataset_detail(self.conn, '订单')
        self.assertEqual([row[0] for row in page['preview']['rows']], ['A1', 'A2'])
        self.assertEqual(dataset_detail(self.conn, '订单', 1)['rows'], 160)

    def test_a_taken_name_without_a_target_and_mode_is_refused_and_nothing_is_written(self):
        upload(self.conn, [planted('订单')], '小林')
        for more, words in [({}, '已经有叫“订单”的数据集'), ({'target': '订单'}, '一起写'), ({'mode': 'overwrite'}, '一起写'),
                            ({'target': '订单', 'mode': 'merge'}, '只有按主键更新'), ({'target': '订单', 'mode': 'update_by_key'}, '主键列'),
                            ({'target': '没有这个', 'mode': 'overwrite'}, '没有叫“没有这个”')]:
            with self.subTest(more), self.assertRaisesRegex(ValueError, words):
                upload(self.conn, [planted('客户'), part('订单.csv', table_csv([order('Z')]), **more)], '小王')
        self.assertEqual([d['name'] for d in list_datasets(self.conn)], ['订单'])   # the new 客户 in the same request was not written either
        self.assertEqual(dataset_detail(self.conn, '订单')['rows'], 160)

    def test_a_key_column_the_new_file_lacks_is_refused(self):
        upload(self.conn, [planted('订单')], '小林')
        data = '订单号,金额\nDD20260001,1\n'.encode()
        with self.assertRaisesRegex(ValueError, '新文件里没有主键列“客户编号”'):
            upload(self.conn, [part('x.csv', data, target='订单', mode='update_by_key', key_columns=['客户编号'])], '小王')
        self.assertEqual(len(dataset_detail(self.conn, '订单')['versions']), 1)

    def test_a_new_dataset_can_be_given_another_name_when_the_file_name_is_taken(self):
        upload(self.conn, [planted('订单')], '小林')
        [r] = upload(self.conn, [part('订单.csv', table_csv([order('B1')]), name='订单（试）')], '小林')
        self.assertEqual((r['name'], r['mode'], r['rows']), ('订单（试）', 'new', 1))
        self.assertEqual(len(list_datasets(self.conn)), 2)

    def test_a_workbook_with_two_sheets_makes_a_dataset_per_sheet_but_cannot_be_a_target(self):
        from openpyxl import Workbook
        book = Workbook()
        book.active.title = '甲'
        book.active.append(['编号', '值'])
        book.active.append(['1', '2'])
        book.create_sheet('乙').append(['编号', '值'])
        book['乙'].append(['3', '4'])
        buffer = io.BytesIO()
        book.save(buffer)
        results = upload(self.conn, [part('两张.xlsx', buffer.getvalue())], '小林')
        self.assertEqual(sorted(r['name'] for r in results), ['乙', '甲'])
        with self.assertRaisesRegex(ValueError, '2 个工作表'):
            upload(self.conn, [part('两张.xlsx', buffer.getvalue(), target='甲', mode='overwrite')], '小林')


class DatasetApiTests(unittest.TestCase):
    def call(self, base, path, payload=None):
        request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_upload_update_and_read_over_http_with_no_run(self):
        with OntologyServerTests().server() as (base, out):
            status, body = self.call(base, '/api/workspace/datasets/upload', {'who': '小林', 'files': [planted('订单'), planted('客户')]})
            self.assertEqual(status, 200, body)
            self.assertEqual([(r['name'], r['rows']) for r in body['results']], [('订单', 160), ('客户', 31)])
            status, body = self.call(base, '/api/workspace/datasets/upload', {'files': [planted('订单')]})
            self.assertEqual(status, 400)
            self.assertIn('已经有叫“订单”的数据集', body['error'])
            status, body = self.call(base, '/api/workspace/datasets/upload', {'who': '小王', 'files': [
                part('x.csv', table_csv([order('DD20260001', amount='7')]), target='订单', mode='update_by_key', key_columns=['订单号'])]})
            self.assertEqual((status, body['results'][0]['version']), (200, 2))
            _, listed = self.call(base, '/api/workspace/datasets')
            self.assertEqual({d['name']: (d['version'], d['who']) for d in listed['datasets']}, {'订单': (2, '小王'), '客户': (1, '小林')})
            status, page = self.call(base, f'/api/workspace/datasets/{quote("订单")}?version=1')
            self.assertEqual((status, page['version'], page['current_version'], page['preview']['rows'][0][4]), (200, 1, 2, '2520'))
            self.assertEqual(self.call(base, f'/api/workspace/datasets/{quote("没有")}')[0], 404)
            self.assertEqual(self.call(base, f'/api/workspace/datasets/{quote("订单")}?version=x')[0], 400)
            self.assertEqual([p.name for p in out.glob('*.json')], [])   # no run file anywhere


if __name__ == '__main__':
    unittest.main()
