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

from ontology_poc_generator.anchors import check_code, code_anchor
from ontology_poc_generator.code_meanings import code_columns
from ontology_poc_generator.named_views import save_definition, views_of_run
from ontology_poc_generator.pipelines import workspace_datasets
from ontology_poc_generator.relation_checks import check_relations
from ontology_poc_generator.workspace_datasets import UploadRefused, dataset_detail, list_datasets, upload
from ontology_poc_generator.workspace_store import current_dataset, dataset_records, merge_by_key, open_workspace, set_element_states
from tests.test_ontology_server import OntologyServerTests
from tests.test_relation_checks import DRAFT

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
        self.assertEqual(counts, {'changed': 1, 'added': 1, 'unchanged': 1, 'blank_kept': 0, 'changed_keys': ['b'], 'added_keys': ['d']})
        self.assertEqual([(r['id'], r['v']) for r in rows], [('a', '1'), ('b', '9'), ('c', '3'), ('d', '4')])
        self.assertEqual(self.CURRENT[1], {'id': 'b', 'v': '2'})   # the input is not changed

    def test_a_column_only_the_file_has_is_added_and_one_it_lacks_keeps_its_values(self):
        rows, counts = merge_by_key(self.CURRENT, [{'id': 'a', 'note': 'x'}], ['id'])
        self.assertEqual(counts, {'changed': 1, 'added': 0, 'unchanged': 0, 'blank_kept': 0, 'changed_keys': ['a'], 'added_keys': []})
        self.assertEqual(rows[0], {'id': 'a', 'v': '1', 'note': 'x'})
        self.assertEqual(rows[1], {'id': 'b', 'v': '2', 'note': None})

    def test_a_blank_cell_keeps_the_stored_value_and_is_not_a_change(self):
        rows, counts = merge_by_key(self.CURRENT, [{'id': 'c', 'v': ''}, {'id': 'b', 'v': None}, {'id': 'a', 'v': '5'}], ['id'])
        self.assertEqual({k: counts[k] for k in ('changed', 'added', 'unchanged', 'blank_kept')}, {'changed': 1, 'added': 0, 'unchanged': 2, 'blank_kept': 2})
        self.assertEqual([r['v'] for r in rows], ['5', '2', '3'])
        _, added = merge_by_key(self.CURRENT, [{'id': 'z', 'v': ''}], ['id'])   # a new row's blank is just blank
        self.assertEqual((added['added'], added['blank_kept']), (1, 0))

    def test_keys_match_as_numbers_in_plain_form_but_codes_with_a_leading_zero_stay_text(self):
        current = [{'id': '1', 'v': 'a'}, {'id': '2.5', 'v': 'b'}, {'id': '007', 'v': 'c'}]
        rows, counts = merge_by_key(current, [{'id': '1.0', 'v': 'x'}, {'id': ' 2.50 ', 'v': 'y'}, {'id': '7', 'v': 'z'}], ['id'])
        self.assertEqual({k: counts[k] for k in ('changed', 'added', 'unchanged')}, {'changed': 2, 'added': 1, 'unchanged': 0})
        self.assertEqual([(r['id'], r['v']) for r in rows], [('1', 'x'), ('2.5', 'y'), ('007', 'c'), ('7', 'z')])   # a matched key keeps its stored spelling
        with self.assertRaisesRegex(ValueError, '出现了 2 行'):
            merge_by_key(current, [{'id': '1', 'v': 'x'}, {'id': '1.0', 'v': 'y'}], ['id'])

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
        before = dataset_detail(self.conn, '订单')
        same = before['preview']['rows'][:2]
        [r] = upload(self.conn, [part('x.csv', table_csv(same), target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')
        self.assertEqual((r['created_version'], r['version'], r['changes']['unchanged']), (False, 1, 2))
        page = dataset_detail(self.conn, '订单')
        self.assertEqual(len(page['versions']), 1)
        self.assertEqual([(u['who'], u['unchanged'], u['file_rows'], u['key_columns']) for u in page['no_change_updates']], [('小王', 2, 2, ['订单号'])])
        self.assertEqual(page['updated_at'], before['updated_at'])   # a skipped update is not an update of the dataset

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


def small_xlsx(rows):
    from openpyxl import Workbook
    book = Workbook()
    for row in rows:
        book.active.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class UpdateDetailsTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        upload(self.conn, [part('k.csv', '编号,值,备注\n1,甲,x\n2,乙,y\n'.encode())], '小林')

    def update(self, filename, data, keys=('编号',)):
        [r] = upload(self.conn, [part(filename, data, target='k', mode='update_by_key', key_columns=list(keys))], '小王')
        return r

    def rows(self):
        return [tuple(r.values()) for r in dataset_records(self.conn, current_dataset(self.conn, 'k'))]

    def test_blank_cells_keep_what_was_stored_and_the_count_is_reported(self):
        r = self.update('x.csv', '编号,值,备注\n1,,\n2,丙,y\n'.encode())
        self.assertEqual({k: r['changes'][k] for k in ('changed', 'added', 'unchanged', 'blank_kept')}, {'changed': 1, 'added': 0, 'unchanged': 1, 'blank_kept': 2})
        self.assertEqual(self.rows(), [('1', '甲', 'x'), ('2', '丙', 'y')])
        self.assertEqual(dataset_detail(self.conn, 'k')['versions'][0]['blank_kept'], 2)

    def test_overwrite_still_writes_blanks(self):
        upload(self.conn, [part('x.csv', '编号,值,备注\n1,,\n'.encode(), target='k', mode='overwrite')], '小王')
        self.assertEqual(self.rows(), [('1', None, None)])

    def test_the_same_key_matches_from_csv_and_from_xlsx(self):
        r = self.update('x.csv', '编号,值,备注\n1.0,乙乙,\n'.encode())   # a CSV spells the number 1.0
        self.assertEqual((r['changes']['changed'], r['changes']['added'], r['rows']), (1, 0, 2))
        r = self.update('x.xlsx', small_xlsx([['编号', '值', '备注'], [2.0, '丙丙', None]]))   # an Excel cell holds the number 2.0
        self.assertEqual((r['changes']['changed'], r['changes']['added'], r['rows']), (1, 0, 2))
        self.assertEqual(self.rows(), [('1', '乙乙', 'x'), ('2', '丙丙', 'y')])

    def test_a_name_and_a_column_with_brackets_and_commas_read_back_whole(self):
        upload(self.conn, [part('o(1).csv', 'id,a\n1,x\n'.encode())], '小林')
        upload(self.conn, [part('x.csv', 'id,a\n2,y\n'.encode(), target='o(1)', mode='update_by_key', key_columns=['id'])], '小林')
        self.assertEqual([c['columns'] for c in dataset_detail(self.conn, 'o(1)')['key_checks']], [['id']])
        upload(self.conn, [part('c.csv', '"x,y",z\n1,2\n'.encode())], '小林')
        upload(self.conn, [part('c2.csv', '"x,y",z\n3,4\n'.encode(), target='c', mode='update_by_key', key_columns=['x,y'])], '小林')
        self.assertEqual([c['columns'] for c in dataset_detail(self.conn, 'c')['key_checks']], [['x,y']])
        self.assertEqual(dataset_detail(self.conn, 'c')['columns'][0]['key_check']['status'], 'passed')

    def test_malformed_requests_are_refused_in_words(self):
        for more, words in [({'key_columns': 5}, '主键列'), ({'key_columns': 'id'}, '主键列'), ({'key_columns': []}, '主键列'), ({'key_columns': [1]}, '主键列'),
                            ({'target': ['k'], 'mode': 'overwrite'}, 'target 要写成文字'), ({'name': 7}, 'name 要写成文字'), ({'target': 'k', 'mode': 5}, '导入方式')]:
            with self.subTest(more), self.assertRaisesRegex(ValueError, words):
                upload(self.conn, [part('x.csv', '编号,值\n1,a\n'.encode(), **{'target': 'k', 'mode': 'update_by_key', **more})], '小王')

    def test_every_refused_file_is_named_with_its_own_problem_and_nothing_is_written(self):
        upload(self.conn, [part('k2.csv', '编号,值\n1,a\n'.encode())], '小林')
        parts = [part('ok.csv', '编号\n9\n'.encode()),
                 part('a.csv', '编号,值\n1,b\n1,c\n'.encode(), target='k', mode='update_by_key', key_columns=['编号']),
                 part('b.csv', '编号\n1\n'.encode()),   # a taken name, no way chosen
                 part('c.csv', '值\n1\n'.encode(), target='k', mode='update_by_key', key_columns=['编号'])]
        parts[2]['filename'] = 'k2.csv'
        with self.assertRaises(UploadRefused) as caught:
            upload(self.conn, parts, '小王')
        self.assertEqual(sorted(caught.exception.files), [1, 2, 3])
        self.assertIn('出现了 2 行', caught.exception.files[1])
        self.assertIn('已经有叫“k2”的数据集', caught.exception.files[2])
        self.assertIn('没有主键列“编号”', caught.exception.files[3])
        self.assertNotIn('a.csv：', caught.exception.files[1])
        self.assertIn('a.csv：', str(caught.exception))
        self.assertEqual([d['name'] for d in list_datasets(self.conn)], ['k', 'k2'])   # ok.csv was not written either

    def test_a_version_names_the_first_fifty_rows_it_changed_and_added(self):
        from tests.test_workspace_datasets import order as make_order
        upload(self.conn, [planted('订单')], '小林')
        rows = [make_order(f'DD2026{n:04d}', amount='1') for n in range(1, 56)] + [make_order('NEW1'), make_order('NEW2')]
        upload(self.conn, [part('x.csv', table_csv(rows), target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')
        page = dataset_detail(self.conn, '订单')
        newest = page['versions'][0]
        self.assertEqual((newest['changed'], newest['added']), (55, 2))
        self.assertEqual((len(newest['changed_keys']), newest['changed_keys'][:2], newest['added_keys']), (50, ['DD20260001', 'DD20260002'], ['NEW1', 'NEW2']))
        self.assertEqual(dataset_detail(self.conn, '订单', 1)['version_at'], page['versions'][1]['at'])

    def test_numeric_keys_of_any_length_keep_every_digit(self):
        upload(self.conn, [part('b.csv', 'id,v\n123456789012345678901234567890001,a\n-0.0,z\n'.encode())], '小林')
        [r] = upload(self.conn, [part('x.csv', 'id,v\n123456789012345678901234567890002,b\n0,y\n'.encode(), target='b', mode='update_by_key', key_columns=['id'])], '小王')
        self.assertEqual({k: r['changes'][k] for k in ('changed', 'added')}, {'changed': 1, 'added': 1})   # the 0 matched -0.0; the 30-digit key did not match its neighbour
        self.assertEqual(r['changes']['added_keys'], ['123456789012345678901234567890002'])
        rows = [(x['id'], x['v']) for x in dataset_records(self.conn, current_dataset(self.conn, 'b'))]
        self.assertEqual(rows, [('123456789012345678901234567890001', 'a'), ('-0.0', 'y'), ('123456789012345678901234567890002', 'b')])
        self.assertEqual(merge_by_key([{'id': '1.500'}], [{'id': '1.5'}], ['id'])[1]['unchanged'], 1)

    def test_a_cell_the_csv_reader_cannot_hold_is_refused_in_words(self):
        with self.assertRaisesRegex(ValueError, '无法作为 CSV 读取'):
            upload(self.conn, [part('big.csv', ('id,v\n1,' + 'x' * 200000 + '\n').encode())], '小林')

    def test_a_file_with_no_data_rows_is_refused(self):
        for name, data in [('h.csv', '编号,值\n'.encode()), ('b.xlsx', small_xlsx([[None, None]]))]:
            with self.subTest(name), self.assertRaisesRegex(ValueError, '没有数据行'):
                upload(self.conn, [part(name, data)], '小林')


KEY = 'abcdef0123456789'   # what the definitions are kept under
CODES = {'values': [{'value': '0', 'label': '进行中', 'description': ''}, {'value': '1', 'label': '已交付', 'description': ''},
                    {'value': '2', 'label': '已取消', 'description': ''}]}


class ConsumersReadTheNewVersionTests(unittest.TestCase):
    """What reads the planted tables (a view, a code anchor, a relation check) is handed the current version of each dataset: after an update
    by key it reads the new one. Those consumers are given dataset ids, so this is the check that a new version's id is a good one."""

    def setUp(self):
        self.conn = open_workspace(':memory:')
        self.addCleanup(self.conn.close)
        uploaded_all(self.conn)

    def current(self):
        return {d['name']: current_dataset(self.conn, d['name']) for d in list_datasets(self.conn)}

    def seen(self):
        """(valid orders, the 订单→客户 side, the 状态码 profile with the rows it came from), all read from the current versions."""
        current = self.current()
        tables = workspace_datasets(self.conn, {n: d['id'] for n, d in current.items()})
        view = {v['name']: v for v in views_of_run(self.conn, KEY, 'run00001', DRAFT, tables)}['有效订单']
        [relation] = [r for r in check_relations(self.conn, DRAFT, current) if r['key'] == 'order_customer']
        records = dataset_records(self.conn, current['订单'])
        [profile] = [p for p in code_columns({'sources': {'订单': {'records': records}}}) if p['column'] == '状态码']
        return view, relation['sides'][0], profile, records

    def test_the_view_the_code_anchor_and_the_relation_check_all_move_to_the_new_version(self):
        set_element_states(self.conn, [(f'property:{KEY}:订单.状态码', 'confirmed', None, '小林', CODES)])
        save_definition(self.conn, KEY, {'name': '有效订单', 'kind': 'filter', 'base': '订单', 'column': '状态码', 'op': 'is_not', 'label': '已取消'},
                        workspace_datasets(self.conn, {n: d['id'] for n, d in self.current().items()}), DRAFT, '小林')
        view, side, profile, records = self.seen()
        self.assertEqual((view['rows'], side['rows'], side['matched'], side['unmatched']), (144, 160, 157, 3))
        anchor = code_anchor(profile, records)
        self.assertEqual(check_code(anchor, {'2': '已取消'}, profile, records), [])
        upload(self.conn, [part('x.csv', table_csv([order('DD20269001', 'KH001', status='0'), order('DD20269002', 'KH999', status='1'), order('DD20269003', 'KH001', status='3')]),
                                target='订单', mode='update_by_key', key_columns=['订单号'])], '小王')
        view, side, profile, records = self.seen()
        self.assertEqual((view['rows'], side['rows'], side['matched'], side['unmatched']), (147, 163, 159, 4))   # 163 orders, 16 of them cancelled; KH999 joins KH099
        self.assertEqual(check_code(anchor, {'2': '已取消'}, profile, records), ['多了取值 3（1 行）'])


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
            for bad in ('x', '²', '99999999999999999999', '-1'):
                self.assertEqual(self.call(base, f'/api/workspace/datasets/{quote("订单")}?version={quote(bad)}')[0], 400, bad)
            status, body = self.call(base, '/api/workspace/datasets/upload', {'files': [planted('订单'), part('x.csv', table_csv([order('A')]), target='订单', mode='overwrite'),
                                                                                       part('y.csv', table_csv([order('A')]), target='没有这个', mode='overwrite')]})
            self.assertEqual((status, sorted(body['files'])), (400, ['0', '2']))   # 订单 as a new name is taken, 没有这个 is not a dataset, the overwrite of 订单 is fine
            for bad in (5, 'id', None):
                status, body = self.call(base, '/api/workspace/datasets/upload', {'files': [part('x.csv', table_csv([order('A')]), target='订单', mode='update_by_key', key_columns=bad)]})
                self.assertEqual(status, 400, bad)
                self.assertIn('主键列', body['error'])
            self.assertEqual([p.name for p in out.glob('*.json')], [])   # no run file anywhere


if __name__ == '__main__':
    unittest.main()
