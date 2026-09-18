"""The ontology as a data platform's object form wants it: one CSV per object, the form's columns in the form's order.
Only the form is trusted (PLATFORM_FORM_REFERENCE.md); the batch import contract is untested, so the package says so and
carries no relation table."""
import base64
import io
import json
import unittest
import zipfile
from urllib.request import urlopen

from ontology_poc_generator.object_forms import COLUMNS, form_files
from tests.test_ontology_ask_server import QuestionModel, call
from tests.test_ontology_server import CSV, OntologyServerTests

HANDOVER = {'types': [{'type': 'order', 'label': '订单', 'identity_fields': ['orderID'], 'needs_single_key': False, 'fields': [
    {'path': 'orderID', 'identity': True, 'type': 'INTEGER', 'length': 5},
    {'path': 'freight', 'identity': False, 'type': 'DECIMAL', 'length': 6},
    {'path': 'orderDate', 'identity': False, 'type': 'DATETIME', 'length': 23},
    {'path': 'shipName', 'identity': False, 'type': 'VARCHAR', 'length': 34},
    {'path': 'note', 'identity': False, 'type': None, 'length': 0}]}]}
FORM = {'types': {'order': {'label': '销售订单', 'description': '客户的一次下单', 'display_field': 'orderID', 'drafted': False,
                            'fields': {'freight': {'label': '运费', 'description': '', 'drafted': True}}}}}


class FormFilesTests(unittest.TestCase):
    def test_one_csv_per_object_with_the_forms_columns_in_order(self):
        files = form_files({'object_types': [{'key': 'order', 'label': '订单'}]}, HANDOVER, FORM)
        self.assertEqual(sorted(files), ['order.csv', '说明.txt'])
        text = files['order.csv']
        self.assertTrue(text.startswith('﻿'))   # Excel reads the Chinese
        rows = [line.split(',') for line in text.lstrip('﻿').strip().split('\r\n')]
        self.assertEqual(rows[0], COLUMNS)
        self.assertEqual(COLUMNS, ['主键', '展示', '中文名称', '英文名称', '描述', '类型', '长度', '属性类型'])
        self.assertEqual(rows[1], ['是', '是', '', 'orderID', '', 'INT', '5', '主键'])
        self.assertEqual(rows[2], ['', '', '运费', 'freight', '', 'DOUBLE', '6', '数据导入'])
        self.assertEqual(rows[3][5], 'DATETIME')
        self.assertEqual(rows[5][5:7], ['', ''])   # an all-empty column has no type or length to say
        note = files['说明.txt']
        for said in ('销售订单', 'order.csv', '导入前', '实测'):
            self.assertIn(said, note)

    def test_an_object_needing_two_key_fields_is_called_out(self):
        two = {'types': [{**HANDOVER['types'][0], 'identity_fields': ['orderID', 'shipName'], 'needs_single_key': True}]}
        self.assertIn('orderID + shipName', form_files({'object_types': [{'key': 'order', 'label': '订单'}]}, two, None)['说明.txt'])


class FormExportServerTests(unittest.TestCase):
    def test_a_kept_run_downloads_as_a_zip_of_forms(self):
        with OntologyServerTests().server(gateway=QuestionModel()) as (base, _):
            _, run = call(base, '/api/ontology/build', {'filename': 'orders.csv', 'content_base64': base64.b64encode(CSV).decode()})
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/forms") as r:
                self.assertEqual(r.headers['Content-Type'], 'application/zip')
                names = zipfile.ZipFile(io.BytesIO(r.read())).namelist()
            self.assertEqual(sorted(names), ['customer.csv', 'order.csv', '说明.txt'])
            with urlopen(f"{base}/api/ontology/runs/{run['saved_as']}/export/forms?format=json") as r:
                self.assertEqual(sorted(json.load(r)['files']), ['customer.csv', 'order.csv', '说明.txt'])


if __name__ == '__main__':
    unittest.main()
