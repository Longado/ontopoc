"""A small .xlsx can unpack to far more than its size (the security review made a 124 KB file of 1M rows that took the service from 63 MB to 556 MB).
Excel files are refused, in words, when what they unpack to or the cells they hold go past a cap, before the rows are kept in memory."""
import io
import unittest
import zipfile
from unittest import mock

from openpyxl import Workbook

from ontology_poc_generator import company_sources
from ontology_poc_generator.company_sources import SourceFileError, load_table_file


def workbook(rows: int, cols: int = 3) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append([f'列{c}' for c in range(cols)])
    for r in range(rows):
        sheet.append([r * cols + c for c in range(cols)])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class ExcelCapTests(unittest.TestCase):
    def test_a_workbook_with_more_cells_than_the_cap_is_refused_in_words(self):
        data = workbook(60)   # 61 rows × 3 cells
        with mock.patch.object(company_sources, 'MAX_CELLS', 100):
            with self.assertRaises(SourceFileError) as raised:
                load_table_file('t.xlsx', data)
        self.assertIn('单元格', str(raised.exception))
        self.assertEqual(len(load_table_file('t.xlsx', data)['sources']['Sheet']['records']), 60)   # under the real cap it reads as before

    def test_a_workbook_that_unpacks_past_the_cap_is_refused_before_it_is_opened(self):
        data = workbook(10)
        unpacked = sum(i.file_size for i in zipfile.ZipFile(io.BytesIO(data)).infolist())
        with mock.patch.object(company_sources, 'MAX_UNPACKED', unpacked - 1), mock.patch('openpyxl.load_workbook') as opened:
            with self.assertRaises(SourceFileError) as raised:
                load_table_file('t.xlsx', data)
        self.assertIn('解压', str(raised.exception))
        opened.assert_not_called()


    def test_a_csv_with_more_cells_than_the_cap_is_refused_too_and_the_caps_fit_a_ten_megabyte_upload(self):
        data = ('a,b\n' + ''.join(f'{i},x\n' for i in range(60))).encode()
        with mock.patch.object(company_sources, 'MAX_CELLS', 100):
            with self.assertRaises(SourceFileError) as raised:
                load_table_file('t.csv', data)
        self.assertIn('单元格', str(raised.exception))
        self.assertLessEqual(company_sources.MAX_CELLS, 1_000_000)        # the security review's file: a million rows of two cells
        self.assertLessEqual(company_sources.MAX_UNPACKED, 50 * 1024 * 1024)

if __name__ == '__main__':
    unittest.main()
