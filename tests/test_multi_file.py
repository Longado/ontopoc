import unittest

from ontology_poc_generator.company_sources import MAX_BYTES, SourceFileError, load_table_file, load_table_files

CUSTOMERS = '客户编号,名称\nC1,甲\nC2,乙\n'.encode('utf-8')
ORDERS = '订单号,客户编号,金额\nO1,C1,100\nO2,C2,50\n'.encode('utf-8')
OTHER_ORDERS = '订单号,数量\nO9,3\n'.encode('utf-8')


class MultiFileTests(unittest.TestCase):
    def test_several_tables_become_one_bundle_the_model_sees_together(self):
        bundle = load_table_files([('客户.csv', CUSTOMERS), ('订单.csv', ORDERS)], '摸底')
        self.assertEqual(sorted(bundle['sources']), ['客户', '订单'])
        self.assertEqual(bundle['file']['kind'], 'table')
        self.assertEqual([f['name'] for f in bundle['file']['files']], ['客户.csv', '订单.csv'])
        self.assertEqual(bundle['decision'], '摸底')

    def test_one_file_through_the_new_door_reads_the_same_as_through_the_old_one(self):
        one = load_table_files([('订单.csv', ORDERS)], None)
        old = load_table_file('订单.csv', ORDERS, None)
        self.assertEqual(one['sources'], old['sources'])
        self.assertEqual(one['file']['sha256'], old['file']['sha256'])   # a single file keeps the identity it always had

    def test_a_group_of_files_keeps_its_identity_whatever_order_they_are_picked_in(self):
        one = load_table_files([('客户.csv', CUSTOMERS), ('订单.csv', ORDERS)], None)
        other = load_table_files([('订单.csv', ORDERS), ('客户.csv', CUSTOMERS)], None)
        self.assertEqual(one['file']['sha256'], other['file']['sha256'])
        self.assertNotEqual(one['file']['sha256'], load_table_files([('订单.csv', ORDERS)], None)['file']['sha256'])

    def test_tables_of_the_same_name_from_two_files_are_told_apart_by_their_file(self):
        bundle = load_table_files([('本月.csv', ORDERS), ('上月.csv', OTHER_ORDERS)], None)
        self.assertEqual(sorted(bundle['sources']), ['上月', '本月'])   # each CSV is named after its own file
        same = load_table_files([('订单.csv', ORDERS), ('订单.csv', OTHER_ORDERS)], None)
        self.assertEqual(sorted(same['sources']), ['订单', '订单（2）'])   # same name twice: nothing to tell them apart but the order

    def test_a_file_that_cannot_be_read_names_itself_and_stops_the_batch(self):
        with self.assertRaisesRegex(SourceFileError, '坏的.csv'):
            load_table_files([('客户.csv', CUSTOMERS), ('坏的.csv', b''), ('订单.csv', ORDERS)], None)
        with self.assertRaisesRegex(SourceFileError, '报告.pdf'):
            load_table_files([('客户.csv', CUSTOMERS), ('报告.pdf', b'%PDF')], None)

    def test_the_limit_is_on_the_whole_batch(self):
        big = b'a,b\n' + b'1,2\n' * (MAX_BYTES // 4)
        with self.assertRaisesRegex(SourceFileError, '一共'):
            load_table_files([('一.csv', big), ('二.csv', big)], None)


if __name__ == '__main__':
    unittest.main()
