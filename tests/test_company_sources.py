from datetime import date, datetime
import io
import unittest

from openpyxl import Workbook

from ontology_poc_generator.company_sources import SourceFileError, load_table_file


def xlsx(sheets: dict) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class TableFileTests(unittest.TestCase):
    def test_each_excel_sheet_becomes_a_source_with_one_record_per_row(self):
        data = xlsx({
            '客户': [['客户编号', '客户名称', '签约日期'], ['C1', '甲公司', date(2026, 1, 2)], [None, None, None], ['C2', '乙公司', datetime(2026, 3, 4)]],
            '订单': [['订单号', '客户编号', '金额'], ['O1', 'C1', 100.0], ['O2', 'C2', 12.5]],
            '空表': [],
        })
        bundle = load_table_file('公司.xlsx', data)
        self.assertEqual(bundle['schema'], 'company_source_bundle.v1')
        self.assertEqual(list(bundle['sources']), ['客户', '订单'])
        self.assertEqual(bundle['sources']['客户']['records'], [
            {'客户编号': 'C1', '客户名称': '甲公司', '签约日期': '2026-01-02'},
            {'客户编号': 'C2', '客户名称': '乙公司', '签约日期': '2026-03-04'}])
        self.assertEqual([r['金额'] for r in bundle['sources']['订单']['records']], ['100', '12.5'])
        self.assertEqual(bundle['file']['name'], '公司.xlsx')
        self.assertEqual(len(bundle['file']['sha256']), 64)
        self.assertTrue(bundle['decision'])

    def test_csv_becomes_one_source_named_after_the_file(self):
        bundle = load_table_file('orders.csv', '﻿订单号,金额\nO1,100\nO2,\n'.encode('utf-8'))
        self.assertEqual(bundle['sources'], {'orders': {'records': [{'订单号': 'O1', '金额': '100'}, {'订单号': 'O2', '金额': None}],
                                                        'requests': []}})

    def test_gbk_csv_is_read(self):
        bundle = load_table_file('客户.csv', '编号,名称\nC1,甲公司\n'.encode('gb18030'))
        self.assertEqual(bundle['sources']['客户']['records'], [{'编号': 'C1', '名称': '甲公司'}])

    def test_blank_and_repeated_headers_get_names(self):
        bundle = load_table_file('t.csv', 'a,,a\n1,2,3\n'.encode('utf-8'))
        self.assertEqual(bundle['sources']['t']['records'], [{'a': '1', '列2': '2', 'a_2': '3'}])

    def test_the_purpose_line_is_kept(self):
        self.assertEqual(load_table_file('t.csv', b'a\n1\n', purpose='看售后')['decision'], '看售后')

    def test_refuses_unknown_empty_and_oversized_files(self):
        for name, data, message in (('a.pdf', b'%PDF', '不支持'), ('a.csv', b'', '空'), ('a.csv', b'a\n', '没有数据行'),
                                    ('a.xlsx', b'not a zip', 'Excel'), ('a.csv', b'a\n' + b'1\n' * 6_000_000, '太大')):
            with self.subTest(name=name, message=message), self.assertRaisesRegex(SourceFileError, message):
                load_table_file(name, data)


if __name__ == '__main__':
    unittest.main()
